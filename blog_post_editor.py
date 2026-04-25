"""
Feature A/C/D — Blog Post Editor (DIGEST.md §2.4, §4, §5.7)

Utilities for editing Jekyll blog posts:
- append_addendum_to_post(): append review addendum, add reviewed marker to front matter
- insert_media_embed(): insert media embed before a section
- add_where_this_leads_to_post(): append Where This Leads section
- promote_to_deep_dive(): write a deep-dive post from an insight

Usage:
    updated = append_addendum_to_post(post_text, addendum_block, date_str="2026-04-23")
    updated = insert_media_embed(post_text, markdown_embed, target_section="future_anchors", ...)
"""
import re
import os
import subprocess


# ── Addendum ──────────────────────────────────────────────────────────────────

def append_addendum_to_post(
    post_content: str,
    addendum_block: str,
    date_str: str,
) -> str:
    """
    Append review addendum to a blog post and update front matter.

    §2.4:
    - Adds "reviewed: true" to front matter
    - Adds reviewed-v1 marker label
    - Appends addendum block before the closing `---` of the front matter
      OR at the end of the post body (before the footer line)

    Returns updated post content.
    """
    post = post_content

    # Update front matter: add reviewed: true
    fm_pattern = r"^(---.*?)(\n)(---)"
    if re.search(fm_pattern, post, re.DOTALL):
        def add_reviewed(m):
            front = m.group(1)
            # Add reviewed: true before the closing ---
            if "reviewed:" not in front:
                front += "\nreviewed: true"
            return front + m.group(2) + m.group(3)
        post = re.sub(fm_pattern, add_reviewed, post, count=1, flags=re.DOTALL)

    # Check if addendum already exists — replace if so
    existing_addendum = re.search(
        r"## Review Addendum — reviewed-v1.*",
        post,
        re.DOTALL,
    )
    if existing_addendum:
        # Replace existing addendum with new one
        post = post[:existing_addendum.start()] + addendum_block + "\n\n" + post[existing_addendum.start() + len(existing_addendum.group()):]
        return post

    # Append addendum at end of post body
    footer_marker = "*This digest was generated automatically"
    if footer_marker in post:
        post = post.replace(footer_marker, addendum_block + "\n\n" + footer_marker)
    else:
        post = post.rstrip() + "\n\n" + addendum_block + "\n"

    return post


# ── Media embedding ────────────────────────────────────────────────────────────

def insert_media_embed(
    post_content: str,
    markdown_embed: str,
    target_section: str | None = None,
    before_section: str | None = None,
) -> str:
    """
    Insert a media markdown embed into a blog post.

    §5.7 — insertion strategy:
    - If before_section is provided (e.g. "## GitHub Activity"), insert before it
    - If target_section is provided, insert in that section
    - Otherwise append at end of post

    Returns updated post content.
    """
    post = post_content

    if before_section:
        if before_section in post:
            post = post.replace(before_section, markdown_embed + "\n\n" + before_section)
            return post

    if target_section:
        # Find section and append to it
        section_pattern = rf"(##\s+{re.escape(target_section)}.*?)(\n##\s+|\Z)"
        m = re.search(section_pattern, post, re.DOTALL)
        if m:
            section_body = m.group(1)
            after = m.group(2)
            new_section = section_body.rstrip() + "\n\n" + markdown_embed + "\n"
            post = post[:m.start()] + new_section + after + post[m.end():]
            return post

    # Fallback: append at end
    post = post.rstrip() + "\n\n" + markdown_embed + "\n"
    return post


# ── Where This Leads ──────────────────────────────────────────────────────────

def add_where_this_leads_to_post(
    post_content: str,
    where_this_leads_section: str,
) -> str:
    """
    Append "Where This Leads" section to a blog post.

    Inserts before the footer marker if present, otherwise at end.
    """
    if not where_this_leads_section.strip():
        return post_content

    footer_marker = "*This digest was generated automatically"
    if footer_marker in post_content:
        return post_content.replace(
            footer_marker,
            where_this_leads_section + "\n" + footer_marker,
        )
    return post_content.rstrip() + "\n\n" + where_this_leads_section + "\n"


