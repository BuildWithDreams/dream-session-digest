"""
Shared fixtures for dream-session-digest tests.
All tests use real session_digest.py functions; Venice and network calls are mocked.
"""
import json
import os
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure the repo scripts are on the path
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)


# ── Sample session files ──────────────────────────────────────────────────────

@pytest.fixture
def sample_session_jsonl(tmp_path):
    """Current JSONL format — one JSON object per line, with session_meta."""
    f = tmp_path / "20260425_080000_abc123.jsonl"
    f.write_text(
        '{"role":"session_meta","platform":"telegram","model":"minimax-m27"}\n'
        '{"role":"user","content":"review digest for 2026-04-23"}\n'
        '{"role":"assistant","content":"Ill pull up that digest and open a review."}\n'
        '{"role":"user","content":"add screenshot to post"}\n'
        '{"role":"assistant","content":"Noted. Screenshot queued for next digest run."}\n'
    )
    return str(f)


@pytest.fixture
def sample_session_legacy_json(tmp_path):
    """Legacy JSON format — top-level messages array."""
    f = tmp_path / "session_20260315_080000_def456.json"
    f.write_text(json.dumps({
        "session_id": "session_20260315_080000_def456",
        "model": "minimax",
        "platform": "cli",
        "session_start": "2026-03-15T08:00:00+00:00",
        "messages": [
            {"role": "user", "content": "deploy the new stack"},
            {"role": "assistant", "content": "Deployment complete."},
        ]
    }))
    return str(f)


@pytest.fixture
def sample_session_with_urls(tmp_path):
    """Session containing URLs for Contextual Links testing and Future Anchors."""
    f = tmp_path / "20260425_100000_urls.jsonl"
    f.write_text(
        '{\"role\":\"session_meta\",\"platform\":\"telegram\",\"model\":\"minimax-m27\"}\n'
        '{\"role\":\"user\",\"content\":\"worked on the vDEX liquidity bot today\"}\n'
        '{\"role\":\"assistant\",\"content\":\"Deployed. See https://github.com/BuildWithDreams/vdex-liquidity-bot/issues/47\"}\n'
        '{\"role\":\"user\",\"content\":\"where this leads\"}\n'
        '{\"role\":\"assistant\",\"content\":\"Next steps:\\n- Monitor the bot for 24h\\n- Review audit findings\"}\n'
    )
    return str(f)


@pytest.fixture
def session_with_review_trigger(tmp_path):
    """Session whose content triggers Q2/Q3 review questions conditionally."""
    f = tmp_path / "20260425_110000_review.jsonl"
    f.write_text(
        '{"role":"session_meta","platform":"telegram"}\n'
        '{"role":"user","content":"something unexpected happened with the bridge"}\n'
        '{"role":"assistant","content":"Debugging the bridge connection issue."}\n'
        '{"role":"user","content":"review today"}\n'
    )
    return str(f)


# ── Config fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def minimal_config(tmp_path):
    """Minimal config for testing — no credentials needed."""
    cfg = tmp_path / "digest_config.yaml"
    cfg.write_text(textwrap.dedent("""\
        github:
          org: "test-org"
          blog_repo: "test-blog"
          tracked_repos: []
        email:
          from: "test@example.com"
          to: ["test@example.com"]
        sessions:
          dir: "~/.hermes/sessions"
    """))
    return str(cfg)


@pytest.fixture
def full_config_with_new_fields(tmp_path):
    """Config with all new review/forward_links/deep_dive/media fields populated."""
    cfg = tmp_path / "digest_config.yaml"
    cfg.write_text(textwrap.dedent("""\
        github:
          org: "test-org"
          blog_repo: "test-blog"
          tracked_repos: []
        email:
          from: "test@example.com"
          to: ["test@example.com"]
        sessions:
          dir: "~/.hermes/sessions"
        review:
          enabled: true
          token_budget_multiplier: 2.0
          auto_trigger_after_hour: 22
        forward_links:
          enabled: true
          trigger_phrase: "where this leads"
          max_contextual_links: 5
          max_anchors: 5
          cross_thread_threshold: 3
        deep_dive:
          auto_promote: false
          min_days_span: 3
        media:
          enabled: true
          blog_repo_dir: "~/.hermes/test-blog-clone"
    """))
    return str(cfg)


