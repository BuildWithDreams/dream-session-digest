# dream-session-digest

**Autonomous nightly session digest for Hermes CLI — delivered by email and published to a Jekyll blog.**

Every evening at 4 AM UTC, this system:

1. Collects the day's Hermes CLI sessions from `~/.hermes/sessions/`
2. Clusters sessions by topic + time proximity
3. Generates one Venice AI summary per cluster
4. Scans for GitHub activity (commits, PRs, issues) from the session itself — not author attribution
5. Emails a digest to configured recipients
6. Pushes a Jekyll-formatted blog post to [dream-blog](https://buildwithdreams.github.io/dream-blog)

## Why This Exists

Hermes CLI sessions are dense. Reviewing a long session to remember what was decided takes time. The digest compresses the day into a readable changelog so you can recall what the agent did, and why, at a glance.

The GitHub evidence links ground the summaries in real commits — no he-said-she-said between what the agent reported and what actually landed on GitHub.

## How It Works

```
~/.hermes/sessions/         ← raw session JSONL files
~/.hermes/scripts/
  session_digest.py         ← main script (symlinked from this repo)
  fetch_github_evidence.py   ← evidence scanner (symlinked from this repo)
  digest_config.yaml        ← your config (gitignored)
  session_evidence.json     ← cached GitHub evidence (gitignored)
```

Sessions are clustered using union-find on Jaccard topic similarity (≥0.35) within a 3-hour time window. Telegram sessions (which run 3–4× longer than CLI sessions) are flagged in the digest header for awareness.

## Setup

### 1. Clone this repo

```bash
git clone https://github.com/BuildWithDreams/dream-session-digest.git ~/code/dream-session-digest
```

### 2. Link the scripts

```bash
ln -sf ~/code/dream-session-digest/session_digest.py ~/.hermes/scripts/session_digest.py
ln -sf ~/code/dream-session-digest/fetch_github_evidence.py ~/.hermes/scripts/fetch_github_evidence.py
```

### 3. Configure

Copy and edit the config:

```bash
cp ~/code/dream-session-digest/digest_config_TEMPLATE.yaml \
   ~/.hermes/scripts/digest_config.yaml
# Edit digest_config.yaml with your email, org, and tracked repos
```

Set environment variables:

```bash
# ~/.hermes/.env
VENICE_API_KEY=vk-...        # Venice AI API key
GITHUB_PAT=ghp_...           # GitHub PAT with repo and org scope
```

### 4. Verify

```bash
python3 ~/.hermes/scripts/session_digest.py --dry-run
```

### 5. Schedule

```bash
0 4 * * * cd ~/code/dream-session-digest && python3 session_digest.py >> ~/.hermes/scripts/digest_cron.log 2>&1
```

## Digest Output

Each digest contains:

- **Session summaries** — one per cluster, Venice AI-generated, 2–3 sentences
- **GitHub Activity** — new repos, commits (with SHA links), issues
- **Platform awareness** — Telegram sessions flagged in the header

Example header:
```
SESSION DIGEST — 2026-04-23
2 cluster(s) from 9 session(s)  (1 Telegram session)
```

## File Formats

The system reads two session file formats:

| Format | Path pattern | Platform |
|--------|-------------|----------|
| JSONL (current) | `YYYYMMDD_HHMMSS_hash.jsonl` | Telegram, CLI |
| JSON (legacy) | `session_YYYYMMDD_HHMMSS_hash.json` | March 2026 sessions |

## Republishing a Digest

To republish a past digest (e.g. today's):

```bash
python3 ~/.hermes/scripts/session_digest.py 2026-04-23
```

Dry run first:
```bash
python3 ~/.hermes/scripts/session_digest.py 2026-04-23 --dry-run
```

## Adopting for Another Org

The scripts are parameterized — no code changes needed. Fill in `digest_config.yaml`:

```yaml
github:
  org: "YOUR_ORG_NAME"
  blog_repo: "your-blog-repo"
  tracked_repos:
    - repo-name-1
    - repo-name-2

email:
  from: "sender@example.com"
  to:
    - "recipient@example.com"
```

See `digest_config_TEMPLATE.yaml` for the full reference.

## Repository Structure

```
dream-session-digest/
├── SKILL.md                      ← technical skill reference
├── README.md                     ← this file
├── DIGEST.md                     ← feature spec (source of truth)
├── session_digest.py             ← main digest script (symlinked to ~/.hermes/scripts/)
├── fetch_github_evidence.py      ← GitHub evidence scanner
├── review_addendum.py            ← Feature A: review dialog + addendum builder
├── review_questions.py           ← Feature A: question generation
├── forward_links.py              ← Feature B: "Where This Leads" section builder
├── insight_store.py              ← Feature B: digest_insights.yaml (threaded insights)
├── blog_post_editor.py           ← Features A+C: blog post editing + deep-dive promotion
├── media_queue.py                ← Feature D: media queue + markdown embed
├── digest_config_TEMPLATE.yaml   ← annotated config template
├── tests/                        ← TDD test suite (102 tests)
│   ├── unit/
│   ├── integration/
│   └── regression/
└── .github/workflows/test.yml    ← CI (runs pytest on push + PR)
```

## New Features (v5)

### Review Addendum (Feature A, §2)
Human-in-the-loop review dialog — triggered via Telegram ("review today") or CLI (`--review`).

```bash
# Step 1: generate review questions
python3 session_digest.py --review 2026-04-23

# Step 2: provide numbered answers
python3 session_digest.py --review 2026-04-23 --answers '[1] completed vDEX bot; [4] monitor 24h'
```

Appends `## Review Addendum — reviewed-v1` to the blog post and sets `reviewed: true` in front matter.

### Where This Leads (Feature B, §3)
Trigger with "where this leads" in any session. Builds a `## Where This Leads` section with contextual links (GitHub issues/PRs/commits), threaded insights from `digest_insights.yaml`, and future anchors (TODO items + follow-ups).

Insights appearing in ≥3 digests are flagged `standalone_candidate` and prompted for deep-dive promotion.

### Deep-Dive Promotion (Feature C, §4)
Insights can be promoted to standalone blog posts. Front matter: `title`, `date`, `tags: [deep-dive, ...]`, `digest_sources: [...]`, `layout: post`.

### Media Queue (Feature D, §5.8)
Send images (PNG/JPG/WebP) or video (MP4/WebM) from Telegram with a caption. Files are committed to `assets/media/YYYY-MM-DD/` in the blog repo and embedded as markdown images in the post.

## License

MIT — see [BuildWithDreams](https://github.com/BuildWithDreams) organization.
