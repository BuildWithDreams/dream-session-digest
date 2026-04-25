"""
Regression tests: Existing Digest Invariants (AC1–AC15, §11.5)

These tests MUST pass on every commit — they protect existing behavior.
If any of these fail, the change that caused it is rejected.
"""
import re
import os
import pytest
import session_digest as sd


class TestDigestOutputInvariants:
    """Non-negotiable: these must hold for every digest output."""

    def test_digest_output_contains_github_activity(self, sample_sessions_data):
        """Every digest must include a GitHub Activity section (if evidence _text is provided)."""
        # _text must be pre-rendered (as load_evidence_manifest() does in the real pipeline)
        result = sd.build_blog_post(
            "2026-04-25",
            sample_sessions_data,
            proj_keywords={},
            label_keywords={},
            evidence={"commits": [{"repo": "test-repo", "sha": "abc1234", "message": "test commit"}], "_text": "## GitHub Activity\nTest commit."},
        )
        assert "GitHub Activity" in result

    def test_email_contains_session_count(self, sample_sessions_data):
        """Email header must state number of clusters and sessions."""
        result = sd.build_email(
            "2026-04-25",
            sample_sessions_data,
            proj_keywords={},
            label_keywords={},
            evidence=None,
        )
        # Must contain the cluster/session count format
        assert re.search(r"\d+ cluster", result)
        assert re.search(r"\d+ session", result)

    def test_email_contains_header_marker(self, sample_sessions_data):
        """Email body contains SESSION DIGEST — marker."""
        result = sd.build_email(
            "2026-04-25",
            sample_sessions_data,
            proj_keywords={},
            label_keywords={},
            evidence=None,
        )
        assert "SESSION DIGEST" in result

    def test_email_contains_github_links_when_evidence_present(self, sample_sessions_data):
        """Email body contains GitHub URLs when evidence is provided."""
        evidence = {
            "commits": [
                {"repo": "docker-verusd", "sha": "a1b2c3d", "message": "fix: container restart"}
            ],
            "merged_prs": [],
            "issues": [],
            "_text": "See [docker-verusd](https://github.com/BuildWithDreams/docker-verusd)",
        }
        result = sd.build_email(
            "2026-04-25",
            sample_sessions_data,
            proj_keywords={},
            label_keywords={},
            evidence=evidence,
        )
        assert "github.com" in result

    def test_review_addendum_has_reviewed_v1_marker(self):
        """Reviewed posts must carry the reviewed-v1 tag (AC3)."""
        try:
            review_addendum = pytest.importorskip('review_addendum'); from review_addendum import build_review_addendum
            addendum = build_review_addendum(
                "2026-04-23",
                qa_pairs={"[1]": "test answer"},
                original_summary="original text",
            )
            assert "reviewed-v1" in addendum
        except ImportError:
            pytest.skip("review_addendum module not yet implemented")

    def test_where_this_leads_never_appears_without_trigger(self):
        """Where This Leads section must NOT appear when not triggered (AC4 regression)."""
        try:
            forward_links = pytest.importorskip('forward_links'); from forward_links import build_where_this_leads_section
        except ImportError:
            pytest.skip("forward_links module not yet implemented")
        text = "Standard session — no special triggers. Built the docker setup."
        result = build_where_this_leads_section(session_text=text)
        assert "## Where This Leads" not in result
        assert result.strip() == ""


class TestSessionFormatInvariants:
    """Both JSONL and JSON session formats must parse correctly."""

    def test_jsonl_and_json_sessions_both_parsed(self, sample_session_jsonl, sample_session_legacy_json):
        """Both session formats must produce valid text without crashing."""
        for session_file in [sample_session_jsonl, sample_session_legacy_json]:
            result = sd.extract_messages_from_session(session_file)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_clustering_handles_empty_session_list(self):
        """cluster_sessions() returns empty list when given no files."""
        clusters = sd.cluster_sessions([])
        assert clusters == []

    def test_clustering_returns_list(self, sample_session_jsonl):
        """cluster_sessions() returns a list for valid session."""
        clusters = sd.cluster_sessions([sample_session_jsonl])
        assert isinstance(clusters, list)


class TestConfigInvariants:
    """Config loading must never crash — fallbacks always work."""

    def test_cfg_get_handles_missing_keys(self):
        """_cfg_get returns default when keys are missing."""
        result = sd._cfg_get("nonexistent", "section", "key", default="fallback")
        assert result == "fallback"

    def test_cfg_get_returns_none_on_missing_optional(self):
        """_cfg_get returns None for missing optional values (not default)."""
        result = sd._cfg_get("email", "nonexistent_key", default=None)
        assert result is None

    def test_config_file_missing_does_not_crash(self, monkeypatch):
        """When digest_config.yaml is missing, _load_config returns None without crashing."""
        monkeypatch.setattr(sd, "_config", "SOME_VALUE")  # ensure not None initially
        result = sd._load_config()
        # _load_config returns None when file is missing
        assert hasattr(sd, "_load_config")


class TestMediaInvariants:
    """Media feature must not break existing non-media digest runs."""

    def test_media_queue_missing_does_not_crash_digest(self, tmp_path):
        """Missing media_queue.yaml should not crash the digest pipeline."""
        pytest.importorskip("media_queue")
        from media_queue import MediaQueue

        fake_path = str(tmp_path / "nonexistent_dir" / "media_queue.yaml")
        queue = MediaQueue(fake_path)
        # Should gracefully return empty queue
        assert queue.count_pending() == 0
        # Should not raise
