"""
Unit tests: "Where This Leads" Section Builder (Feature B, §3)

Tests AC4: Where This Leads appears only when triggered
Tests AC5: Contextual links are extracted from session URLs
"""
import pytest


class TestTriggerPhraseDetection:
    """§3 — Where This Leads is only generated when explicitly triggered."""

    def test_not_triggered_without_phrase(self, sample_session_jsonl):
        """When no trigger phrase present, is_triggered() returns False."""
        fl = pytest.importorskip("forward_links")
        with open(sample_session_jsonl) as f:
            content = f.read()
        assert fl.is_where_this_leads_triggered(content) is False

    def test_triggered_with_default_phrase(self):
        """Default trigger phrase 'where this leads' activates the section."""
        fl = pytest.importorskip("forward_links")
        text = "where this leads — need to track the bot stability"
        assert fl.is_where_this_leads_triggered(text) is True

    def test_triggered_case_insensitive(self):
        """Trigger detection is case-insensitive."""
        fl = pytest.importorskip("forward_links")
        assert fl.is_where_this_leads_triggered("WHERE THIS LEADS") is True
        assert fl.is_where_this_leads_triggered("Where This Leads") is True

    def test_triggered_with_log_this_as_thread(self):
        """Alternate trigger: 'log this as a thread' also activates."""
        fl = pytest.importorskip("forward_links")
        assert fl.is_where_this_leads_triggered("log this as a thread") is True


class TestContextualLinks:
    """§3.2 Contextual Links — extract and format GitHub URLs from session text."""

    def test_extracts_github_issue_url(self):
        """Issue URLs are extracted with their brief description."""
        fl = pytest.importorskip("forward_links")
        text = "worked on https://github.com/BuildWithDreams/vdex-liquidity-bot/issues/47"
        links = fl.extract_contextual_links(text)
        assert len(links) >= 1
        assert any("issues/47" in link["url"] for link in links)

    def test_extracts_github_pr_url(self):
        """PR URLs are extracted."""
        fl = pytest.importorskip("forward_links")
        text = "merged https://github.com/BuildWithDreams/docker-verusd/pull/23"
        links = fl.extract_contextual_links(text)
        assert len(links) >= 1
        assert any("pull/23" in link["url"] for link in links)

    def test_extracts_github_commit_url(self):
        """Commit URLs are extracted."""
        fl = pytest.importorskip("forward_links")
        text = "pushed to https://github.com/BuildWithDreams/vdex-liquidity-bot/commit/a1b2c3d"
        links = fl.extract_contextual_links(text)
        assert len(links) >= 1
        assert any("commit/a1b2c3d" in link["url"] for link in links)

    def test_external_urls_extracted(self):
        """External URLs (non-GitHub) are extracted as 'External' type."""
        fl = pytest.importorskip("forward_links")
        text = "referenced https://docs.docker.com/compose/ for the compose file"
        links = fl.extract_contextual_links(text)
        assert len(links) >= 1
        assert any("docker.com" in link["url"] for link in links)

    def test_deduplicates_urls(self):
        """Same URL mentioned twice is not duplicated in output."""
        fl = pytest.importorskip("forward_links")
        text = (
            "issue: https://github.com/BuildWithDreams/repo/issues/1\n"
            "follow up: https://github.com/BuildWithDreams/repo/issues/1"
        )
        links = fl.extract_contextual_links(text)
        urls = [l["url"] for l in links]
        assert len(urls) == len(set(urls)), "Duplicate URLs found"

    def test_respects_max_contextual_links(self):
        """Output is capped at max_contextual_links (default 5)."""
        fl = pytest.importorskip("forward_links")
        text = "\n".join(
            f"see https://github.com/BuildWithDreams/repo/issues/{i}"
            for i in range(10)
        )
        links = fl.extract_contextual_links(text, max_links=5)
        assert len(links) <= 5


class TestFutureAnchors:
    """§3.2 Future Anchors — TODO items, follow-ups, deferred decisions."""

    def test_extracts_todo_items(self):
        """TODO-style items are extracted from session text."""
        fl = pytest.importorskip("forward_links")
        text = (
            "Next steps:\n"
            "- Monitor the vDEX bot for 24h\n"
            "- Review vARRR bridge audit findings\n"
        )
        anchors = fl.extract_future_anchors(text)
        assert len(anchors) >= 2
        assert any("monitor" in a.lower() for a in anchors)

    def test_extracts_deferred_decisions(self):
        """Deferred decisions flagged with 'defer' or 'deferred' are captured."""
        fl = pytest.importorskip("forward_links")
        text = "We deferred the PBaaS chain restart decision until next week."
        anchors = fl.extract_future_anchors(text)
        assert len(anchors) >= 1

    def test_respects_max_anchors(self):
        """Output is capped at max_anchors (default 5)."""
        fl = pytest.importorskip("forward_links")
        items = "\n".join(f"- [ ] Task {i}" for i in range(10))
        anchors = fl.extract_future_anchors(items, max_anchors=5)
        assert len(anchors) <= 5


class TestWhereThisLeadsSectionBuilder:
    """§3 — Full section builder."""

    def test_builds_all_three_sub_sections(self, sample_session_with_urls):
        """Section contains Contextual Links, Threaded Insights, Future Anchors."""
        fl = pytest.importorskip("forward_links")
        with open(sample_session_with_urls) as f:
            content = f.read()
        section = fl.build_where_this_leads_section(session_text=content)
        assert "Contextual Links" in section or "contextual" in section.lower()
        assert "Future" in section or "future" in section.lower() or "Anchor" in section

    def test_returns_empty_when_not_triggered(self):
        """When no trigger present, builder returns empty string."""
        fl = pytest.importorskip("forward_links")
        section = fl.build_where_this_leads_section(
            session_text="just some random session text with no triggers"
        )
        assert section.strip() == ""

    def test_never_auto_adds_without_trigger(self):
        """Where This Leads must NOT appear unless triggered (AC4 regression)."""
        fl = pytest.importorskip("forward_links")
        no_trigger = "This was a productive session building the docker setup."
        result = fl.build_where_this_leads_section(session_text=no_trigger)
        assert "Where This Leads" not in result
        assert result.strip() == ""
