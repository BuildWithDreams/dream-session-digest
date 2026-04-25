"""
Feature B — Insight Store (DIGEST.md §6)

Schema and CRUD for digest_insights.yaml — cross-digest threaded insight objects.

Lifecycle:
    active → resolved  (confirmed fixed, stale, or manually closed)
    active → promoted  (expanded to standalone deep-dive post)
    active → parked    (deferred by user; re-opens on next mention)
    parked → active    (referenced in future "where this leads" or review)
    resolved → active  (re-opened by user)

Insight object schema (§6):
    slug:
        text: str
        type: pattern | weak-signal | cross-thread | decision
        first_seen: YYYY-MM-DD
        last_updated: YYYY-MM-DD
        status: active | resolved | promoted | parked
        reason: str | null        # set when status=resolved
        links: list[str]
        promoted_to: str | null  # set when status=promoted
        digest_references: list[YYYY-MM-DD]
        body: str

Usage:
    store = InsightStore()                        # uses default path
    store = InsightStore("/path/to/digest_insights.yaml")
    store.add("vARRR bridge instability", insight_type="pattern", first_seen="2026-04-23")
    store.add_digest_reference(slug, "2026-04-25")
    store.promote(slug, promoted_to="Deep Dive Title")
    insights = store.list_insights()
"""
import os
import re
import yaml
from datetime import datetime, timezone
from typing import Optional

# ── Schema constants ──────────────────────────────────────────────────────────

VALID_INSIGHT_TYPES = {"pattern", "weak-signal", "cross-thread", "decision"}
VALID_STATUSES = {"active", "resolved", "promoted", "parked"}
CROSS_THREAD_THRESHOLD = 3  # references needed to become standalone-candidate
INSIGHTS_FILE = os.path.expanduser("~/.hermes/scripts/digest_insights.yaml")


class InvalidInsightTypeError(ValueError):
    """Raised when insight_type is not one of the valid types."""


class InsightNotFoundError(KeyError):
    """Raised when attempting to operate on a non-existent insight slug."""


def _slug_from_text(text: str, date_str: str) -> str:
    """Generate a URL-safe slug from insight text + date."""
    # Take first 6 significant words, lowercase, hyphenated
    words = re.findall(r"[\w]+", text.lower())
    significant = [w for w in words if len(w) > 3][:6]
    base = "-".join(significant)
    date_part = date_str.replace("-", "")
    return f"{base}-{date_part}"


def _timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── InsightStore ──────────────────────────────────────────────────────────────

class InsightStore:
    """
    Manages digest_insights.yaml — reads, writes, and provides CRUD operations.
    """

    def __init__(self, insights_file: str | None = None):
        self.path = insights_file or INSIGHTS_FILE
        self._insights: dict = {}
        self._load()

    def _load(self) -> None:
        """Load existing insights from disk. Silently ignores missing file."""
        try:
            with open(self.path) as f:
                data = yaml.safe_load(f) or {}
                self._insights = {k: v for k, v in data.items() if isinstance(v, dict)}
        except (FileNotFoundError, yaml.YAMLError):
            self._insights = {}

    def save(self) -> None:
        """Write current insights to disk."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            yaml.safe_dump(
                self._insights,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def add(
        self,
        text: str,
        insight_type: str,
        first_seen: str,
        links: list | None = None,
        body: str = "",
    ) -> str:
        """
        Add a new insight. Returns the generated slug.
        Raises InvalidInsightTypeError if type is not valid.
        """
        if insight_type not in VALID_INSIGHT_TYPES:
            raise InvalidInsightTypeError(
                f"insight_type must be one of {VALID_INSIGHT_TYPES}, got '{insight_type}'"
            )

        slug = _slug_from_text(text, first_seen)
        self._insights[slug] = {
            "text": text,
            "type": insight_type,
            "first_seen": first_seen,
            "last_updated": _timestamp_now(),
            "status": "active",
            "reason": None,
            "links": links or [],
            "promoted_to": None,
            "digest_references": [first_seen],
            "body": body or text,
        }
        return slug

    def get(self, slug: str) -> dict:
        """Return the insight dict for a slug. Raises InsightNotFoundError if missing."""
        if slug not in self._insights:
            raise InsightNotFoundError(f"Insight not found: {slug}")
        return self._insights[slug]

    def list_insights(self) -> dict:
        """Return all insights as a dict {slug: insight_dict}."""
        return dict(self._insights)

    def delete(self, slug: str) -> None:
        """Remove an insight."""
        if slug in self._insights:
            del self._insights[slug]

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def resolve(self, slug: str, reason: str) -> None:
        """Mark an insight as resolved with a reason."""
        self.get(slug)  # raises if missing
        self._insights[slug]["status"] = "resolved"
        self._insights[slug]["reason"] = reason
        self._insights[slug]["last_updated"] = _timestamp_now()
        # resolved insights are not standalone-candidates
        self._insights[slug].pop("standalone_candidate", None)

    def promote(self, slug: str, promoted_to: str) -> None:
        """Mark an insight as promoted to a deep-dive post."""
        self.get(slug)
        self._insights[slug]["status"] = "promoted"
        self._insights[slug]["promoted_to"] = promoted_to
        self._insights[slug]["last_updated"] = _timestamp_now()
        self._insights[slug].pop("standalone_candidate", None)

    def park(self, slug: str) -> None:
        """Park an insight (deferred)."""
        self.get(slug)
        self._insights[slug]["status"] = "parked"
        self._insights[slug]["last_updated"] = _timestamp_now()

    def reopen(self, slug: str) -> None:
        """Re-open a parked or resolved insight."""
        insight = self.get(slug)
        insight["status"] = "active"
        insight["last_updated"] = _timestamp_now()
        insight.pop("reason", None)

    # ── Digest references ────────────────────────────────────────────────────

    def add_digest_reference(self, slug: str, date_str: str) -> None:
        """
        Add a digest date to an insight's reference list.
        Also updates last_updated and re-evaluates standalone_candidate status.
        """
        insight = self.get(slug)
        if date_str not in insight["digest_references"]:
            insight["digest_references"].append(date_str)
        insight["last_updated"] = _timestamp_now()
        self._update_standalone_candidate(slug)

    def _update_standalone_candidate(self, slug: str) -> None:
        """Set standalone_candidate=True when digest reference count >= threshold."""
        insight = self._insights[slug]
        if insight["status"] != "active":
            return
        threshold = CROSS_THREAD_THRESHOLD
        # Only count *additional* references beyond the initial first_seen
        additional_refs = len(insight["digest_references"]) - 1
        if additional_refs >= threshold:
            insight["standalone_candidate"] = True
        else:
            insight.pop("standalone_candidate", None)

    # ── Query helpers ─────────────────────────────────────────────────────────

    def get_standalone_candidates(self) -> dict:
        """Return all active insights flagged as standalone-candidate."""
        return {
            slug: insight
            for slug, insight in self._insights.items()
            if insight.get("standalone_candidate") is True
        }

    def get_active_for_date(self, date_str: str) -> dict:
        """Return all insights with digest_references containing date_str."""
        return {
            slug: insight
            for slug, insight in self._insights.items()
            if date_str in insight.get("digest_references", [])
        }

    def get_stale(self, days: int = 14) -> dict:
        """Return active insights with no references in the last `days` days."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        stale = {}
        for slug, insight in self._insights.items():
            if insight["status"] != "active":
                continue
            try:
                last_upd = datetime.fromisoformat(insight["last_updated"].replace("Z", "+00:00"))
                if last_upd.timestamp() < cutoff:
                    stale[slug] = insight
            except Exception:
                pass
        return stale
