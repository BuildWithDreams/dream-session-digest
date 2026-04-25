---
name: dream-session-digest
description: Venice-powered nightly session digest for Hermes CLI — clusters similar sessions, generates blog-style summaries, emails via himalaya, and publishes Jekyll posts to dream-blog with GitHub evidence links.
version: 5.0.0
tags: [hermes, session, digest, blog, jekyll, venice-ai, github]
related_skills: []
---

# Hermes Session Digest

Nightly email digest of Hermes CLI sessions, with augmented GitHub evidence links and automatic Jekyll blog post publication.

**Script:** `session_digest.py`
**Evidence scanner:** `fetch_github_evidence.py`
**Blog:** `https://buildwithdreams.github.io/dream-blog`

## Pipeline

```
4am cron trigger
    ↓
fetch_github_evidence.py — queries GitHub API for commits/PRs/issues by dream-hermes-agent
    ↓
Writes session_evidence.json (commits, PRs, issues)
    ↓
session_digest.py — clusters sessions, summarizes via Venice, builds email + blog post
    ↓
Email sent via himalaya → inbox
    ↓
Jekyll post pushed to BuildWithDreams/dream-blog → GitHub Pages (auto-publishes)
```

## Usage

```bash
# Dry run (no email, no blog push)
python3 session_digest.py --dry-run

# Single day
python3 session_digest.py 2026-04-22

# Date range
python3 session_digest.py 2026-04-01 2026-04-22

# Review a digest (Feature A)
# Step 1 — generate questions:
python3 session_digest.py --review 2026-04-23
# Step 2 — provide answers:
python3 session_digest.py --review 2026-04-23 --answers '[1] answer; [4] follow-up'
```

## New Features (v5)

### Feature A — Review Addendum (§2)
Trigger with "review today" or "review digest for YYYY-MM-DD" in Telegram, or `--review` CLI flag. Generates Q&A questions about the session, collects answers, and appends a `## Review Addendum — reviewed-v1` block to the blog post with `reviewed: true` in front matter.

```bash
# Telegram:
/review digest for 2026-04-23

# CLI:
python3 session_digest.py --review 2026-04-23
```

### Feature B — Where This Leads (§3)
Trigger with "where this leads" in any session. Builds a `## Where This Leads` section with three sub-sections:
- **Contextual Links** — GitHub issues/PRs/commits and external URLs extracted from the session
- **Threaded Insights** — cross-digest insights tracked in `digest_insights.yaml`
- **Future Anchors** — TODO items, follow-ups, deferred decisions

Insights with ≥3 digest references are flagged `standalone_candidate` and can be promoted to deep-dive posts.

### Feature C — Deep-Dive Promotion (§4)
Insights accumulated over multiple digests can be promoted to standalone blog posts via review questionnaire. Blog post front matter includes `digest_sources` referencing all contributing dates.

### Feature D — Media Queue (§5.8)
Queue PNG/JPG/WebP/MP4/WebM files from Telegram for the next digest run. Files are committed to `assets/media/YYYY-MM-DD/` in the blog repo and embedded as markdown images in the post.

```bash
# In Telegram, send an image with a caption
# It is queued and embedded on next digest run
```

## Config System

User-specific values live in `~/.hermes/scripts/digest_config.yaml` — the repo scripts read it at startup with fallback to BuildWithDreams defaults.

| File | Purpose |
|------|---------|
| `~/.hermes/scripts/digest_config.yaml` | Your values — email to, GitHub org, tracked repos, blog repo |
| `~/.hermes/scripts/digest_config_TEMPLATE.yaml` | Annotated template — copy and fill in |
| `~/.hermes/.env` | `VENICE_API_KEY` and `GITHUB_PAT` (reused for blog push) |

The script falls back to BuildWithDreams defaults when `digest_config.yaml` is absent.

## Evidence Scanner

`fetch_github_evidence.py` uses two sources:

1. **Session parsing** (authoritative) — scans session files for git push output, gh repo create, and gh issue create tool results
2. **GitHub REST API** — enriches with author, date, files_changed for commits; fetches issue titles if missing from session output

Manifest saved to: `~/.hermes/scripts/session_evidence.json`

**Important:** When a new BWD repo is created during a session, add it to `tracked_repos` in `digest_config.yaml` so the API enrichment queries it. The session scanner auto-detects new repos regardless.

## Digest Output

Both email and blog post contain:
1. **Session summaries** — clustered by topic+time, one Venice-powered summary per cluster
2. **GitHub Activity section** — structured changelog: new repos, commits (compact bullets, repo header, SHA + 70-char message + files count), issues (with title resolved via API)

**Formatting rules:**
- Commit messages truncated to 70 chars to keep the changelog scannable
- Each commit has a clickable SHA link to the commit on GitHub
- Issues section only appears when there are issues

## Architecture

### Two-Source Evidence Model

The evidence scanner (`fetch_github_evidence.py`) combines two independent sources:

