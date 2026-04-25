"""
Unit tests: Insight Store (Feature B, §6 — digest_insights.yaml schema + CRUD)

Tests AC6: Insights with >=3 digest references are flagged standalone-candidate
"""
import os
import pytest


class TestInsightSchema:
    """§6 — Threaded Insight Object schema validation."""

    def test_insight_requires_slug(self, insights_store_path):
        """Each insight is keyed by a generated slug."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add(
            text="vARRR bridge was exhibiting intermittent failures under load",
            insight_type="pattern",
            first_seen="2026-04-23",
        )
        insights = store.list_insights()
        assert len(insights) == 1
        slug = list(insights.keys())[0]
        assert isinstance(slug, str)
        assert len(slug) > 0

    def test_insight_has_required_fields(self, insights_store_path):
        """Insight object contains all required schema fields."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add(
            text="vARRR bridge was exhibiting intermittent failures",
            insight_type="pattern",
            first_seen="2026-04-23",
        )
        insights = store.list_insights()
        insight = list(insights.values())[0]
        assert "text" in insight
        assert "type" in insight
        assert "first_seen" in insight
        assert "last_updated" in insight
        assert "status" in insight
        assert "links" in insight
        assert "digest_references" in insight
        assert "body" in insight

    def test_insight_type_enum(self, insights_store_path):
        """insight_type must be one of: pattern, weak-signal, cross-thread, decision."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore, InvalidInsightTypeError
        store = InsightStore(insights_store_path)
        with pytest.raises(InvalidInsightTypeError):
            store.add(
                text="some insight",
                insight_type="invalid_type",
                first_seen="2026-04-23",
            )

    def test_status_enum(self, insights_store_path):
        """status must be one of: active, resolved, promoted, parked."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test insight", insight_type="pattern", first_seen="2026-04-23")
        insights = store.list_insights()
        insight = list(insights.values())[0]
        assert insight["status"] in ("active", "resolved", "promoted", "parked")


class TestInsightLifecycle:
    """§6 — Lifecycle: active → resolved/promoted/parked."""

    def test_add_insight_default_status_active(self, insights_store_path):
        """Newly added insights have status: active."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test", insight_type="pattern", first_seen="2026-04-23")
        insights = store.list_insights()
        assert list(insights.values())[0]["status"] == "active"

    def test_resolve_insight(self, insights_store_path):
        """Insight can be resolved with a reason."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test", insight_type="pattern", first_seen="2026-04-23")
        slug = list(store.list_insights().keys())[0]
        store.resolve(slug, reason="confirmed-fixed")
        insight = store.get(slug)
        assert insight["status"] == "resolved"
        assert insight.get("reason") == "confirmed-fixed"

    def test_promote_insight(self, insights_store_path):
        """Insight can be promoted to deep-dive."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test", insight_type="pattern", first_seen="2026-04-23")
        slug = list(store.list_insights().keys())[0]
        store.promote(slug, promoted_to="Deep Dive Post Title")
        insight = store.get(slug)
        assert insight["status"] == "promoted"
        assert insight.get("promoted_to") == "Deep Dive Post Title"

    def test_park_insight(self, insights_store_path):
        """Insight can be parked (deferred)."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test", insight_type="pattern", first_seen="2026-04-23")
        slug = list(store.list_insights().keys())[0]
        store.park(slug)
        insight = store.get(slug)
        assert insight["status"] == "parked"

    def test_reopen_parked_insight(self, insights_store_path):
        """Parked insight can be re-opened (parked → active)."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test", insight_type="pattern", first_seen="2026-04-23")
        slug = list(store.list_insights().keys())[0]
        store.park(slug)
        store.reopen(slug)
        insight = store.get(slug)
        assert insight["status"] == "active"


class TestDigestReferences:
    """§6 — Insights accumulate digest references over time."""

    def test_add_digest_reference(self, insights_store_path):
        """A digest date can be added to an insight's references."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test", insight_type="pattern", first_seen="2026-04-23")
        slug = list(store.list_insights().keys())[0]
        store.add_digest_reference(slug, "2026-04-23")
        store.add_digest_reference(slug, "2026-04-25")
        insight = store.get(slug)
        assert "2026-04-23" in insight["digest_references"]
        assert "2026-04-25" in insight["digest_references"]

    def test_standalone_candidate_flagged_at_threshold(self, insights_store_path):
        """Insight is flagged as standalone-candidate after N digest references."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test thread", insight_type="pattern", first_seen="2026-04-20")
        slug = list(store.list_insights().keys())[0]
        # Add 3 references (default threshold from spec §3)
        for date in ["2026-04-23", "2026-04-24", "2026-04-25"]:
            store.add_digest_reference(slug, date)
        insight = store.get(slug)
        assert insight.get("standalone_candidate") is True

    def test_not_flagged_below_threshold(self, insights_store_path):
        """Insight is NOT standalone-candidate below the threshold."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test thread", insight_type="pattern", first_seen="2026-04-20")
        slug = list(store.list_insights().keys())[0]
        store.add_digest_reference(slug, "2026-04-23")
        store.add_digest_reference(slug, "2026-04-24")
        insight = store.get(slug)
        assert insight.get("standalone_candidate") is not True

    def test_resolved_not_flagged_above_threshold(self, insights_store_path):
        """Resolved insights are not flagged standalone-candidate even if above threshold."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("test", insight_type="pattern", first_seen="2026-04-20")
        slug = list(store.list_insights().keys())[0]
        for date in ["2026-04-23", "2026-04-24", "2026-04-25"]:
            store.add_digest_reference(slug, date)
        store.resolve(slug, reason="confirmed-fixed")
        insight = store.get(slug)
        assert insight.get("standalone_candidate") is not True


class TestPersistence:
    """Insights persist to digest_insights.yaml."""

    def test_persists_to_disk(self, insights_store_path):
        """Adding an insight writes it to the YAML file."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("persistent insight", insight_type="pattern", first_seen="2026-04-23")
        store.save()

        # Re-load from disk
        store2 = InsightStore(insights_store_path)
        insights = store2.list_insights()
        assert len(insights) == 1
        assert "persistent insight" in list(insights.values())[0]["text"]

    def test_loads_existing_insights(self, insights_store_path):
        """Re-initializing the store loads existing insights from disk."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add("first", insight_type="pattern", first_seen="2026-04-23")
        store.save()

        store2 = InsightStore(insights_store_path)
        store2.add("second", insight_type="weak-signal", first_seen="2026-04-24")
        insights = store2.list_insights()
        assert len(insights) == 2
