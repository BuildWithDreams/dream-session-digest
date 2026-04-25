"""
Feature A — Review Addendum (DIGEST.md §2)

Review dialog generation and addendum block builder.

§2.1 Trigger:
    - Telegram: "review digest for [date]" or "review today"
    - CLI: --review flag
    - Marker file: ~/.hermes/sessions/review_requested

§2.2 Review dialog: questions from review_questions.generate_review_questions()
§2.3 Refinement pass: builds addendum block from Q&A pairs
§2.4 Addendum format: "## Review Addendum — reviewed-v1"
§2.5 Re-publishing: appends addendum to blog post, sets reviewed-v1 marker

Usage:
    is_review_trigger("review today")  # True/False
    addendum = build_review_addendum("2026-04-23", qa_pairs={...}, original_summary="...")
"""
import os
import re
from datetime import datetime, timezone

# ── Trigger detection ──────────────────────────────────────────────────────────

REVIEW_TRIGGER_PATTERNS = [
    re.compile(r"^review\s+(today|digest)", re.IGNORECASE),
    re.compile(r"^review\s+(digest\s+for\s+\d{4}-\d{2}-\d{2})", re.IGNORECASE),
    re.compile(r"^(review|review\s+digest)\s+\d{4}-\d{2}-\d{2}", re.IGNORECASE),
]
REVIEW_MARKER_FILE = os.path.expanduser("~/.hermes/sessions/review_requested")


def is_review_trigger(
    message: str = "",
    marker_file: str | None = None,
) -> bool:
    """
    Returns True if the message or marker file signals a review trigger.

    §2.1 — trigger methods:
    - Telegram: "review digest for [date]" or "review today"
    - Marker file: review_requested in sessions dir
    """
    if marker_file is None:
        marker_file = REVIEW_MARKER_FILE

    # Check marker file
    if os.path.isfile(marker_file):
        return True

    # Check message patterns
    msg = message.strip()
    if not msg:
        return False

    return any(pat.search(msg) for pat in REVIEW_TRIGGER_PATTERNS)


def extract_review_date(message: str) -> str | None:
    """
    Extract the date from a review trigger message.
    Returns YYYY-MM-DD or None if no date found.
    """
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", message)
    if m:
        return m.group(1)
    if re.search(r"\breview\s+today\b", message, re.IGNORECASE):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return None


# ── Addendum block builder ─────────────────────────────────────────────────────

def build_review_addendum(
    date_str: str,
    qa_pairs: dict[str, str],
    original_summary: str = "",
) -> str:
    """
    Build a review addendum block from Q&A pairs.

    §2.4 format:
        ## Review Addendum — reviewed-v1

        **Review triggered:** 2026-04-23 21:14 UTC

        **[1]** What's the most important thing missing?
        > Answer text here.

        **[4]** Open threads / follow-ups
        > Answer text here.
    """
    timestamp = datetime.now(timezone.utc).strftime("%H:%M UTC")

    lines = [
        "---",
        "",
        "## Review Addendum — reviewed-v1",
        "",
        f"**Review triggered:** {date_str} {timestamp}",
        "",
    ]

    # Add each Q&A
    for q_num in sorted(qa_pairs.keys(), key=lambda x: int(x.strip("[]"))):
        answer = qa_pairs[q_num].strip()
        if answer:
            lines.append(f"**{q_num}** {answer}")
            lines.append("")
        lines.append("")

    lines.extend([
        "*This addendum was generated after user review and appended to the original digest.*",
    ])

    return "\n".join(lines)


# ── Q&A parser ─────────────────────────────────────────────────────────────────

def parse_review_answers(
    answers_text: str,
) -> dict[str, str]:
    """
    Parse numbered answers from a Telegram/review response.

    Input:
        "[1] The vDEX bot was completed at 20:47.\n[4] Monitor for 24h."
    Output:
        {"[1]": "The vDEX bot was completed at 20:47.", "[4]": "Monitor for 24h."}

    Answers can be:
    - Prefixed with [1], [2], etc.
    - Separated by newlines
    - Free-form text after the number
    """
    qa_pairs = {}
    # Split by numbered markers
    parts = re.split(r"(?=\[)\[([1-9])\]", answers_text)
    # parts[0] may be empty; subsequent pairs: [num, text]
    for i in range(1, len(parts), 2):
        num = parts[i]
        text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if text:
            qa_pairs[f"[{num}]"] = text
    return qa_pairs


# ── Deep-dive questionnaire ─────────────────────────────────────────────────────

DEEP_DIVE_QUESTIONNAIRE = """
**Insight thread promotion check**

This thread has {n} digest references and is flagged as a standalone-candidate.

Promote to a deep-dive post?

Reply: **yes** / **defer** / **park**
"""


def build_deep_dive_questionnaire(insight: dict, n_references: int) -> str:
    """Build the questionnaire sent to the user for deep-dive promotion."""
    return DEEP_DIVE_QUESTIONNAIRE.format(n=n_references)
