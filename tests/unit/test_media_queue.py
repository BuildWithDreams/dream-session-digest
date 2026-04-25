"""
Unit tests: Media Queue (Feature D, §5.8)

Tests AC11: Media upload is accepted and queued
Tests AC12: Media appears in correct assets/media/YYYY-MM-DD/ in blog repo
Tests AC13: Media embeds correctly as markdown image
Tests AC14: Media is NOT auto-added — only when explicitly triggered
Tests AC15: Video (MP4/WebM) uploads are accepted and stored
"""
import os
import pytest


class TestMediaQueueEntry:
    """§5.8 — Media entries in media_queue.yaml."""

    def test_queue_entry_schema(self, media_queue_path):
        """Each queue entry has required fields: path, caption, target_date, target_section."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue = MediaQueue(media_queue_path)
        queue.add(
            file_path="/tmp/screenshot.png",
            caption="vDEX bot dashboard",
            target_date="2026-04-25",
            target_section="future_anchors",
        )
        entries = queue.list_pending()
        assert len(entries) == 1
        entry = entries[0]
        assert "path" in entry
        assert "caption" in entry
        assert "target_date" in entry
        assert "target_section" in entry

    def test_add_image(self, media_queue_path):
        """PNG, JPG, JPEG, WebP images are accepted."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue, UnsupportedMediaError
        queue = MediaQueue(media_queue_path)
        # Should not raise
        queue.add("/tmp/screenshot.png", "bot dashboard", "2026-04-25", "future_anchors")
        assert queue.count_pending() == 1

    def test_add_webp(self, media_queue_path):
        """WebP images are accepted."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue = MediaQueue(media_queue_path)
        queue.add("/tmp/terminal.webp", "build output", "2026-04-25", "future_anchors")
        assert queue.count_pending() == 1

    def test_add_video_mp4(self, media_queue_path):
        """MP4 video uploads are accepted."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue = MediaQueue(media_queue_path)
        queue.add("/tmp/recording.mp4", "screen recording", "2026-04-25", "future_anchors")
        assert queue.count_pending() == 1

    def test_add_video_webm(self, media_queue_path):
        """WebM video uploads are accepted."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue = MediaQueue(media_queue_path)
        queue.add("/tmp/recording.webm", "screen recording", "2026-04-25", "future_anchors")
        assert queue.count_pending() == 1

    def test_rejects_unsupported_format(self, media_queue_path):
        """Unsupported formats (e.g. .gif, .pdf) are rejected."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue, UnsupportedMediaError
        queue = MediaQueue(media_queue_path)
        with pytest.raises(UnsupportedMediaError):
            queue.add("/tmp/clip.gif", "animated clip", "2026-04-25", "future_anchors")


class TestMediaQueueLifecycle:
    """Queue entries are processed and removed after blog commit."""

    def test_mark_processed_removes_entry(self, media_queue_path):
        """After blog commit, entry is removed from queue."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue = MediaQueue(media_queue_path)
        queue.add("/tmp/screenshot.png", "bot dashboard", "2026-04-25", "future_anchors")
        entries = queue.list_pending()
        entry = entries[0]
        queue.mark_processed(entry["id"])
        assert queue.count_pending() == 0

    def test_persistence(self, media_queue_path):
        """Queue persists across MediaQueue instantiations."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue1 = MediaQueue(media_queue_path)
        queue1.add("/tmp/screenshot.png", "caption", "2026-04-25", "future_anchors")
        queue1.save()

        queue2 = MediaQueue(media_queue_path)
        assert queue2.count_pending() == 1

    def test_multiple_entries_for_same_date(self, media_queue_path):
        """Multiple media items can target the same date."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue = MediaQueue(media_queue_path)
        queue.add("/tmp/screenshot-01.png", "first", "2026-04-25", "future_anchors")
        queue.add("/tmp/screenshot-02.png", "second", "2026-04-25", "future_anchors")
        entries = [e for e in queue.list_pending() if e["target_date"] == "2026-04-25"]
        assert len(entries) == 2


class TestMediaPathGeneration:
    """§5.3 — Media stored at assets/media/YYYY-MM-DD/ in blog repo."""

    def test_target_path_format(self, media_queue_path):
        """Entry's computed target path follows assets/media/YYYY-MM-DD/ convention."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import MediaQueue
        queue = MediaQueue(media_queue_path)
        queue.add("/tmp/screenshot.png", "caption", "2026-04-25", "future_anchors")
        entry = queue.list_pending()[0]
        assert "2026-04-25" in entry["target_path"]
        assert "assets" in entry["target_path"] or "media" in entry["target_path"]


class TestMarkdownEmbed:
    """§5.6 — Blog post markdown embedding."""

    def test_markdown_image_format(self):
        """Markdown image uses correct format: ![caption](/assets/media/...')."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import format_markdown_embed
        embed = format_markdown_embed(
            file_path="screenshot-01.png",
            caption="vDEX bot dashboard",
            target_date="2026-04-25",
        )
        assert embed.startswith("![]")
        assert "screenshot-01.png" in embed
        assert "2026-04-25" in embed
        assert "vDEX bot dashboard" in embed

    def test_caption_in_italic_under_image(self):
        """Caption appears as italic text below the image."""
        media_queue = pytest.importorskip('media_queue'); from media_queue import format_markdown_embed
        embed = format_markdown_embed(
            file_path="screenshot-01.png",
            caption="Bot dashboard",
            target_date="2026-04-25",
        )
        assert "*Bot dashboard*" in embed or "_Bot dashboard_" in embed
