#!/usr/bin/env python3
"""
Nightly Session Digest — Venice-powered LLM session summaries.
Reads raw session JSONs, extracts conversation text, asks Venice AI (e2ee-gpt-oss-120b-p)
for a concise one-line summary per session, groups by project, and emails via himalaya.

Usage:
    python3 session_digest.py                    # tonight's sessions (last 24h)
    python3 session_digest.py 2026-03-21          # single day
    python3 session_digest.py 2026-03-21 2026-03-31  # date range
"""

import fcntl
import os
import sys
import glob
import re
import json
import time
import math
import hashlib
import argparse
import subprocess
import yaml
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

# Load .env for Venice API key
load_dotenv(os.path.expanduser("~/.hermes/.env"))

# ── Config ──────────────────────────────────────────────────────────────────
# Load from digest_config.yaml — see digest_config_TEMPLATE.yaml for docs.
# Silent fallback to hardcoded BWD defaults so existing runs keep working.

CONFIG_FILE = os.path.expanduser("~/.hermes/scripts/digest_config.yaml")
_template_warn = False

def _load_config():
    """Load digest config with fallback to hardcoded BWD defaults."""
    global _template_warn
    try:
        with open(CONFIG_FILE) as f:
            cfg = yaml.safe_load(f)
        return cfg
    except FileNotFoundError:
        _template_warn = True
        return None

_config = _load_config()

def _cfg_get(*keys, default=None):
    """Navigate nested dict: _cfg_get('github', 'org', default='BuildWithDreams')"""
    if _config is None:
        return default
    val = _config
    for k in keys:
        try:
            val = val[k]
        except (TypeError, KeyError):
            return default
    return val if val is not None else default

# ── Paths ────────────────────────────────────────────────────────────────────
SESSIONS_DIR  = os.path.expanduser(_cfg_get("sessions", "dir", default="~/.hermes/sessions"))
ARCHIVE_DIR   = os.path.join(SESSIONS_DIR, "digest_archive")
HIMALAYA     = os.path.expanduser(_cfg_get("sessions", "himalaya", default="~/.local/bin/himalaya"))

# ── Email ────────────────────────────────────────────────────────────────────
EMAIL_FROM   = _cfg_get("email", "from", default="hermesreport@verus.trading")
EMAIL_TO_STR = _cfg_get("email", "to", default=["imylomylo@gmail.com", "mylo@verus.trading"])
if isinstance(EMAIL_TO_STR, list):
    EMAIL_TO = ", ".join(EMAIL_TO_STR)
else:
    EMAIL_TO = str(EMAIL_TO_STR)

PROJECTS_FILE = os.path.join(SESSIONS_DIR, "projects.yaml")
LABELS_FILE   = os.path.join(SESSIONS_DIR, "labels.yaml")

# ── GitHub ───────────────────────────────────────────────────────────────────
GITHUB_ORG   = _cfg_get("github", "org", default="BuildWithDreams")
BLOG_REPO    = _cfg_get("github", "blog_repo", default="dream-blog")

# Blog push token — reuse GITHUB_PAT (already set in ~/.hermes/.env)
GH_BLOG_TOKEN = os.getenv("GITHUB_PAT", "")

# Evidence scanner script
EVIDENCE_SCRIPT = os.path.expanduser("~/.hermes/scripts/fetch_github_evidence.py")

# ── Venice AI Config ────────────────────────────────────────────────────────
VENICE_API_KEY   = os.getenv("VENICE_API_KEY", "")
VENICE_BASE_URL  = "https://api.venice.ai/api/v1"
MODEL            = "e2ee-gpt-oss-120b-p"
MAX_WORKERS      = 1   # Venice has low rate limits — 1 at a time prevents 429s

# ── Helpers ──────────────────────────────────────────────────────────
def load_yaml(path):
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def extract_messages_from_session(filepath):
    """Extract user/assistant message text from a session file.
    Handles two formats:
      - .json  (legacy): top-level 'messages' array
      - .jsonl (current): one JSON object per line with 'role'/'content'
    """
    try:
        with open(filepath, "r", errors="replace") as fh:
            raw = fh.read()
    except Exception:
        return ""

    # Try JSONL first (one object per line)
    if filepath.endswith(".jsonl"):
        messages = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return extract_text_from_messages(messages)

    # Fall back to legacy JSON with 'messages' array
    try:
        data = json.loads(raw)
        messages = data.get("messages", [])
        return extract_text_from_messages(messages)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return extract_via_regex(raw)


