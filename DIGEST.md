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

### 📌 Tomorrow's Anchors
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
| Tomorrow's Anchors | TODO items, follow-up markers, deferred decisions | Extracted from session content; auto-generated checklist |

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
  status: active|resolved|promoted  # lifecycle stage
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
```

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
  max_anchors: 5                       # max items in Tomorrow's Anchors checklist
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

### 7.4 Deep-Dive Flow

```
"Tomorrow's Anchors" or "Threaded Insights" flagged after N references
        ↓
User approves promotion: "promote this thread"
        ↓
Synthesis pass: Venice collects all cross-references
        ↓
Standalone post generated and pushed
        ↓
Source digests updated with backlink
        ↓
Insight status: active → promoted
```

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
├── DIGEST.md                              ← new: feature spec (this document)
├── SKILL.md                               ← updated: document new features
├── README.md                              ← updated: add features to overview
├── session_digest.py                      ← modified: --review flag, "Where This Leads" builder
├── fetch_github_evidence.py               ← no change
├── digest_config_TEMPLATE.yaml            ← modified: add review + forward_links + deep_dive sections
└── scripts/
    ├── generate_review_questions.py      ← new: review dialog question generator
    ├── build_forward_links.py             ← new: "Where This Leads" section builder
    ├── synthesize_deep_dive.py            ← new: deep-dive post synthesizer
    └── digest_insights.yaml              ← new: cross-digest insight store (gitignored)
```

---

## 10. Open Questions for Feedback

Before implementation, these need answers:

1. **Delivery format for review questions** — Telegram is the primary channel. Should the dialog be:
   - (a) A single Telegram message with numbered questions, user replies with `[1] answer [2] answer...`
   - (b) One question per message, bot waits for each answer before sending next
   - (c) A mini-survey interface via Telegram inline buttons

2. **Review addendum email** — Should it be:
   - (a) A reply-thread email (keeps it grouped with original digest)
   - (b) A new top-level email with a `⚠️ Updated` prefix in the subject

3. **"Tomorrow's Anchors" format** — Should this be:
   - (a) A checklist (`- [ ]`) — actionable, scannable
   - (b) A plain list — simpler to generate
   - (c) A table with `Action | Owner | Deadline` — if multiple people are involved

4. **Auto-promotion of deep-dives** — Should the system:
   - (a) Only flag as `standalone-candidate`, never auto-promote (user must approve)
   - (b) Auto-promote after N references but allow undo
   - (c) Auto-promote silently (no friction, just a backlink added)

5. **Insight expiry** — Insights marked `active` that haven't been referenced in 14 days:
   - (a) Auto-archive (status: resolved, reason: stale)
   - (b) Surface as "this thread seems cold — close it?" in next review
   - (c) Keep alive indefinitely until manually closed
