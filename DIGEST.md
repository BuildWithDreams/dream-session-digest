# Feature Spec: Digest Review & Forward Links System

**Status:** Draft — for feedback
**Spec version:** 1.0
**Date:** 2026-04-25
**Author:** Captain Mylo / BuildWithDreams
**Related:** [Issue #2 — Create a feedback mechanism](https://github.com/BuildWithDreams/dream-session-digest/issues/2)

---

## 1. Problem Statement

Two related gaps exist in the current digest system:

1. **Incomplete captures** — The nightly digest sometimes misses vital work that emerged late in a session or wasn't part of the main thread. The day's most important outcome may be buried or absent.

2. **No forward-looking structure** — Digests are siloed by day. There's no native way to link across days, surface patterns, record external context, or flag things that matter for tomorrow.

The fix for (1) is a **review & refine** workflow. The fix for (2) is a **"Where This Leads"** section embedded in every digest — and a class of **standalone deep-dive posts** that span multiple days.

---

## 2. Feature A — Review & Refine (Feedback Mechanism)

### 2.1 Trigger

The user (or a future publishing team member) flags that a digest needs review. This is a **one-time, on-demand operation** — not a nightly step.

**Critically: a review trigger always includes "where this leads".** The two are unified by design — when something was missed, the reason it matters and what needs to happen next are usually discovered together. The review dialog covers both: it corrects the record *and* captures the forward context in one pass.

**Trigger methods (Phase 1):**
- A Telegram message: `"review digest for [date]"` or `"review today"`
- A CLI flag: `session_digest.py --review 2026-04-23`
- A cron job watching for a `review_requested` marker file

**Trigger methods (Phase 2, future):**
- Inline in the blog post (e.g. a "Request Review" button that opens a GitHub issue)
- Automated: if a session runs past 22:00, auto-flag for review

### 2.2 Review Dialog

When triggered, the system generates a short **review dialog** — 3–5 targeted questions. The user answers via Telegram (or email reply in Phase 2). Answers are session messages like any other.

**Standard review questions:**

| # | Question | Purpose |
|---|----------|---------|
| 1 | "What's the single most important thing that happened today that isn't in the summary?" | Retrospective — fills the biggest gap |
| 2 | "Was anything started but left unfinished — does it matter?" | Retrospective — completeness check |
| 3 | "Was there anything unexpected — good or bad?" | Retrospective — surfaces surprises |
| 4 | "Any open threads, follow-ups, or decisions deferred — and what needs to happen next?" | **Forward-looking — where this leads** |
| 5 | "Does the summary make sense to someone who wasn't in the room?" | Retrospective — sanity check |

Q4 is the **"where this leads"** question embedded in the review dialog. When you answer it, you're doing double duty: correcting the record and threading forward in one go. No separate trigger needed.

**Question generation rules:**
- Always ask Q1 and Q4 minimum (the most critical gaps + forward context)
- Q2, Q3, Q5 are asked conditionally based on session content signals
- Questions are numbered (`[1]`, `[2]`) so answers can be tied to questions compactly
- Questions are short — one focused sentence each

### 2.3 Digest Refinement

After answers are collected, a **refinement pass** is run:

1. The original digest is appended to the session context
2. A targeted Venice prompt incorporates each Q&A, producing an **addendum block**
3. The addendum is appended to the blog post with a `reviewed-v1` marker
4. The marker ensures the post is re-published (new commit) even if the date is stale
5. A one-time token budget increase is applied for this pass (configurable, e.g. 2× normal)

### 2.4 Review Addendum Format

```markdown
---

## Review Addendum — reviewed-v1

**Review triggered:** 2026-04-23 21:14 UTC

**[1]** What's the most important thing missing?

> The vDEX liquidity bot was actually completed and deployed — it's not in the
> main summary. The final push was at 20:47. Here's the commit:
> [a1b2c3d](https://github.com/BuildWithDreams/vdex-liquidity-bot/commit/a1b2c3d)

**[4]** Open threads / follow-ups

> - Need to monitor the bot for 24h before declaring it stable
> - vARRR bridge audit scheduled for tomorrow

*This addendum was generated after user review and appended to the original digest.*
```

### 2.5 Re-publishing

- The blog post is updated with the addendum and pushed as a new commit
- Email: if the original digest was emailed, a **reply-thread email** is sent (not a new top-level email) noting the addendum
- The `reviewed-v1` tag appears in the post header

---

## 3. Feature B — "Where This Leads" Section

### 3.1 Overview

A section that is **generated on-demand** — triggered only when you explicitly ask for it in the context of current work. When not triggered, it does not appear in the digest at all.

**Trigger:**
- You say: `"where this leads"` or `"log this as a thread"` or similar during a session
- The section is generated as part of that session's digest, not the previous night's

This keeps the output clean and ensures every "Where This Leads" entry is intentional, not boilerplate.

```markdown
## Where This Leads

### → Contextual Links
- [repo-name#issue-n](url) — brief description of why it matters today
- [PR #n: Title](url) — mentioned in context, not resolved
- [External: Article Title](url) — referenced during the session

### 💡 Threaded Insights
- **Pattern noticed:** [text] *(first noticed: Day N)*
- **Weak signal:** [text] — not actionable yet, worth tracking
- **Cross-thread:** [text] → relates to Day N

### 📌 Future Anchors
- [ ] Monitor the vDEX bot for 24h stability
- [ ] Review vARRR bridge audit findings
- [ ] Follow up: why did the build take 3× longer than expected?
```

### 3.2 Data Sources

Each sub-section pulls from different signals. The section is only built if the user triggered it in the session:

| Sub-section | Source | Method |
|-------------|--------|--------|
| Contextual Links | Repos, issues, PRs mentioned in sessions | Extract URLs and map to brief descriptions |
| Threaded Insights | Pattern across recent digests; weak signals from current session | Venice-generated; flagged as `insight` in post-processing |
| Future Anchors | TODO items, follow-up markers, deferred decisions | Extracted from session content; auto-generated checklist |

### 3.3 Cross-Digest Threads

When an insight or open thread is first flagged, it gets tagged with the originating digest date. Future digests reference it:

```
💡 **Cross-thread:** vARRR bridge instability — flagged [Day 14](#day14) —
today we saw it resolved after the upgrade. See [Day 14 thread →](#day14).
```

This creates a **wiki-style thread** between related digests without requiring manual linking.

### 3.4 Digest Types Summary

| Digest Type | Trigger | Output |
|-------------|---------|--------|
| `standard` | Nightly cron | Blog post + email |
| `standard` + `where-this-leads` | Nightly cron + user triggered `"where this leads"` in-session | Blog post + email + Where This Leads section |
| `review` | On-demand (user request) | Addendum block + reply email |
| `deep-dive` | Auto (insight flagged "standalone") or manual | Standalone blog post |

---

## 4. Feature C — Standalone Deep-Dive Posts

### 4.1 When to Promote

An insight is **promoted** to a standalone post when:
- It is referenced by 3+ future digests ("as mentioned in [Day N]...")
- It represents a decision with a reasoned conclusion worth preserving
- A pattern spans 5+ days and needs synthesis
- The user explicitly requests it

### 4.2 Promotion Workflow

1. **Detection** — Venice or user flags an insight as `standalone-candidate`
2. **Synthesis** — A Venice prompt collects all cross-references from session evidence and prior digests, then writes a coherent standalone post
3. **Publication** — The post is pushed to the blog with a tag `deep-dive` and front matter linking to source digests
4. **Backlink** — All contributing digests get a note: *"Expanded: [Post Title →](#deep-dive-link)"*

### 4.3 Deep-Dive Post Front Matter

```yaml
---
title: "The vARRR Bridge Audit: A 6-Day Thread"
date: 2026-04-29
tags: [deep-dive, vARRR, bridge, audit]
digest_sources: [2026-04-23, 2026-04-24, 2026-04-25, 2026-04-26]
layout: post
---
```

---

## 5. Schema: Threaded Insight Object

Stored in a new file: `~/.hermes/scripts/digest_insights.yaml`

```yaml
# One entry per insight, keyed by a generated slug
varrr-bridge-audit-2026-04-23:
  text: "vARRR bridge was exhibiting intermittent failures under load"
  type: pattern|weak-signal|cross-thread|decision  # insight category
  first_seen: 2026-04-23
  last_updated: 2026-04-26
  status: active|resolved|promoted|parked  # lifecycle stage
  reason: null  # set when status=resolved: "stale", "confirmed-fixed", "manually-closed"
  links:
    - https://github.com/BuildWithDreams/varrr-bridge/issues/47
    - https://github.com/BuildWithDreams/varrr-bridge/commit/a1b2c3d
  promoted_to: null  # set if status=promoted, points to post title
  digest_references:
    - 2026-04-23
    - 2026-04-25
    - 2026-04-26
  body: |
    First noticed during the stress test on Day 23. Persisted through
    Days 24-25. Resolved after the configuration patch on Day 26.
```

**Lifecycle:**
```
active → resolved  (confirmed fixed or no longer relevant)
active → promoted  (expanded to standalone deep-dive post)
active → parked    (deferred by user; re-opens on next mention)
resolved → active  (re-opened by user or referenced again after archive)
parked → active   (referenced in a future "where this leads" or review dialog)
```

**Auto-archive:** Insights in `active` status with no digest references for 14 days are auto-archived (`status: resolved, reason: stale`). Archived insights remain readable but are deprioritized. They can be manually re-opened at any time by referencing them in a review or "where this leads" dialog.

---

## 6. Config: New Fields

Added to `digest_config_TEMPLATE.yaml`:

```yaml
# --- Section: Review & Refine ---

review:
  enabled: true
  token_budget_multiplier: 2.0   # one-time multiplier for refinement pass
  auto_trigger_after_hour: 22    # Phase 2: auto-flag sessions running past this hour (UTC)

# --- Section: Where This Leads ---
# NOTE: This section is only generated when YOU explicitly ask for it
# in-session (e.g. "where this leads"). The enabled flag here is for
# adopting orgs who want to disable the feature entirely.

forward_links:
  enabled: true
  trigger_phrase: "where this leads"   # phrase to detect in session for triggering
  max_contextual_links: 5             # cap per digest to keep section scannable
  max_anchors: 5                       # max items in Future Anchors checklist
  cross_thread_threshold: 3           # flag as standalone-candidate after N references

deep_dive:
  auto_promote: false            # Phase 2: auto-promote when threshold reached
  min_days_span: 3               # minimum days spanned to qualify as deep-dive
```

---

## 7. Workflow: Publishing Team Process

### 7.1 Standard Nightly Flow (unchanged)

```
4am cron → session_digest.py → email + blog post (standard)
```

**"Where This Leads"** is not automatic — it is triggered only when you explicitly
request it during a session (e.g. `"where this leads"`). When triggered, it is
built from that session's content and appended to the digest at the next run.

### 7.2 Where This Leads Flow

```
You: "where this leads" (during a session)
        ↓
Session tagged with where-this-leads marker
        ↓
Next nightly digest picks up the marker
        ↓
"Where This Leads" section built from that session's URLs, todos, follow-ups
        ↓
Section appended → blog post updated → pushed
        ↓
Insights written to digest_insights.yaml for cross-digest threading
```

### 7.3 Review Flow (Unified — includes "where this leads")

```
User: "review digest for 2026-04-23" (Telegram / CLI)
        ↓
Review dialog opened — questions 1–5 including Q4 (where this leads)
        ↓
User answers all questions
        ↓
Refinement pass: Venice generates addendum incorporating Q1–Q3 corrections
                  AND Q4 forward context
        ↓
Addendum appended → blog post updated → new commit pushed
        ↓
Reply-thread email sent with addendum
        ↓
Digest tagged: reviewed-v1
        ↓
Q4 answers → insights written to digest_insights.yaml
          → cross-digest threads updated
```

### 7.4 Deep-Dive Flow (Cron-Triggered Questionnaire)

Deep-dive promotion is driven by a **questionnaire triggered from the nightly cron**, not a manual request. The flow handles three states:

**Trigger:** Cron runs at 4am and checks `digest_insights.yaml` for insights that have reached `cross_thread_threshold` (default: 3 digest references) or have `status: active` and are past their stale date.

```
Cron (4am): digest_insights.yaml scan
        ↓
Insight flagged as standalone-candidate (≥N references OR user-tagged)
        ↓
Questionnaire sent to user: "This thread has N mentions — promote to deep-dive?"
        ↓
User replies: "yes" / "defer" / "park until next trigger"
        │
        ├── "yes" → Synthesis pass → standalone post generated → push
        │         → Source digests get backlink
        │         → Insight status: active → promoted
        │
        ├── "defer" → Remind tonight (next cron cycle)
        │
        └── "park" → Status: active → parked
                    → Re-opens when same insight is mentioned again
                    → ("this relates to the [thread name] we parked")
```

**Parking and re-opening:**
- A parked insight stays in `digest_insights.yaml` with `status: parked`
- Any future `"where this leads"` or review dialog that references the insight by slug or topic reopens it: `parked → active`
- The re-opened insight resumes accumulating references toward promotion

---

## 8. Acceptance Criteria

| ID | Criterion | Testable By |
|----|-----------|-------------|
| AC1 | Review dialog generates exactly the questions defined in §2.2 | Manual: trigger review, inspect questions |
| AC2 | Review addendum is appended to the correct date's blog post | Manual: trigger review, check blog post commit |
| AC3 | Reviewed posts show `reviewed-v1` marker in front matter | Manual: inspect blog post |
| AC4 | "Where This Leads" appears in every standard digest output | Automated: parse digest output |
| AC5 | Contextual links are extracted from session URLs | Manual: compare session URLs to digest links |
| AC6 | Insights with ≥3 digest references are flagged as `standalone-candidate` | Automated: parse `digest_insights.yaml` |
| AC7 | Deep-dive post front matter contains `digest_sources` list | Manual: inspect promoted post |
| AC8 | Adopting org can enable/disable each feature independently via `digest_config.yaml` | Manual: toggle flags, run digest |
| AC9 | New fields in config are absent → feature disabled (graceful fallback) | Automated: remove fields, run digest |
| AC10 | Review refinement uses increased token budget (logged) | Manual: inspect Venice API call logs |

---

## 9. File Changes

```
dream-session-digest/
├── DIGEST.md                              ← this document
├── SKILL.md                               ← updated: document new features
├── README.md                              ← updated: add features to overview
├── session_digest.py                      ← modified: --review flag, "Where This Leads" builder
├── fetch_github_evidence.py               ← no change
├── digest_config_TEMPLATE.yaml            ← modified: add review + forward_links + deep_dive sections
├── .github/
│   └── workflows/
│       └── test.yml                       ← new: CI test suite
└── tests/
    ├── conftest.py                       ← new: shared fixtures
    ├── unit/
    │   ├── test_review_questions.py     ← new
    │   ├── test_forward_links.py          ← new
    │   ├── test_insight_store.py         ← new
    │   └── test_config_parsing.py        ← new
    ├── integration/
    │   ├── test_digest_pipeline.py        ← new
    │   ├── test_review_addendum.py        ← new
    │   └── test_where_this_leads.py      ← new
    └── regression/
        └── test_existing_digest_invariants.py  ← new
```

---

## 11. TDD — Test-Driven Development

The system is complex enough that changes require a regression harness. TDD is mandatory for this project, not optional.

### 11.1 Why TDD Here

Three reasons this system specifically needs it:

1. **Silent regressions** — The digest pipeline has many moving parts. A change to the clustering logic can silently change what summaries look like. A change to the email builder can silently drop the GitHub Activity section.
2. **Non-deterministic output** — Venice generates different summaries on the same input. Tests can't assert on exact LLM output, but can assert on *structure, presence, and invariants*.
3. **Multi-format sessions** — The system handles both JSONL (current) and JSON (legacy) session formats. Changing one parser shouldn't break the other.

### 11.2 Test Categories

| Category | What it tests | Example |
|----------|--------------|---------|
| **Unit** | Pure functions in isolation | `generate_review_questions()` returns correct questions for a given config |
| **Unit** | Config parsing and fallback | Missing config fields fall back to defaults |
| **Unit** | Session format detection | JSONL vs JSON sessions are parsed correctly |
| **Integration** | Full pipeline with mocked Venice | Session JSONL → blog post YAML has correct front matter |
| **Integration** | Review addendum flow | Questions + answers → addendum block has correct format |
| **Regression** | Existing behavior unchanged | Standard digest output contains GitHub Activity section |
| **Regression** | Email content invariants | Email body contains `SESSION DIGEST —`, cluster count, GitHub links |

### 11.3 Test Structure

```
tests/
├── conftest.py              ← shared fixtures: sample sessions, config, mock Venice
├── unit/
│   ├── test_review_questions.py
│   ├── test_forward_links.py
│   ├── test_insight_store.py
│   └── test_config_parsing.py
├── integration/
│   ├── test_digest_pipeline.py
│   ├── test_review_addendum.py
│   └── test_where_this_leads.py
└── regression/
    └── test_existing_digest_invariants.py
```

### 11.4 Shared Fixtures (`conftest.py`)

```python
# Sample session files — real format, synthetic content
@pytest.fixture
def sample_session_jsonl():
    """Current format: one JSON object per line"""
    return ["~/.hermes/sessions/20260425_080000_abc123.jsonl"]

@pytest.fixture
def sample_session_legacy_json():
    """Legacy format: JSON with messages array"""
    return ["~/.hermes/sessions/session_20260315_080000_def456.json"]

@pytest.fixture
def mock_venice(mocker):
    """Mocks Venice API — returns stable, structured responses"""
    return mocker.patch('session_digest.venice_generate', return_value="...")

@pytest.fixture
def temp_digest_config(tmp_path):
    """Minimal config for testing — no real credentials needed"""
    config = tmp_path / "digest_config.yaml"
    config.write_text("github:\n  org: test-org\n  blog_repo: test-blog\n  tracked_repos: []\nemail:\n  to: [test@example.com]\nreview:\n  enabled: true\nforward_links:\n  enabled: true\n")
    return config
```

### 11.5 Regression Tests — Non-Negotiable

These tests must pass on every commit. They protect the existing contracts:

```python
def test_digest_output_contains_github_activity(session, mock_venice, capsys):
    """Every digest must include a GitHub Activity section."""
    result = run_digest(session)
    assert "## GitHub Activity" in result.blog_post_body

def test_email_contains_session_count(session, mock_venice):
    """Email header must state number of sessions and clusters."""
    result = run_digest(session)
    assert re.search(r"\d+ cluster\(s\) from \d+ session\(s\)", result.email_body)

def test_review_addendum_has_reviewed_v1_marker(addendum_output):
    """Reviewed posts must carry the reviewed-v1 tag in front matter."""
    assert "reviewed-v1" in addendum_output.front_matter

def test_where_this_leads_never_appears_without_trigger(session_no_trigger, mock_venice):
    """Where This Leads section must NOT appear when not triggered."""
    result = run_digest(session_no_trigger)
    assert "## Where This Leads" not in result.blog_post_body

def test_jsonl_and_json_sessions_both_parsed(sample_session_jsonl, sample_session_legacy_json):
    """Both session formats must produce a valid digest without crashing."""
    for session in [sample_session_jsonl, sample_session_legacy_json]:
        result = run_digest(session)
        assert result.cluster_count >= 1
```

### 11.6 TDD Workflow

**For every feature or fix:**

```
1. Write the failing test
   $ touch tests/unit/test_review_questions.py
   $ pytest tests/unit/test_review_questions.py  # must FAIL

2. Implement to make it pass
   $ vim session_digest.py  # or scripts/generate_review_questions.py
   $ pytest tests/unit/test_review_questions.py  # must PASS

3. Run full suite — no regressions
   $ pytest tests/ -v

4. Commit with test coverage
   $ git add tests/ session_digest.py
   $ git commit -m "feat: review question generation [tests pass]"
```

**Before any PR merge:** full suite must pass, including regression suite.

### 11.7 CI — GitHub Actions

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install pytest pytest-mock pyyaml
      - run: pytest tests/ -v --tb=short

  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install pytest pytest-mock pyyaml
      - run: pytest tests/regression/ -v
      - name: Re-run digest on last 7 days (smoke test)
        run: python3 session_digest.py --dry-run --date-range $(date -d '7 days ago' +%Y-%m-%d) $(date +%Y-%m-%d)
```

### 11.8 What Tests Cannot Cover

- **Exact LLM output** — Venice summaries vary. Tests assert on *structure*, not copy.
- **Network calls** — mocked in unit/integration; real API tested in a separate manual smoke test
- **Blog publishing** — the git push step is mocked; actual push tested in a manual post-deploy check

---

## 12. Open Questions for Feedback

Before implementation, these need answers:

~~1. **Delivery format for review questions**~~ ✅ DECIDED — (a) — single Telegram message with numbered answers

~~2. **Review addendum email**~~ ✅ DECIDED — reply-thread email

~~3. **"Future Anchors" format**~~ ✅ DECIDED — renamed "Future Anchors", checklist format (`- [ ]`), lives under "Where This Leads"

~~4. **Auto-promotion of deep-dives**~~ ✅ DECIDED — cron-triggered questionnaire, can be deferred or parked until next mention/trigger

~~5. **Insight expiry**~~ ✅ DECIDED — keep open indefinitely; auto-archive after 14 days with no mention, but re-openable