# ── Mock Venice ────────────────────────────────────────────────────────────────

class MockVeniceResponse:
    """Stable structured response from mocked Venice API."""
    def __init__(self, content: str):
        self.content = content

    def to_dict(self):
        return {
            "choices": [{
                "message": {"content": self.content},
                "finish_reason": "stop",
            }]
        }


@pytest.fixture
def mock_venice(mocker):
    """Mocks Venice API calls — returns stable, structured responses."""
    # Patch at the urllib level so retries also return mocked data
    mock_urlopen = mocker.patch("urllib.request.urlopen")
    mock_urlopen.return_value.__enter__ = mocker.Mock(
        return_value=mocker.Mock(
            read=mocker.Mock(return_value=json.dumps({
                "choices": [{
                    "message": {"content": "Mocked summary via Venice."},
                    "finish_reason": "stop",
                }]
            }).encode())
        )
    )
    mock_urlopen.return_value.__exit__ = mocker.Mock(return_value=False)
    return mock_urlopen


# ── Digest runner helper ──────────────────────────────────────────────────────

@pytest.fixture
def run_digest(mocker, minimal_config, tmp_path):
    """Run session_digest.run() with mocked Venice + config override."""
    import session_digest as sd

    # Point config at our test file
    mocker.patch.object(sd, "CONFIG_FILE", minimal_config)
    # Re-load config with patched path
    sd._config = None
    sd._load_config = lambda: sd._load_config.__wrapped__() if hasattr(sd._load_config, '__wrapped__') else None

    # Better: patch _cfg_get directly and clear cache
    mocker.patch.object(sd, "_config", None)
    original_load = sd._load_config

    def patched_load():
        import yaml
        with open(minimal_config) as f:
            sd._config = yaml.safe_load(f)
        return sd._config

    mocker.patch.object(sd, "_load_config", patched_load)
    mocker.patch.object(sd, "_cfg_get", lambda *k, default=None: _cfg_get_patched(sd._config, *k, default=default))

    # Also patch GH_BLOG_TOKEN so blog push doesn't explode
    mocker.patch.object(sd, "GH_BLOG_TOKEN", "fake-token")

    return sd.run


def _cfg_get_patched(config, *keys, default=None):
    """Navigate nested dict for patched config."""
    if config is None:
        return default
    val = config
    for k in keys:
        try:
            val = val[k]
        except (TypeError, KeyError):
            return default
    return val if val is not None else default


# ── Insight store fixture ─────────────────────────────────────────────────────

@pytest.fixture
def insights_store_path(tmp_path):
    return str(tmp_path / "digest_insights.yaml")


@pytest.fixture
def media_queue_path(tmp_path):
    return str(tmp_path / "media_queue.yaml")


# ── Blog post fixture ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_sessions_data():
    """Minimal sessions_data as produced by summarize_cluster_worker."""
    return [
        {
            "session_id": "20260425_080000_abc",
            "timestamp": "Apr 25, 2026 08:00 AM",
            "session_start": "2026-04-25T08:00:00",
            "model": "minimax-m27",
            "platform": "telegram",
            "summary": "Deployed vDEX liquidity bot and fixed a bridge issue.",
            "cluster_size": 1,
            "cluster_files": ["20260425_080000_abc.jsonl"],
            "platforms": {"telegram"},
            "projects": ["vDEX"],
            "labels": [],
        },
        {
            "session_id": "20260425_110000_def",
            "timestamp": "Apr 25, 2026 11:00 AM",
            "session_start": "2026-04-25T11:00:00",
            "model": "minimax-m27",
            "platform": "telegram",
            "summary": "Refactored docker-verusd playbook for PBaaS chain provisioning.",
            "cluster_size": 2,
            "cluster_files": ["20260425_110000_def.jsonl", "20260425_113000_xyz.jsonl"],
            "platforms": {"telegram"},
            "projects": ["docker-verusd"],
            "labels": [],
        },
    ]
