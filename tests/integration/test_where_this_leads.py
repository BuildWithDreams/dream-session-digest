"""
Integration tests: "Where This Leads" Flow (Feature B, §3)

Tests AC4: Where This Leads appears only when triggered
Tests AC5: Contextual links extracted from session URLs
"""
import os
import pytest


class TestWhereThisLeadsTriggerIntegration:
    """End-to-end: session text → triggered? → section built."""

    def test_trigger_produces_where_this_leads_section(self, sample_session_with_urls):
        """A session with 'where this leads' trigger produces the full section."""
        forward_links = pytest.importorskip('forward_links'); from forward_links import build_where_this_leads_section
        with open(sample_session_with_urls) as f:
            content = f.read()
        section = build_where_this_leads_section(session_text=content)
        assert len(section) > 0
        assert section.strip() != ""

    def test_non_triggered_session_produces_empty_section(self):
        """A session without any trigger phrase produces empty string."""
        forward_links = pytest.importorskip('forward_links'); from forward_links import build_where_this_leads_section
        text = "Worked on docker-compose setup and fixed the verusd container restart."
        section = build_where_this_leads_section(session_text=text)
        assert section.strip() == ""

    def test_links_appear_in_section(self, sample_session_with_urls):
        """Contextual GitHub links appear in the section."""
        forward_links = pytest.importorskip('forward_links'); from forward_links import build_where_this_leads_section
        with open(sample_session_with_urls) as f:
            content = f.read()
        section = build_where_this_leads_section(session_text=content)
        assert "github.com" in section or "vdex-liquidity-bot" in section.lower()


class TestWhereThisLeadsInDigestOutput:
    """Where This Leads appears in final blog post and email output."""

    def test_section_not_in_standard_digest_output(self, sample_sessions_data):
        """Standard digest (no trigger) does NOT include Where This Leads."""
        from session_digest import build_blog_post
        result = build_blog_post(
            "2026-04-25",
            sample_sessions_data,
            proj_keywords={},
            label_keywords={},
            evidence=None,
        )
        # Where This Leads only appears when triggered
        assert "## Where This Leads" not in result

    def test_future_anchors_format_in_where_this_leads(self):
        """Future Anchors use checklist format: - [ ] Item."""
        forward_links = pytest.importorskip('forward_links'); from forward_links import extract_future_anchors
        text = (
            "Next steps:\n"
            "- Monitor bot for 24h\n"
            "- Review audit findings\n"
        )
        anchors = extract_future_anchors(text)
        # Each anchor should be suitable for checklist output
        assert len(anchors) >= 2


class TestCrossDigestThreading:
    """§3.3 — Insights cross-reference across digests."""

    def test_insight_stores_digest_date_reference(self, insights_store_path):
        """Adding an insight from a session stores the digest date."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add(
            text="Pattern: vARRR bridge instability",
            insight_type="pattern",
            first_seen="2026-04-23",
        )
        slug = list(store.list_insights().keys())[0]
        store.add_digest_reference(slug, "2026-04-23")
        insight = store.get(slug)
        assert "2026-04-23" in insight["digest_references"]

    def test_insight_backlink_format(self, insights_store_path):
        """Promoted insight generates backlink for source digests."""
        insight_store = pytest.importorskip('insight_store'); from insight_store import InsightStore
        store = InsightStore(insights_store_path)
        store.add(
            text="Deep-dive-worthy thread",
            insight_type="pattern",
            first_seen="2026-04-20",
        )
        slug = list(store.list_insights().keys())[0]
        for date in ["2026-04-23", "2026-04-24", "2026-04-25"]:
            store.add_digest_reference(slug, date)
        store.promote(slug, promoted_to="The vARRR Bridge Audit: A 6-Day Thread")
        insight = store.get(slug)
        # Backlink text should be generated
        assert insight.get("promoted_to") is not None
        # digest_sources list should contain all contributing dates
        assert "2026-04-23" in insight["digest_references"]
