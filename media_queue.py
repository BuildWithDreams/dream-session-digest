"""
Feature D — Media Queue (DIGEST.md §5.8)

Manages media_queue.yaml — a queue of media files uploaded during sessions
that are waiting to be committed to the blog repo and embedded in posts.

Queue entry schema (§5.8):
    - id: str          # UUID
      path: str        # local file path
      caption: str     # user-provided caption
      target_date: str # YYYY-MM-DD
      target_section: str  # future_anchors | screenshots | contextual_links
      target_path: str # assets/media/YYYY-MM-DD/screenshot-01.png
      added_at: str    # ISO timestamp

Supported formats: PNG, JPG, JPEG, WebP, MP4, WebM

Usage:
    queue = MediaQueue()                              # default path
    queue = MediaQueue("/custom/path/media_queue.yaml")
    queue.add("/tmp/screenshot.png", "vDEX dashboard", "2026-04-25", "future_anchors")
    queue.save()
    for entry in queue.list_pending():
        print(entry["target_path"], entry["caption"])
    queue.mark_processed(entry["id"])
"""
import os
import uuid
import yaml
from datetime import datetime, timezone
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

MEDIA_QUEUE_FILE = os.path.expanduser("~/.hermes/scripts/media_queue.yaml")

IMAGE_EXTS  = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS  = {".mp4", ".webm"}
ALL_EXTS    = IMAGE_EXTS | VIDEO_EXTS

# Section → human-readable sub-heading in post
SECTION_LABELS = {
    "future_anchors":     "Screenshots & Media",
    "screenshots":        "Screenshots & Media",
    "contextual_links":   "Contextual Links",
}


class UnsupportedMediaError(ValueError):
    """Raised when a media file has an unsupported extension."""


def _ext_ok(filepath: str) -> bool:
    """Return True if file extension is in supported set."""
    _, ext = os.path.splitext(filepath.lower())
    return ext in ALL_EXTS


def _compute_target_path(
    original_path: str,
    target_date: str,
) -> str:
    """
    Compute the blog repo storage path for a media file.

    Format: assets/media/YYYY-MM-DD/filename
    """
    filename = os.path.basename(original_path)
    return f"assets/media/{target_date}/{filename}"


def _timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── MediaQueue ────────────────────────────────────────────────────────────────

class MediaQueue:
    """
    Manages media_queue.yaml — queues media uploads for next digest run.
    """

    def __init__(self, queue_file: str | None = None):
        self.path = queue_file or MEDIA_QUEUE_FILE
        self._entries: list = []
        self._load()

    def _load(self) -> None:
        """Load existing queue entries from disk."""
        try:
            with open(self.path) as f:
                data = yaml.safe_load(f) or {}
                self._entries = data.get("entries", [])
        except (FileNotFoundError, yaml.YAMLError):
            self._entries = []

    def save(self) -> None:
        """Write queue entries to disk."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            yaml.safe_dump(
                {"entries": self._entries},
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    def add(
        self,
        file_path: str,
        caption: str,
        target_date: str,
        target_section: str = "screenshots",
    ) -> str:
        """
        Add a media file to the queue.

        Returns the entry ID.
        Raises UnsupportedMediaError if the file type is not supported.
        """
        if not _ext_ok(file_path):
            _, ext = os.path.splitext(file_path.lower())
            raise UnsupportedMediaError(
                f"Unsupported media format: {ext}. "
                f"Supported: {', '.join(sorted(ALL_EXTS))}"
            )

        entry_id = str(uuid.uuid4())[:8]
        target_path = _compute_target_path(file_path, target_date)

        entry = {
            "id": entry_id,
            "path": file_path,
            "caption": caption,
            "target_date": target_date,
            "target_section": target_section,
            "target_path": target_path,
            "added_at": _timestamp_now(),
            "processed": False,
        }
        self._entries.append(entry)
        return entry_id

    def list_pending(self) -> list:
        """Return all unprocessed queue entries."""
        return [e for e in self._entries if not e.get("processed")]

    def count_pending(self) -> int:
        """Return count of unprocessed entries."""
        return len(self.list_pending())

    def mark_processed(self, entry_id: str) -> None:
        """Mark an entry as processed (removes from pending)."""
        for entry in self._entries:
            if entry["id"] == entry_id:
                entry["processed"] = True
                entry["processed_at"] = _timestamp_now()
                break
        # Remove processed entries to keep queue clean
        self._entries = [e for e in self._entries if not e.get("processed")]

    def clear_processed(self) -> None:
        """Remove all processed entries from the queue."""
        self._entries = [e for e in self._entries if not e.get("processed")]


# ── Markdown embedding ────────────────────────────────────────────────────────

def format_markdown_embed(
    file_path: str,
    caption: str,
    target_date: str,
    target_section: str | None = None,
) -> str:
    """
    Format a media file as a markdown image embed for the blog post.

    §5.6 format:
    ![caption](/assets/media/YYYY-MM-DD/filename.png)
    *Caption text*
    """
    filename = os.path.basename(file_path)
    rel_path = f"/assets/media/{target_date}/{filename}"

    lines = [
        f"![]({rel_path})",
        f"*{caption}*",
    ]

    if target_section and target_section in SECTION_LABELS:
        label = SECTION_LABELS[target_section]
        lines.insert(0, f"**{label}**\n")

    return "\n".join(lines)