def extract_text_from_messages(messages):
    """Pull readable text from a list of message objects (handles JSONL format)."""
    lines = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, str) and content.strip():
            lines.append(f"[{role.upper()}] {content.strip()}")
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text = item.get("text", "") or ""
                        if text.strip():
                            lines.append(f"[{role.upper()}] {text.strip()}")
                    elif item.get("type") == "tool_result":
                        text = str(item.get("content", "") or "").strip()
                        if text:
                            lines.append(f"[{role.upper()}/tool] {text[:300]}")
    return "\n".join(lines)


def extract_via_regex(raw):
    """Fallback: extract content fields via regex from raw text."""
    texts = re.findall(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    return "\n".join(texts[:50])  # limit to first 50 to avoid huge strings


def detect_platform(session_file):
    """Fast platform detection — reads only line 0 to find session_meta.

    Returns 'telegram', 'cli', or 'unknown' based on the session_meta
    marker at the start of the JSONL file. Falls back to 'unknown' for
    legacy .json files and edge cases where no session_meta is present.
    """
    try:
        with open(session_file) as f:
            first_line = f.readline().strip()
        if first_line:
            obj = json.loads(first_line)
            if obj.get('role') == 'session_meta':
                platform = obj.get('platform', 'unknown')
                if platform in ('telegram', 'cli', 'api_server', 'discord'):
                    return platform
    except Exception:
        pass
    return 'unknown'


def get_sessions_for_date(date_str):
    """Return list of session file paths for a given YYYY-MM-DD date.
    Handles both .jsonl (current Telegram sessions) and .json (CLI/legacy sessions).
    Filenames use YYYYMMDD format (e.g. 20260321_114101_83c17c.jsonl).
    """
    compact = date_str.replace("-", "")   # YYYY-MM-DD -> YYYYMMDD
    # Match both .jsonl (current Telegram) and .json (CLI/legacy) session files
    jsonl_pattern = os.path.join(SESSIONS_DIR, f"{compact}_*.jsonl")
    json_pattern  = os.path.join(SESSIONS_DIR, f"session_{compact}_*.json")
    return sorted(glob.glob(jsonl_pattern)) + sorted(glob.glob(json_pattern))


def load_projects_and_labels():
    """Load keyword matching tables."""
    projects_data = load_yaml(PROJECTS_FILE).get("projects", {})
    labels_data   = load_yaml(LABELS_FILE).get("labels", {})

    proj_keywords = {k: v.get("keywords", []) for k, v in projects_data.items()}
    label_keywords = {k: v.get("keywords", []) for k, v in labels_data.items()}
    return proj_keywords, label_keywords


# ── Topic Clustering ──────────────────────────────────────────────────
# Sessions on the same topic (within a time window, with keyword overlap)
# are merged before summarization to avoid near-duplicate summaries.

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "as", "is", "was", "are", "were", "been", "be", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "must", "shall", "can", "need", "dare", "ought", "used", "it", "its",
    "this", "that", "these", "those", "i", "you", "he", "she", "we", "they",
    "what", "which", "who", "whom", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just", "about",
    "also", "into", "our", "your", "their", "if", "then", "else", "while", "during",
    "before", "after", "above", "below", "between", "under", "again", "further",
    "once", "here", "there", "any", "all", "because", "out", "up", "down", "off",
    "over", "now", "new", "one", "two", "first", "last", "get", "got", "let",
    "made", "make", "put", "say", "see", "look", "think", "go", "come", "take",
    "use", "using", "used", "file", "path", "line", "code", "like", "run", "back",
    "thing", "way", "right", "left", "ok", "okay", "yes", "yeah", "no", "nope",
    "well", "even", "still", "yet", "already", "always", "never", "ever", "each",
    "done", "now", "being", "though", "although", "however", "whether", "else",
    "instead", "rather", "thus", "hence", "therefore", "otherwise", "anyway",
}

TIME_WINDOW_HOURS = 3      # sessions within this window are clustering candidates
TOPIC_SIMILARITY   = 0.35   # Jaccard similarity threshold for clustering


