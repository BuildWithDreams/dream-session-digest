"""
Feature B — "Where This Leads" Section Builder (DIGEST.md §3)

Generates the "Where This Leads" section for a digest on-demand.
Triggered only when the user explicitly says "where this leads" or similar.
Three sub-sections: Contextual Links, Threaded Insights, Future Anchors.

Usage:
    triggered = is_where_this_leads_triggered(session_text)
    section   = build_where_this_leads_section(session_text, trigger_date="2026-04-25")
    links     = extract_contextual_links(session_text)
    anchors   = extract_future_anchors(session_text)
"""
import re
from urllib.parse import urlparse


# ── Config ─────────────────────────────────────────────────────────────────────

import os

CONFIG_FILE = os.path.expanduser("~/.hermes/scripts/digest_config.yaml")

def _load_config():
    try:
        import yaml
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

_config = _load_config()

def _cfg_get(*keys, default=None):
    val = _config
    for k in keys:
        try:
            val = val[k]
        except (TypeError, KeyError):
            return default
    return val if val is not None else default


DEFAULT_TRIGGER_PHRASES = [
    "where this leads",
    "log this as a thread",
    "track this as a thread",
    "open thread",
]

DEFAULT_MAX_LINKS = 5
DEFAULT_MAX_ANCHORS = 5


# ── Trigger detection ─────────────────────────────────────────────────────────

def is_where_this_leads_triggered(session_text: str) -> bool:
    """
    Returns True if session contains the forward-links trigger phrase.

    §3 trigger:
    - Default: "where this leads" or "log this as a thread"
    - Case-insensitive
    - Configurable via forward_links.trigger_phrase
    """
    text_lower = session_text.lower()

    # Load configured trigger phrases
    configured_phrase = _cfg_get("forward_links", "trigger_phrase", default=None)
    trigger_phrases = DEFAULT_TRIGGER_PHRASES.copy()
    if configured_phrase:
        trigger_phrases = [configured_phrase.lower()] + trigger_phrases

    return any(phrase in text_lower for phrase in trigger_phrases)


# ── Contextual Links ──────────────────────────────────────────────────────────

GITHUB_URL_RE = re.compile(
    r"https?://github\.com/([\w-]+)/([\w\.\-]+)/(issues|pull|commit)/([^\s)\]\'\"]+)"
)
EXTERNAL_URL_RE = re.compile(
    r"https?://(?!github\.com)([^\s)\]\'\"]+)"
)


def extract_contextual_links(
    session_text: str,
    max_links: int | None = None,
) -> list[dict]:
    """
    Extract GitHub and external URLs from session text.

    Returns list of dicts:
        { "url": "...", "type": "issue|PR|commit|external", "description": "..." }

    §5.3: capped at max_contextual_links (default 5).
    """
    if max_links is None:
        max_links = _cfg_get("forward_links", "max_contextual_links", default=DEFAULT_MAX_LINKS)

    seen = set()
    results = []

    # GitHub URLs
    for m in GITHUB_URL_RE.finditer(session_text):
        org, repo, link_type, ref = m.groups()
        url = m.group(0).rstrip("/")
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "url": url,
            "type": link_type,
            "org": org,
            "repo": repo,
            "ref": ref,
            "description": f"{link_type.title()} {ref}",
        })
        if len(results) >= max_links:
            break

    # External URLs
    for m in EXTERNAL_URL_RE.finditer(session_text):
        url = m.group(0).rstrip("/.,;:!?")
        if url in seen:
            continue
        if any(url.startswith(gh) for gh in ["https://github.com", "http://github.com"]):
            continue
        seen.add(url)
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        results.append({
            "url": url,
            "type": "external",
            "description": f"External: {domain}",
        })
        if len(results) >= max_links:
            break

    return results[:max_links]


# ── Future Anchors ─────────────────────────────────────────────────────────────

TODO_RE = re.compile(r"^\s*[-*]\s*\[\s*[ xX]\s*\] (.+)", re.MULTILINE)
TODO_UNCHECKED_RE = re.compile(r"^\s*[-*]\s*(.+)", re.MULTILINE)
DEFERRED_RE = re.compile(r"\b(defer|postponed|deferred|deferring)\b", re.IGNORECASE)
FOLLOWUP_RE = re.compile(r"\b(next steps?|follow[-\s]?up|todo|task|action item)\b", re.IGNORECASE)