# ── Deep-dive post ─────────────────────────────────────────────────────────────

DEEP_DIVE_TEMPLATE = """---
title: "{title}"
date: {date}
tags: [deep-dive{extra_tags}]
digest_sources: [{digest_sources}]
layout: post
---

{body}

*Expanded from [{n} digest references → digest_sources](#).*
"""


def promote_to_deep_dive(
    title: str,
    body: str,
    digest_sources: list[str],
    extra_tags: list[str] | None = None,
    output_path: str | None = None,
) -> str:
    """
    Write a deep-dive post to the blog repo.

    §4.3 front matter:
        title, date, tags: [deep-dive, ...], digest_sources: [...], layout: post

    Args:
        title: Post title
        body: Venice-generated synthesis content
        digest_sources: List of YYYY-MM-DD dates contributing to this deep-dive
        extra_tags: Additional tags beyond 'deep-dive'
        output_path: Optional file path to write to (otherwise returned as string)

    Returns:
        Post content as string (and writes to output_path if provided).
    """
    date = digest_sources[-1] if digest_sources else __import__("datetime").date.today().isoformat()
    tag_str = ", ".join(f"'{t}'" for t in (["deep-dive"] + (extra_tags or [])))
    sources_str = ", ".join(f"'{d}'" for d in digest_sources)

    post = DEEP_DIVE_TEMPLATE.format(
        title=title,
        date=date,
        extra_tags="," + ",".join(f" {t}" for t in (extra_tags or [])),
        digest_sources=sources_str,
        body=body.strip(),
        n=len(digest_sources),
    )

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(post)

    return post


# ── Blog post update + push ───────────────────────────────────────────────────

BLOG_REPO_DIR = os.path.expanduser("~/.hermes/dream-blog-clone")


def push_updated_post(
    date_str: str,
    updated_post_content: str,
    commit_message: str | None = None,
    dry_run: bool = False,
) -> bool:
    """
    Clone dream-blog, update the post for date_str, commit and push.

    Args:
        date_str: YYYY-MM-DD of the post to update
        updated_post_content: Full new content for the post
        commit_message: Custom commit message (default: "docs: add review addendum for {date}")
        dry_run: If True, makes no changes

    Returns:
        True if push succeeded, False otherwise.
    """
    import shutil
    import json

    from session_digest import (
        _cfg_get,
        GH_BLOG_TOKEN,
        GITHUB_ORG,
        BLOG_REPO,
    )

    blog_token = GH_BLOG_TOKEN
    if not blog_token:
        print("[Blog] GITHUB_PAT env var not set — cannot push", file=__import__("sys").stderr)
        return False

    blog_clone_url = f"https://{blog_token}@github.com/{GITHUB_ORG}/{BLOG_REPO}.git"
    repo_dir = BLOG_REPO_DIR

    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)

    try:
        result = subprocess.run(
            ["git", "clone", blog_clone_url, repo_dir],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"[Blog] Clone failed: {result.stderr}", file=__import__("sys").stderr)
            shutil.rmtree(repo_dir, ignore_errors=True)
            return False
    except Exception as e:
        print(f"[Blog] Clone failed: {e}", file=__import__("sys").stderr)
        return False

    post_path = os.path.join(repo_dir, "_posts", f"{date_str}-session-digest.md")
    os.makedirs(os.path.join(repo_dir, "_posts"), exist_ok=True)
    with open(post_path, "w") as f:
        f.write(updated_post_content)
    print(f"[Blog] Updated {post_path}")

    if dry_run:
        print("[Blog] Dry run — not pushing")
        shutil.rmtree(repo_dir, ignore_errors=True)
        return True

    msg = commit_message or f"docs: add review addendum for {date_str}"
    try:
        subprocess.run(["git", "add", "_posts/"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo_dir, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=repo_dir, capture_output=True, text=True, timeout=30,
        )
        print(f"[Blog] Pushed updated post for {date_str}")
        return True
    except Exception as e:
        print(f"[Blog] Push failed: {e}", file=__import__("sys").stderr)
        return False
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)
