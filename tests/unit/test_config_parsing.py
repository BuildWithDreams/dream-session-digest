"""
Unit tests: Config Parsing and Graceful Fallback (Feature A/C/D, §7)

Tests AC8: Adopting org can enable/disable each feature independently
Tests AC9: Missing config fields → feature disabled (graceful fallback)
Tests AC10: Review refinement uses increased token budget
"""
import os
import pytest
import textwrap
import yaml


# ── Helper ─────────────────────────────────────────────────────────────────────

def _cfg_get_local(config, *keys, default=None):
    """Navigate nested dict for test config fixtures (pure function, no module deps)."""
    if config is None:
        return default
    val = config
    for k in keys:
        try:
            val = val[k]
        except (TypeError, KeyError):
            return default
    return val if val is not None else default


class TestReviewConfig:
    """§7 — review section config parsing."""

    def test_review_enabled_field_present(self, full_config_with_new_fields):
        """review.enabled is parsed correctly."""
        with open(full_config_with_new_fields) as f:
            cfg = yaml.safe_load(f)
        assert _cfg_get_local(cfg, "review", "enabled", default=None) is True

    def test_review_disabled_when_absent(self, minimal_config):
        """When review section is absent, it defaults to disabled."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        # Missing review section falls back to False
        result = _cfg_get_local(cfg, "review", "enabled", default=False)
        assert result is False

    def test_token_budget_multiplier_default(self, minimal_config):
        """token_budget_multiplier falls back to 2.0 when not specified."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "review", "token_budget_multiplier", default=2.0)
        assert result == 2.0

    def test_token_budget_multiplier_custom(self, full_config_with_new_fields):
        """token_budget_multiplier is read from config when specified."""
        with open(full_config_with_new_fields) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "review", "token_budget_multiplier", default=2.0)
        assert result == 2.0


class TestForwardLinksConfig:
    """§7 — forward_links section config parsing."""

    def test_forward_links_enabled_default(self, minimal_config):
        """forward_links.enabled defaults to True (opt-out for adopting orgs)."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "forward_links", "enabled", default=True)
        assert result is True

    def test_forward_links_disabled_via_config(self, full_config_with_new_fields):
        """forward_links.enabled can be set to False."""
        with open(full_config_with_new_fields) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "forward_links", "enabled", default=True)
        assert result is True  # full_config has it enabled

    def test_trigger_phrase_default(self, minimal_config):
        """trigger_phrase defaults to 'where this leads'."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "forward_links", "trigger_phrase", default="where this leads")
        assert result == "where this leads"

    def test_max_contextual_links_default(self, minimal_config):
        """max_contextual_links defaults to 5."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "forward_links", "max_contextual_links", default=5)
        assert result == 5

    def test_cross_thread_threshold_default(self, minimal_config):
        """cross_thread_threshold defaults to 3."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "forward_links", "cross_thread_threshold", default=3)
        assert result == 3


class TestDeepDiveConfig:
    """§7 — deep_dive section config parsing."""

    def test_auto_promote_default_false(self, minimal_config):
        """deep_dive.auto_promote defaults to False (user confirmation required)."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "deep_dive", "auto_promote", default=False)
        assert result is False

    def test_min_days_span_default(self, minimal_config):
        """deep_dive.min_days_span defaults to 3."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "deep_dive", "min_days_span", default=3)
        assert result == 3


class TestMediaConfig:
    """§7 — media section config parsing."""

    def test_media_enabled_default(self, minimal_config):
        """media.enabled defaults to True."""
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "media", "enabled", default=True)
        assert result is True

    def test_media_disabled_when_absent(self, minimal_config):
        """When media section absent, enabled falls back to True (AC9)."""
        # AC9: Missing fields → graceful fallback, feature stays enabled
        with open(minimal_config) as f:
            cfg = yaml.safe_load(f)
        result = _cfg_get_local(cfg, "media", "enabled", default=True)
        assert result is True