def extract_future_anchors(
    session_text: str,
    max_anchors: int | None = None,
) -> list[str]:
    """
    Extract TODO items, follow-ups, and deferred decisions from session text.

    §3.2 Future Anchors: checklist format `- [ ] Item`
    Capped at max_anchors (default 5).
    """
    if max_anchors is None:
        max_anchors = _cfg_get("forward_links", "max_anchors", default=DEFAULT_MAX_ANCHORS)

    anchors = []

    # Explicit TODO checkboxes
    for m in TODO_RE.finditer(session_text):
        text = m.group(1).strip()
        if text and len(anchors) < max_anchors:
            anchors.append(text)

    # Plain bullet items (not checkbox items, already captured above)
    if len(anchors) < max_anchors:
        for m in TODO_UNCHECKED_RE.finditer(session_text):
            item = m.group(1).strip()
            # Skip checkbox items already captured by TODO_RE
            if re.match(r"^\[[ xX]\]", item):
                continue
            if item and item not in anchors:
                anchors.append(item)
            if len(anchors) >= max_anchors:
                break

    # Follow-up / action item mentions
    if len(anchors) < max_anchors:
        for m in FOLLOWUP_RE.finditer(session_text):
            # Get the surrounding sentence
            start = max(0, m.start() - 80)
            end = min(len(session_text), m.end() + 80)
            sentence = session_text[start:end].strip()
            # Extract a clean phrase
            clean = re.sub(r"[^\w\s\-:]", "", sentence).strip()
            if clean and clean not in anchors:
                anchors.append(clean[:120])
            if len(anchors) >= max_anchors:
                break

    # Deferred decisions
    if len(anchors) < max_anchors:
        for m in DEFERRED_RE.finditer(session_text):
            start = max(0, m.start() - 100)
            end = min(len(session_text), m.end() + 50)
            snippet = session_text[start:end].strip().split("\n")[0][:120]
            if snippet and snippet not in anchors:
                anchors.append(snippet)
            if len(anchors) >= max_anchors:
                break

    return anchors[:max_anchors]


# ── Section builder ────────────────────────────────────────────────────────────

def build_where_this_leads_section(
    session_text: str,
    trigger_date: str = "",
    trigger_phrases: list | None = None,
) -> str:
    """
    Build the full "Where This Leads" section.

    Only generates content if is_where_this_leads_triggered() returns True.
    Otherwise returns empty string (no auto-add).

    §3 output format:

    ## Where This Leads

    ### → Contextual Links
    - [repo#issue-N](url) — brief description

    ### 💡 Threaded Insights
    (populated by insight_store integration — stub for now)

    ### 📌 Future Anchors
    - [ ] Item 1
    - [ ] Item 2
    """
    if trigger_phrases is None:
        trigger_phrases = DEFAULT_TRIGGER_PHRASES

    # Check trigger — but allow caller to force build
    # (if called directly, always build if called)
    if not session_text:
        return ""

    # Quick trigger check
    if not is_where_this_leads_triggered(session_text):
        return ""

    sections = ["## Where This Leads\n"]

    # --- Contextual Links
    links = extract_contextual_links(session_text)
    if links:
        sections.append("### → Contextual Links\n")
        for link in links:
            if link["type"] == "issue":
                label = f"[{link['repo']}#{link['ref']}]({link['url']})"
            elif link["type"] == "pull":
                label = f"[PR #{link['ref']}: {link['repo']}]({link['url']})"
            elif link["type"] == "commit":
                sha = link["ref"][:7]
                label = f"[{sha}]({link['url']})"
            else:
                label = f"[External: {link.get('description', link['url'])}]({link['url']})"
            sections.append(f"- {label}\n")
        sections.append("\n")

    # --- Future Anchors
    anchors = extract_future_anchors(session_text)
    if anchors:
        sections.append("### 📌 Future Anchors\n")
        for anchor in anchors:
            sections.append(f"- [ ] {anchor}\n")
        sections.append("\n")

    result = "".join(sections).strip()
    return result + "\n" if result else ""