1. **Session scanner** (authoritative) — parses git push output and gh commands directly from session tool calls. Bypasses the author attribution problem: commits made via a machine user's SSH key from a different local machine have a different author identity in GitHub's API, so `?author=` queries return nothing.
2. **GitHub API** (enrichment) — fills in metadata (author name, date, files_changed count) for commits already found via the session scanner.

This separation is important: the API alone misses all commits where the git author doesn't match the GitHub username. The session scanner is ground truth.

**What the session scanner detects:**
- `gh repo create` output → `"Created: BuildWithDreams/repo-name"` → new repo events
- `gh issue create` output → `"Issue created: https://github.com/.../issues/N"` → issue events
- `git push` blocks → `"[main sha] message\n...\nTo github.com:org/repo.git\n old..new main -> main"` → commit events (normal and force-push)

**Git push block format (how it appears in session tool output):**
```
{"output": "🔍 Scanning staged files...\n✅ No secrets detected\n[main 0c41cd4] docs: add SKILL.md\n 2 files changed, 283 insertions(+)\n...\nTo github.com:BuildWithDreams/repo.git\n   old..new  main -> main", ...}
```

Force push format (note the `+` prefix on the remote update line):
```
{"output": "...\nTo github.com:BuildWithDreams/repo.git\n + abc1234...def5678  main -> main (forced update)", ...}
```

### Platform Detection

`detect_platform(session_file)` reads line 0 of each JSONL file to find the `session_meta.platform` field. Returns `telegram`, `cli`, `api_server`, `discord`, or `unknown`.

Telegram sessions are flagged in the digest header (e.g. `2 Telegram sessions`) for curation awareness. The platform data is carried through clustering and into the summary entries, available for future platform-aware processing.

### Clustering

Union-find on Jaccard similarity (>=0.35) + time window (3h):
- A≈B and B≈C → all three in one cluster
- Topic fingerprint: top 40 terms by frequency — camelCase, paths, 5+ char words

### Project Assignment (deduplication)

`match_tags()` scores each project by keyword hit count and returns only the **best-match** project per session. Labels (if any) are still returned for all matches.

### Venice Config
```python
MODEL = "e2ee-gpt-oss-120b-p"
VENICE_BASE_URL = "https://api.venice.ai/api/v1"
MAX_WORKERS = 1
```

### Concurrency Control

`/tmp/session_digest.lock` — fcntl.flock prevents concurrent runs.

## Session File Formats (two coexist)

**Current (April 2026+):** `~/.hermes/sessions/YYYYMMDD_HHMMSS_hash.jsonl`
- JSONL — one JSON object per line, keys: `role`, `content`
- Platform: `telegram` (derived from `session_meta` on line 0)
- Message extraction: read each line as JSON, skip malformed lines, collect `content` field

**Legacy (March 2026):** `~/.hermes/sessions/session_YYYYMMDD_HHMMSS_hash.json`
- JSON with top-level fields: `session_id`, `model`, `platform`, `session_start`, `messages[]`
- Message extraction: parse `messages[]` array, collect `content` field
- Both formats are read correctly by `session_digest.py`

## Key Files

| Path | Purpose |
|------|---------|
| `session_digest.py` | Main digest script — reads `~/.hermes/scripts/digest_config.yaml` |
| `fetch_github_evidence.py` | Evidence scanner — reads same config |
| `~/.hermes/scripts/digest_config.yaml` | User config (gitignored — never commit secrets) |
| `~/.hermes/scripts/digest_config_TEMPLATE.yaml` | Annotated template |
| `~/.hermes/sessions/*.jsonl` | Current session files (one JSON object per line) |
| `~/.hermes/sessions/session_*.json` | Legacy session files (JSON with messages array) |
| `~/.hermes/sessions/projects.yaml` | Project → keyword mapping |
| `~/.hermes/sessions/labels.yaml` | Label → keyword mapping |
| `~/.hermes/scripts/session_evidence.json` | GitHub evidence manifest |
| `~/.hermes/dream-blog-clone/` | Temp clone dir for blog publishing |

## Publishing as a Reusable Skill

The hardcoding has been extracted to `digest_config.yaml`. Both scripts read it at startup with fallback to BuildWithDreams defaults. To adopt for another org:

1. Copy `digest_config_TEMPLATE.yaml` → `~/.hermes/scripts/digest_config.yaml`
2. Fill in: `email.to`, `github.org`, `github.tracked_repos`, `github.blog_repo`
3. Ensure `~/.hermes/.env` has `VENICE_API_KEY` and `GITHUB_PAT`
4. Set up the symlinks (see below)

### Symlink Setup

After cloning the repo, set up symlinks so `~/.hermes/scripts/` points to the repo versions:

```bash
# From the repo directory
ln -sf "$(pwd)/session_digest.py" ~/.hermes/scripts/session_digest.py
ln -sf "$(pwd)/fetch_github_evidence.py" ~/.hermes/scripts/fetch_github_evidence.py

# The skill is the repo itself
# ~/.hermes/skills/dream-session-digest is a symlink → the repo directory
```

### Cron Job

```bash
0 4 * * * cd ~/code/dream-session-digest && python3 session_digest.py >> ~/.hermes/scripts/digest_cron.log 2>&1
```
