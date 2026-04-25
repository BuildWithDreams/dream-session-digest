"""
Feature A — Review Question Generation (DIGEST.md §2.2)

Generates 3–5 targeted review questions for a given session.
Always includes Q1 (most important gap) and Q4 (forward-looking).
Conditionally includes Q2 (unfinished work), Q3 (surprises), Q5 (clarity).

Questions are numbered so answers can be tied back compactly:
    "[1] What's the most important thing missing?"
    "[4] Open threads / follow-ups — what needs to happen next?"

Usage:
    questions = generate_review_questions(session_text="...", session_files=[...])
"""
import os
import re

# ── Config ─────────────────────────────────────────────────────────────────────

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
    """Navigate nested dict with graceful fallback."""
    val = _config
    for k in keys:
        try:
            val = val[k]
        except (TypeError, KeyError):
            return default
    return val if val is not None else default


# ── Trigger signals ──────────────────────────────────────────────────────────

UNFINISHED_SIGNALS = [
    "start", "begun", "still", "left", "not done", "incomplete",
    "pending", "deferred", "postponed", "wip", "work in progress",
    "to do", "todo", "backlog",
]

SURPRISE_SIGNALS = [
    "unexpected", "surprise", "surprised", "odd", "weird", "strange",
    "didn't expect", "out of nowhere", "came out of", "broke",
    "unexpectedly", "mistake", "bug", "issue", "problem",
]

CLARITY_LOW_SIGNALS = [
    "confusing", "unclear", "what was that", "don't understand",
    "didn't follow", "hard to explain", "complex", "complicated",
]


def _contains_signal(text: str, signals: list) -> bool:
    """Check if text contains any of the trigger signals (case-insensitive)."""
    text_lower = text.lower()
    return any(sig in text_lower for sig in signals)


def _word_count(text: str) -> int:
    """Approximate word count."""
    return len(text.split())


# ── Core question definitions ─────────────────────────────────────────────────

Q1 = "[1] What's the single most important thing that happened today that isn't in the summary?"

Q2 = "[2] Was anything started but left unfinished — does it matter?"

Q3 = "[3] Was there anything unexpected — good or bad?"

Q4 = "[4] Any open threads, follow-ups, or decisions deferred — and what needs to happen next?"

Q5 = "[5] Does the summary make sense to someone who wasn't in the room?"


# ── Question generation ───────────────────────────────────────────────────────

def generate_review_questions(
    session_text: str,
    session_files: list,
    date_str: str | None = None,
) -> list[str]:
    """
    Generate review questions for a given session.

    Rules (§2.2):
    - Always: Q1 + Q4 (minimum)
    - Q2: if session_text contains unfinished-work signals
    - Q3: if session_text contains surprise/unexpected signals
    - Q5: if session is very short OR low-clarity signals present

    Args:
        session_text: concatenated text from all session files
        session_files: list of session file paths (for future extension)
        date_str: optional date string for date-aware questions

    Returns:
        list[str]: numbered question strings, each under 200 chars
    """
    questions = []

    # Always Q1 and Q4 (the two most critical)
    questions.append(Q1)
    questions.append(Q4)

    # Conditionally Q2
    if _contains_signal(session_text, UNFINISHED_SIGNALS):
        questions.append(Q2)

    # Conditionally Q3
    if _contains_signal(session_text, SURPRISE_SIGNALS):
        questions.append(Q3)

    # Conditionally Q5 (low clarity)
    if _word_count(session_text) < 100 or _contains_signal(session_text, CLARITY_LOW_SIGNALS):
        questions.append(Q5)

    # Ensure no duplicates and questions stay short
    seen = set()
    deduped = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            deduped.append(q.strip())

    return deduped