def extract_topic_fingerprint(text):
    """Extract a weighted topic fingerprint from transcript text.
    Uses TF-IDF-like scoring: terms that are frequent in THIS text but
    rare across the corpus of all sessions get highest weight.
    Returns a set of the top-scoring terms (up to 40).
    """
    # Pull out code-adjacent words
    words = re.findall(r"[a-z]+(?:[A-Z][a-z]+)+", text)          # camelCase
    words += re.findall(r"(?:^|[/\-_])[\w]{3,}(?=[/\-_]|$)", text.lower())  # paths/idents
    words += re.findall(r"\b[a-z]{5,}\b", text.lower())           # plain words 5+
    words += re.findall(r"\b[A-Z]{2,}\b", text)                  # ALL_CAPS consts

    # Normalise
    normalized = []
    for w in words:
        w = w.lower().strip("_-/")
        if w and w not in STOPWORDS and not w.isdigit() and len(w) > 3:
            normalized.append(w)

    # Count frequency
    freq = Counter(normalized)

    # Score: raw frequency (topic prominence in this session)
    # Top 40 terms by frequency
    top = [w for w, _ in freq.most_common(60)]

    return set(top[:40])


def jaccard(a, b):
    """Jaccard similarity between two sets."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def cluster_sessions(session_files):
    """Group sessions by time proximity + topic similarity.
    Uses union-find to find all connected components (sessions within
    TIME_WINDOW_HOURS with Jaccard similarity >= TOPIC_SIMILARITY),
    then forms clusters from those components.

    Returns list of clusters; each cluster is a dict:
      { files: [...], meta: {...}, fingerprint: set, start: datetime, raw_texts: [...] }
    """
    # Load metadata + fingerprints for all files
    loaded = []
    for f in session_files:
        meta = extract_session_metadata(f)
        raw_text = extract_messages_from_session(f)
        fp = extract_topic_fingerprint(raw_text)
        try:
            start = datetime.fromisoformat(meta["session_start"].replace("Z", "+00:00"))
        except Exception:
            start = datetime.fromisoformat(meta["timestamp"], format="%b %d, %Y %I:%M %p")
            start = start.replace(tzinfo=timezone.utc)
        loaded.append({"file": f, "meta": meta, "fingerprint": fp,
                       "start": start, "raw_text": raw_text,
                       "platform": detect_platform(f)})

    # Sort by start time
    loaded.sort(key=lambda x: x["start"])
    n = len(loaded)

    # Union-find with time-window constraint
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path halving
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # For each pair of sessions, if both time-close AND topic-similar, union them
    for i in range(n):
        for j in range(i + 1, n):
            hours_diff = abs((loaded[j]["start"] - loaded[i]["start"]).total_seconds()) / 3600
            if hours_diff > TIME_WINDOW_HOURS:
                break  # sorted by time, so later j values only get further away
            sim = jaccard(loaded[i]["fingerprint"], loaded[j]["fingerprint"])
            if sim >= TOPIC_SIMILARITY:
                union(i, j)

    # Gather clusters from union-find components
    from collections import defaultdict
    comps = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(loaded[i])

    clusters = []
    for members in comps.values():
        cluster = {
            "files": [m["file"] for m in members],
            "meta": members[0]["meta"],
            "fingerprint": set.union(*[m["fingerprint"] for m in members]) if members else set(),
            "start": min(m["start"] for m in members),
            "raw_texts": [m["raw_text"] for m in members],
            "platforms": set(m.get("platform", "unknown") for m in members),
        }
        clusters.append(cluster)

    # Sort clusters by earliest session start time
    clusters.sort(key=lambda c: c["start"])
    return clusters


def match_tags(text, proj_keywords, label_keywords):
    """Match text against keyword tables, return (best_project, labels[]).
    Returns the single best-matching project (most keyword hits) to avoid
    duplicate session entries appearing in multiple project sections.
    Falls back to first match on tie. Returns ([], labels[]) if no match.
    """
    text_lower = text.lower()
    projects_matched = []
    labels = []

    for name, kws in proj_keywords.items():
        hits = sum(1 for kw in kws if kw.lower() in text_lower)
        if hits > 0:
            projects_matched.append((hits, name))

    for name, kws in label_keywords.items():
        if any(kw.lower() in text_lower for kw in kws):
            labels.append(name)

    # Pick best project: most keyword hits; break ties by first
    if projects_matched:
        projects_matched.sort(key=lambda x: -x[0])
        return [projects_matched[0][1]], labels

    return [], labels


def extract_session_metadata(filepath):
    """Get session_id, timestamp, model, platform from a session file via regex.
    Handles two formats:
      - .json  (legacy): top-level fields in the JSON object
      - .jsonl (current): metadata must be derived from filename
    """
    basename = os.path.basename(filepath)

    # JSONL: metadata encoded in filename (20260422_050819_92805f24.jsonl)
    if basename.endswith(".jsonl"):
        m = re.match(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_([a-f0-9]+)\.jsonl", basename)
        if m:
            year, month, day, hour, minute, second, hash_ = m.groups()
            session_start = f"{year}-{month}-{day}T{hour}:{minute}:{second}"
            ts = f"{datetime.fromisoformat(session_start).strftime('%b %d, %Y %I:%M %p')}"
            return {
                "session_id": basename.replace(".jsonl", ""),
                "model": "minimax",
                "platform": "telegram",
                "timestamp": ts,
                "session_start": session_start,
            }
        # Fallback: use file mtime
        mtime = os.path.getmtime(filepath)
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return {
            "session_id": basename.replace(".jsonl", ""),
            "model": "minimax",
            "platform": "telegram",
            "timestamp": dt.strftime("%b %d, %Y %I:%M %p"),
            "session_start": dt.isoformat(),
        }

    # Legacy .json format
    try:
        with open(filepath, "r", errors="replace") as fh:
            raw = fh.read()
        data = json.loads(raw)
        sid   = data.get("session_id", basename)
        model = data.get("model", "?")
        plat  = data.get("platform", "cli")
        start = data.get("session_start", "")
    except:
        raw = open(filepath, "r", errors="replace").read()
        sid_m  = re.search(r'"session_id"\s*:\s*"([^"]+)"', raw)
        model_m = re.search(r'"model"\s*:\s*"([^"]+)"', raw)
        plat_m  = re.search(r'"platform"\s*:\s*"([^"]+)"', raw)
        start_m = re.search(r'"session_start"\s*:\s*"([^"]+)"', raw)
        sid   = sid_m.group(1)   if sid_m   else basename
        model = model_m.group(1) if model_m else "?"
        plat  = plat_m.group(1)  if plat_m  else "cli"
        start = start_m.group(1) if start_m else ""

    # Parse timestamp
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        ts = dt.strftime("%b %d, %Y %I:%M %p")
    except:
        ts = start[:16] if start else "?"

    return {"session_id": sid, "model": model, "platform": plat, "timestamp": ts, "session_start": start}


# ── LLM Summarization ─────────────────────────────────────────────────

LLM_SYSTEM_PROMPT = (
    "You are a senior engineer writing a session digest for your past self. "
    "Your job is to extract what actually mattered from a coding session — the breakthroughs, "
    "the hard-won fixes, and the things built from scratch. "
    "Write 2-4 sentences in a blog-post style: narrative, not a list. "
    "Skip mundane back-and-forth, debugging noise, and tool-call blizzard. "
    "If the session was just troubleshooting with no resolution, say so briefly. "
    "Highlight what was different, hard, or worth remembering. "
    "Write it like you're proud of what you did. No markdown, no headers."
)

LLM_USER_PROMPT = (
    "Write a short digest of this session (2-4 sentences, blog style):\n"
    "{transcript}\n\n"
    "Focus on: what was built/solved/achieved. Skip noise. Write with engineer's pride."
)


def summarize_via_venice(transcript: str) -> str:
    """Call Venice AI (e2ee-gpt-oss-120b-p) to summarize a session transcript."""
    if not transcript.strip():
        return "Empty session."

    # Truncate if very long to stay within context
    if len(transcript) > 8000:
        transcript = transcript[:8000] + "\n[truncated]"

    payload = {
        "model": MODEL,
        "max_tokens": 1000,
        "messages": [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": LLM_USER_PROMPT.format(transcript=transcript)},
        ],
        "venice_parameters": {
            "strip_thinking_response": True,
        },
    }

    headers = {
        "Authorization": f"Bearer {VENICE_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(3):
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{VENICE_BASE_URL}/chat/completions",
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())

            # Straightforward — content is a plain string field
            msg = result.get("choices", [{}])[0].get("message", {})
            content = msg.get("content") or ""
            if content.strip():
                return content.strip()

            # finish_reason == length means content was truncated mid-stream
            finish_reason = result.get("choices", [{}])[0].get("finish_reason", "")
            if finish_reason == "length":
                return "[Summary too long — try shortening the transcript]"

            # Fallback: try reasoning_content if present
            reasoning = result.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "").strip()
            if reasoning:
                return reasoning

            return "[Summary unavailable: empty response]"
        except Exception as e:
            last_error = e
            if attempt < 2:
                import time
                time.sleep(2 ** attempt)

    return f"[Summary unavailable: {last_error}]"


# ── Session worker (per-cluster) ───────────────────────────────────────

def summarize_cluster_worker(cluster):
    """Worker: merge transcripts in a cluster, summarize once via Venice.
    Returns a single entry dict with the merged summary and cluster metadata.
    """
    # Merge all raw texts in this cluster (separator helps LLM distinguish sections)
    merged_transcript = "\n\n===== SESSION SEGMENT =====\n\n".join(cluster["raw_texts"])

    meta = cluster["meta"]
    summary = summarize_via_venice(merged_transcript)

    # One entry per cluster — not one per original session
    return {
        **meta,
        "summary": summary,
        "cluster_size": len(cluster["files"]),
        "cluster_files": [os.path.basename(f) for f in cluster["files"]],
        "platforms": cluster.get("platforms", set()),
    }


# ── Email ─────────────────────────────────────────────────────────────

def render_evidence_section(manifest):
    """
    Render evidence manifest as a structured changelog-style text block.
    Includes repos created, commits grouped by repo, and issues.
    """
    from collections import defaultdict
    lines = []
    org = manifest.get("org", "BuildWithDreams")
    repos_created = manifest.get("repos_created", [])
    commits = manifest.get("commits", [])
    issues = manifest.get("issues", [])

    # ── Repos Created ────────────────────────────────────────────────────────
    if repos_created:
        lines.append(f"\n📦 **New Repos — {org}**")
        for r in repos_created:
            repo = r["repo"]
            desc = r.get("description", "Repository created")
            lines.append(f"  * `+` **[{repo}]({r['url']})** — {desc}")

    # ── Changelog: Commits by repo ──────────────────────────────────────────
    commits_by_repo = defaultdict(list)
    for c in commits:
        commits_by_repo[c["repo"]].append(c)

    for repo, repo_commits in sorted(commits_by_repo.items()):
        lines.append(f"\n🛠️ **[{repo}](https://github.com/{org}/{repo})** — {len(repo_commits)} commit(s)")
        for c in sorted(repo_commits, key=lambda x: x.get("sha", "")):
            sha = c.get("sha", "?")[:7]
            msg = c.get("message", "")[:70]
            files = c.get("files_changed", 0)
            files_str = f" · {files} file(s)" if files else ""
            lines.append(f"  * `{sha}` {msg}{files_str}")

    # ── PRs ──────────────────────────────────────────────────────────────────
    for pr in manifest.get("merged_prs", []):
        lines.append(f"\n🔀 **[PR #{pr['number']}]({pr['url']})** — {pr['title']}")

    # ── Issues ───────────────────────────────────────────────────────────────
    if issues:
        lines.append(f"\n📋 **Issues**")
    for issue in issues:
        icon = "✅" if issue.get("state") == "open" else "❌"
        lines.append(f"\n{icon} **[#{issue['number']}]({issue['url']})** — {issue.get('title', issue.get('msg', ''))}")

    if not lines:
        lines.append("\n_(No GitHub activity recorded this period)_")

    return "\n".join(lines)


def load_evidence_manifest(date_str):
    """Load pre-built evidence manifest for a given date."""
    manifest_path = os.path.expanduser("~/.hermes/scripts/session_evidence.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        # Re-render text section
        manifest["_text"] = render_evidence_section(manifest)
        return manifest
    except Exception:
        return {"commits": [], "merged_prs": [], "issues": [], "_text": ""}


def build_email(date_str, sessions_data, proj_keywords, label_keywords, evidence=None):
    """Build email body grouped by project."""
    # Derive merge stats from sessions_data (each entry has cluster_size)
    total_sessions = sum(e.get("cluster_size", 1) for e in sessions_data)
    total_clusters = len(sessions_data)
    merged_away = total_sessions - total_clusters

    # Group by project
    by_project = defaultdict(list)
    uncategorized = []

    for entry in sessions_data:
        summary = entry.get("summary", "")
        projects, labels = match_tags(summary, proj_keywords, label_keywords)
        entry["projects"] = projects
        entry["labels"] = labels

        if projects:
            for p in projects:
                by_project[p].append(entry)
        else:
            uncategorized.append(entry)

    # Build email lines
    # Platform awareness — detect Telegram sessions for header context
    all_platforms = set()
    for e in sessions_data:
        all_platforms.update(e.get("platforms", set()))
    telegram_sessions = [e for e in sessions_data if "telegram" in e.get("platforms", set())]
    telegram_count = len(telegram_sessions)

    header = f"SESSION DIGEST — {date_str}"
    if merged_away:
        header += f"  ({merged_away} sessions merged away)"
    header += f"\n{total_clusters} cluster(s) from {total_sessions} session(s)"
    if telegram_count:
        header += f"  ({telegram_count} Telegram session{'s' if telegram_count > 1 else ''})"

    lines = [
        header,
        "=" * 50,
        "",
    ]

    for proj, entries in sorted(by_project.items()):
        lines.append(f"\n[{proj.upper()}] ({len(entries)} cluster(s))")
        lines.append("-" * 40)
        for e in sorted(entries, key=lambda x: x.get("timestamp", "")):
            ts = e.get("timestamp", "?")
            sid = e.get("session_id", "?")
            model = e.get("model", "?")
            summary = e.get("summary", "?")
            labels = " ".join(f"#{l}" for l in e.get("labels", []) if l)
            merged_note = f" ({e.get('cluster_size', 1)} sessions merged)" if e.get("cluster_size", 1) > 1 else ""
            lines.append(f"\n  [{ts}] {sid} · {model}{merged_note}")
            if labels:
                lines.append(f"  Tags: {labels}")
            lines.append(f"  {summary}")

    if uncategorized:
        lines.append(f"\n[UNCATEGORIZED] ({len(uncategorized)} cluster(s))")
        lines.append("-" * 40)
        for e in sorted(uncategorized, key=lambda x: x.get("timestamp", "")):
            ts = e.get("timestamp", "?")
            sid = e.get("session_id", "?")
            summary = e.get("summary", "?")
            merged_note = f" ({e.get('cluster_size', 1)} sessions merged)" if e.get("cluster_size", 1) > 1 else ""
            lines.append(f"\n  [{ts}] {sid}{merged_note}")
            lines.append(f"  {summary}")

    lines.append("\n---\nSummaries via Venice e2ee-gpt-oss-120b-p · Hermes Session Digest")

    # Append GitHub evidence section if available
    if evidence and evidence.get("_text"):
        lines.append("\n\n**GitHub Activity This Period**")
        lines.append(evidence["_text"])

    return "\n".join(lines)


# ── Blog Post ──────────────────────────────────────────────────────────

BLOG_REPO_DIR = os.path.expanduser("~/.hermes/dream-blog-clone")


def build_blog_post(date_str, sessions_data, proj_keywords, label_keywords, evidence=None):
    """Build a Jekyll-formatted blog post from sessions data."""
    from collections import defaultdict

    total_sessions = sum(e.get("cluster_size", 1) for e in sessions_data)
    total_clusters = len(sessions_data)

    by_project = defaultdict(list)
    uncategorized = []
    for entry in sessions_data:
        summary = entry.get("summary", "")
        projects, labels = match_tags(summary, proj_keywords, label_keywords)
        entry["projects"] = projects
        entry["labels"] = labels
        if projects:
            for p in projects:
                by_project[p].append(entry)
        else:
            uncategorized.append(entry)

    # Platform awareness — Telegram sessions get flagged for appropriate curation
    telegram_sessions = [e for e in sessions_data if "telegram" in e.get("platforms", set())]
    telegram_count = len(telegram_sessions)

    body_lines = []
    for proj, entries in sorted(by_project.items()):
        body_lines.append(f"## {proj}\n")
        for e in sorted(entries, key=lambda x: x.get("timestamp", "")):
            ts = e.get("timestamp", "?")
            summary = e.get("summary", "?")
            merged_note = f" ({e.get('cluster_size', 1)} sessions)" if e.get("cluster_size", 1) > 1 else ""
            labels = ", ".join(f"`{l}`" for l in e.get("labels", []) if l)
            body_lines.append(f"**{ts}**{merged_note}")
            if labels:
                body_lines.append(f"_Tags: {labels}_")
            body_lines.append(summary)
            body_lines.append("")

    if uncategorized:
        body_lines.append("## Uncategorized\n")
        for e in sorted(uncategorized, key=lambda x: x.get("timestamp", "")):
            ts = e.get("timestamp", "?")
            summary = e.get("summary", "?")
            merged_note = f" ({e.get('cluster_size', 1)} sessions)" if e.get("cluster_size", 1) > 1 else ""
            body_lines.append(f"**{ts}**{merged_note}")
            body_lines.append(summary)
            body_lines.append("")

    if evidence and evidence.get("_text"):
        body_lines.append("## GitHub Activity\n")
        body_lines.append(evidence["_text"])

    body = "\n".join(body_lines)

    post = f"""---
