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
├── session_digest.py             ← main digest script
├── fetch_github_evidence.py       ← GitHub evidence scanner
├── digest_config_TEMPLATE.yaml   ← annotated config template
└── .gitignore
```

## License

MIT — see [BuildWithDreams](https://github.com/BuildWithDreams) organization.