layout: default
title: "Session Digest — {date_str}"
date: {date_str}
---

_Generated by [Hermes Session Digest](https://github.com/BuildWithDreams/dream-session-digest) · {total_clusters} cluster(s) from {total_sessions} session(s){f" · {telegram_count} Telegram session{'s' if telegram_count > 1 else ''}" if telegram_count else ""}_

{body}

*This digest was generated automatically by an autonomous AI agent. Evidence links reflect actual commits, PRs, and issues from the [{GITHUB_ORG}](https://github.com/{GITHUB_ORG}) GitHub organization.*
"""
    return post


def push_blog_post(date_str, sessions_data, proj_keywords, label_keywords, evidence, dry_run=False):
    """Clone dream-blog, add/update the Jekyll post, push."""
    import shutil
    import subprocess

    post_content = build_blog_post(date_str, sessions_data, proj_keywords, label_keywords, evidence)

    blog_token = GH_BLOG_TOKEN
    if not blog_token:
        print("[Blog] GITHUB_PAT env var not set — cannot push", file=sys.stderr)
        return False

    blog_clone_url = f"https://{blog_token}@github.com/{GITHUB_ORG}/{BLOG_REPO}.git"
    repo_dir = os.path.expanduser("~/.hermes/dream-blog-clone")
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)

    try:
        result = subprocess.run(
            ["git", "clone", blog_clone_url, repo_dir],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"[Blog] Clone failed: {result.stderr}", file=sys.stderr)
            shutil.rmtree(repo_dir, ignore_errors=True)
            return False
        if not os.path.isdir(repo_dir):
            print("[Blog] Clone dir not created", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[Blog] Clone failed: {e}", file=sys.stderr)
        return False

    post_path = os.path.join(repo_dir, "_posts", f"{date_str}-session-digest.md")
    os.makedirs(os.path.join(repo_dir, "_posts"), exist_ok=True)
    with open(post_path, "w") as f:
        f.write(post_content)
    print(f"[Blog] Wrote {post_path}")

    if dry_run:
        print("[Blog] Dry run — not pushing")
        shutil.rmtree(repo_dir, ignore_errors=True)
        return True

    try:
        subprocess.run(["git", "add", "_posts/"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"docs: add session digest for {date_str}"],
            cwd=repo_dir, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=repo_dir, capture_output=True, text=True, timeout=30,
        )
        print(f"[Blog] Pushed to dream-blog")
        return True
    except Exception as e:
        print(f"[Blog] Push failed: {e}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


def send_email(subject, body):
    input_data = f"""From: {EMAIL_FROM}
To: {EMAIL_TO}
Subject: {subject}

{body}
"""
    proc = subprocess.Popen(
        [HIMALAYA, "template", "send"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    _, stderr = proc.communicate(input=input_data, timeout=120)
    if proc.returncode != 0:
        print(f"Email send failed: {stderr}", file=sys.stderr)
        return False
    return True


# ── Main ─────────────────────────────────────────────────────────────

def get_date_range(args):
    """Resolve date range from CLI args."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.date and args.end_date:
        return args.date, args.end_date
    elif args.date:
        return args.date, args.date
    else:
        # Default: last 24 hours
        start = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d")
        return start, today


# PID lock — prevents concurrent runs from hammering Venice's rate limits
LOCK_FILE = "/tmp/session_digest.lock"


def acquire_lock():
    """Fail fast if another digest is already running."""
    import fcntl
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd
    except BlockingIOError:
        print("[Digest] Another instance is running. Exiting.")
        sys.exit(0)


def release_lock(lock_fd):
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()
    try:
        os.unlink(LOCK_FILE)
    except FileNotFoundError:
        pass


def run(date_str, end_date_str, dry_run=False, verbose=False):
    lock_fd = acquire_lock()
    try:
        _run_inner(date_str, end_date_str, dry_run, verbose)
    finally:
        release_lock(lock_fd)


def _run_inner(date_str, end_date_str, dry_run=False, verbose=False):
    """Inner run — all actual logic lives here."""
    print(f"[Digest] Processing {date_str} → {end_date_str}")

    current = datetime.strptime(date_str, "%Y-%m-%d")
    end     = datetime.strptime(end_date_str, "%Y-%m-%d")
    all_session_files = []

    while current <= end:
        ds = current.strftime("%Y-%m-%d")
        files = get_sessions_for_date(ds)
        if files:
            print(f"[Digest] {ds}: {len(files)} session(s)")
            all_session_files.extend(files)
        current += timedelta(days=1)

    if not all_session_files:
        print("[Digest] No sessions found for range.")
        return

    print(f"[Digest] Clustering {len(all_session_files)} sessions by topic + time...")
    clusters = cluster_sessions(all_session_files)
    cluster_sizes = [len(c["files"]) for c in clusters]
    total_merged = sum(n - 1 for n in cluster_sizes if n > 1)
    print(f"[Digest] {len(clusters)} clusters ({total_merged} sessions merged away)")

    # Load keyword tables once
    proj_keywords, label_keywords = load_projects_and_labels()

    # Summarize each cluster via Venice (one at a time to avoid 429s)
    sessions_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(summarize_cluster_worker, c): c for c in clusters}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            sessions_data.append(result)
            # Print once per cluster
            n = result.get("cluster_size", 1)
            summary_preview = result.get("summary", "")[:80]
            note = f" ({n} merged)" if n > 1 else ""
            print(f"[{i}/{len(clusters)}]{note} {summary_preview}...")
            # Brief pause between clusters to let rate limiter breathe
            if i < len(clusters):
                time.sleep(3)

    # Build and send email
    subject = f"Session Digest — {date_str}"
    if date_str != end_date_str:
        subject = f"Session Digest — {date_str} to {end_date_str}"

    # Fetch GitHub evidence before building email
    evidence = None
    try:
        result = subprocess.run(
            ["python3", EVIDENCE_SCRIPT, date_str],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "GITHUB_TOKEN": os.getenv("GITHUB_PAT", "")},
        )
        print(f"[Evidence] {result.stdout.strip()}")
        evidence = load_evidence_manifest(date_str)
    except Exception as e:
        print(f"[Evidence] Skipped: {e}", file=sys.stderr)

    body = build_email(date_str, sessions_data, proj_keywords, label_keywords, evidence=evidence)

    if dry_run:
        print("\n========== EMAIL PREVIEW ==========")
        print(body)
        print("==================================")
        return

    if send_email(subject, body):
        print("[Digest] Email sent!")
        # Push blog post
        push_blog_post(date_str, sessions_data, proj_keywords, label_keywords, evidence)
        # Archive processed sessions
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        for f in all_session_files:
            basename = os.path.basename(f)
            archive_path = os.path.join(ARCHIVE_DIR, basename)
            if os.path.exists(archive_path):
                archive_path = os.path.join(
                    ARCHIVE_DIR,
                    f"{os.path.splitext(basename)[0]}_{datetime.now(timezone.utc).strftime('%H%M%S')}.json",
                )
            # Don't actually move — sessions are source of truth
            # Just touch a marker that this was processed
            marker = archive_path + ".sent"
            with open(marker, "w") as mf:
                mf.write(f"Processed: {datetime.now(timezone.utc).isoformat()}\nSubject: {subject}\n")
            print(f"[Digest] Marked {basename}")
    else:
        print("[Digest] Send failed.")


def main():
    parser = argparse.ArgumentParser(description="Hermes Session Digest")
    parser.add_argument("date", nargs="?", help="Start date YYYY-MM-DD (default: last 24h)")
    parser.add_argument("end_date", nargs="?", help="End date YYYY-MM-DD (default: same as date)")
    parser.add_argument("--dry-run", action="store_true", help="Print email without sending")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    date_str, end_date_str = get_date_range(args)
    run(date_str, end_date_str, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
