# ─────────────────────────────────────────────────────────────────────────────
# Evidence Scanner — fetches GitHub commits, PRs, and issues
# for the configured GitHub org since a given date.
#
# Also scans session files for git push output and gh repo create events
# to build a complete changelog that doesn't rely on author attribution.
#
# Configuration: see digest_config.yaml in the same directory.
# Falls back to BuildWithDreams defaults if no config found.
# ─────────────────────────────────────────────────────────────────────────────

import json
import re
import os
import sys
import glob
import yaml
import urllib.request
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Load digest config
CONFIG_FILE = os.path.expanduser(os.path.join(os.path.dirname(__file__), "digest_config.yaml"))
try:
    with open(CONFIG_FILE) as f:
        _cfg = yaml.safe_load(f)
except FileNotFoundError:
    _cfg = None

def _cfg_get(*keys, default=None):
    if _cfg is None:
        return default
    val = _cfg
    for k in keys:
        try:
            val = val[k]
        except (TypeError, KeyError):
            return default
    return val if val is not None else default

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT", "")
ORG = _cfg_get("github", "org", default="BuildWithDreams")
REPOS = _cfg_get("github", "tracked_repos", default=[
    "dream-pbaas-provisioning",
    "docker-verusd",
    "dream-info",
])

SESSIONS_DIR = os.path.expanduser(_cfg_get("sessions", "dir", default="~/.hermes/sessions"))


def gh_get(url):
    """Make an authenticated GitHub API GET request."""
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT", "")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ── Session Scanner ──────────────────────────────────────────────────────────

def scan_sessions_for_gh_events(since_date_str):
    """
    Scan session files for git push output and gh repo create events.
    Returns a dict with 'pushes', 'repos_created', 'issues' keyed from session content.

    The git push output in session files looks like:
      {"output": "🔍 Scanning staged files...\n✅ No secrets detected\n[main 0c41cd4] docs: add SKILL.md\n 2 files changed...\nTo github.com:BuildWithDreams/repo.git\n   old..new  main -> main", ...}

    gh repo create output looks like:
      {"output": "...\nCreated: BuildWithDreams/repo-name\nUrl: https://github.com/...", ...}
    """
    since_iso = f"{since_date_str}T00:00:00Z"

    # Find session files for this date
    date_pattern = since_date_str.replace("-", "")  # YYYYMMDD
    session_files = glob.glob(os.path.join(SESSIONS_DIR, f"*{date_pattern}*.json")) + \
                     glob.glob(os.path.join(SESSIONS_DIR, f"*{date_pattern}*.jsonl"))

    pushes = []       # {repo, sha, message, url, file}
    repos_created = [] # {repo, description, url, file}
    issues = []       # {repo, number, title, url, file}

    for filepath in session_files:
        fname = os.path.basename(filepath)
        try:
            if filepath.endswith(".jsonl"):
                messages = []
                with open(filepath, "r", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                messages.append(json.loads(line))
                            except:
                                pass
            else:
                with open(filepath, "r", errors="replace") as f:
                    data = json.load(f)
                messages = data.get("messages", [])
        except Exception:
            continue

        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))

            # Skip system messages
            if role == "system" or content.startswith("[System note"):
                continue

            # ── Repo created ──────────────────────────────────────────────
            # "Created: BuildWithDreams/repo\nUrl: https://..."
            for m in re.finditer(r'Created:\s*BuildWithDreams/([\w.-]+)', content):
                repo = m.group(1)
                # Try to grab description from nearby JSON fields
                desc = ""
                desc_m = re.search(r'"description":\s*"([^"]*)"', content)
                if desc_m:
                    desc = desc_m.group(1)
                repos_created.append({
                    "repo": repo,
                    "description": desc,
                    "url": f"https://github.com/BuildWithDreams/{repo}",
                    "file": fname,
                })

            # ── Issue created ─────────────────────────────────────────────
            # "Issue created: https://github.com/BuildWithDreams/repo/issues/N"
            for m in re.finditer(r'Issue created:\s*https://github\.com/BuildWithDreams/([\w.-]+)/issues/(\d+)', content):
                repo, num = m.group(1), m.group(2)
                title = ""
                title_m = re.search(r'"title":\s*"([^"]*)"', content)
                if title_m:
                    title = title_m.group(1)
                issues.append({
                    "repo": repo,
                    "number": int(num),
                    "title": title,
                    "url": f"https://github.com/BuildWithDreams/{repo}/issues/{num}",
                    "file": fname,
                })

            # ── Git push ──────────────────────────────────────────────────
            # "To github.com:BuildWithDreams/repo.git" signals a push.
            # The commit info appears either:
            #   (a) in the SAME output block, e.g. {"output": "...\n[main sha] msg\n...\nTo github.com:...\n   old..new  main -> main"}
            #   (b) in a PRECEDING tool output on the same session file page
            # We look back 1500 chars to catch case (a), and forward 200 to catch the remote line.
            for push_m in re.finditer(r'To github\.com:BuildWithDreams/([\w.-]+)\.git', content):
                repo = push_m.group(1)
                push_pos = push_m.start()
                block = content[max(0, push_pos - 1500):push_pos + 200]

                # Find all [main sha] message lines
                commit_lines = re.findall(r'\[main\s+([0-9a-f]{7,})\]\s*([^\n]+)', block)

                if commit_lines:
                    for sha, msg_text in commit_lines:
                        sha = sha[:7]
                        msg_text = msg_text.strip()
                        # Truncate at first escaped newline or field delimiter
                        msg_text = msg_text.split("\\n")[0].strip()[:100]
                        pushes.append({
                            "repo": repo,
                            "sha": sha,
                            "message": msg_text,
                            "url": f"https://github.com/BuildWithDreams/{repo}/commit/{sha}",
                            "file": fname,
                        })
                else:
                    # No explicit [main sha] — try to extract from remote update line
                    # Normal:   "   abc1234..def5678  main -> main"
                    # Force:    " + abc1234..def5678  main -> main (forced update)"
                    remote = re.search(r'\+?\s*([0-9a-f]{7,})\.\.([0-9a-f]{7,})\s+main\s*->\s*main', block)
                    if remote:
                        new_sha = remote.group(2)[:7]
                        pushes.append({
                            "repo": repo,
                            "sha": new_sha,
                            "message": "(push)",
                            "url": f"https://github.com/BuildWithDreams/{repo}/commit/{new_sha}",
                            "file": fname,
                        })

    # Deduplicate by (type, repo, identifier)
    seen = set()
    def dedup(lst, key_fn):
        result = []
        for item in lst:
            key = key_fn(item)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    pushes = dedup(pushes, lambda x: f"push:{x['repo']}:{x['sha']}")
    repos_created = dedup(repos_created, lambda x: f"repo:{x['repo']}")
    issues = dedup(issues, lambda x: f"issue:{x['repo']}:{x['number']}")

    return {
        "pushes": pushes,
        "repos_created": repos_created,
        "issues": issues,
    }


def resolve_commits_via_api(pushes):
    """
    Given a list of {repo, sha, message, url}, enrich with full commit data
    from the GitHub API (author, date, files changed) using the BWD org as source.
    Falls back to existing data if API fails.
    """
    enriched = []
    for push in pushes:
        try:
            url = f"https://api.github.com/repos/{ORG}/{push['repo']}/commits/{push['sha']}"
            data = gh_get(url)
            commit = data.get("commit", {})
            author_info = commit.get("author", {})
            files_changed = data.get("files", [])
            enriched.append({
                "repo": push["repo"],
                "sha": push["sha"],
                "message": push["message"] if push["message"] != "(push)" else commit.get("message", "").split("\n")[0][:100],
                "author": author_info.get("name", ""),
                "date": commit.get("author", {}).get("date", "")[:10],
                "files_changed": len(files_changed),
                "url": push["url"],
                "file": push.get("file", ""),
            })
        except Exception:
            enriched.append({**push, "author": "", "date": "", "files_changed": 0})
    return enriched


def enrich_repos_via_api(repos_created):
    """
    Given a list of {repo, description, url}, fetch full repo metadata
    from the GitHub API to fill in the description if it's empty.
    """
    enriched = []
    for repo_info in repos_created:
        if repo_info.get("description"):
            enriched.append(repo_info)
            continue
        try:
            url = f"https://api.github.com/repos/{ORG}/{repo_info['repo']}"
            data = gh_get(url)
            desc = data.get("description", "") or "Repository created"
            enriched.append({**repo_info, "description": desc})
        except Exception:
            enriched.append({**repo_info, "description": "Repository created"})
    return enriched


def enrich_issues_via_api(issues):
    """
    Given a list of {repo, number, title, url}, fetch full issue details
    from the GitHub API to fill in the title if missing.
    """
    enriched = []
    for issue in issues:
        if issue.get("title"):
            enriched.append(issue)
            continue
        try:
            url = f"https://api.github.com/repos/{ORG}/{issue['repo']}/issues/{issue['number']}"
            data = gh_get(url)
            enriched.append({
                "repo": issue["repo"],
                "number": issue["number"],
                "title": data.get("title", ""),
                "url": issue["url"],
                "state": issue.get("state", data.get("state", "open")),
                "file": issue.get("file", ""),
            })
        except Exception:
            enriched.append(issue)
    return enriched


def fetch_commits(repo, since_iso):
    """Get commits by dream-hermes-agent since a given ISO timestamp."""
    url = (
        f"https://api.github.com/repos/{ORG}/{repo}/commits"
        f"?author=dream-hermes-agent&since={since_iso}&per_page=100"
    )
    data = gh_get(url)
    commits = []
    for item in data:
        c = item["commit"]
        commits.append({
            "repo": repo,
            "sha": item["sha"][:7],
            "message": c["message"].split("\n")[0].strip()[:80],
            "url": item["html_url"],
            "date": c["author"]["date"][:10],
        })
    return commits


def fetch_merged_prs(repo, since_iso):
    """Get PRs merged by dream-hermes-agent since a given ISO timestamp."""
    url = (
        f"https://api.github.com/repos/{ORG}/{repo}/pulls"
        f"?state=closed&sort=updated&direction=desc&per_page=100"
    )
    data = gh_get(url)
    prs = []
    for pr in data:
        if pr.get("merged_at") and pr["merged_at"] >= since_iso:
            if pr.get("user", {}).get("login") == "dream-hermes-agent":
                prs.append({
                    "repo": repo,
                    "number": pr["number"],
                    "title": pr["title"][:100],
                    "url": pr["html_url"],
                    "merged_at": pr["merged_at"][:10],
                })
    return prs


def fetch_issues(repo, since_iso):
    """Get issues opened by dream-hermes-agent since a given ISO timestamp."""
    url = (
        f"https://api.github.com/repos/{ORG}/{repo}/issues"
        f"?creator=dream-hermes-agent&since={since_iso}&per_page=100&state=all"
    )
    data = gh_get(url)
    issues = []
    for issue in data:
        if issue.get("pull_request"):
            continue  # skip PRs
        issues.append({
            "repo": repo,
            "number": issue["number"],
            "title": issue["title"][:100],
            "url": issue["html_url"],
            "state": issue["state"],
            "created_at": issue["created_at"][:10],
        })
    return issues


def build_evidence_manifest(since_date_str):
    """
    Fetch all evidence for ORG repos since YYYY-MM-DD.

    Combines two sources:
    1. GitHub API — for author-attributed commits (misses pushes from other machines)
    2. Session scanner — for git push output and gh repo create events (ground truth)

    The session scanner is authoritative; API results fill in metadata (author, date).
    """
    since_iso = f"{since_date_str}T00:00:00Z"

    # ── Source 1: Session scanner (authoritative for BWD org) ──────────────
    session_events = scan_sessions_for_gh_events(since_date_str)

    pushes_from_sessions = session_events["pushes"]
    repos_created = session_events["repos_created"]
    issues_from_sessions = session_events["issues"]

    # Resolve commit metadata via API
    resolved_commits = resolve_commits_via_api(pushes_from_sessions) if pushes_from_sessions else []

    # ── Source 2: GitHub API (for author-attributed data) ─────────────────
    all_commits = []
    all_prs = []
    all_issues = []

    for repo in REPOS:
        try:
            all_commits.extend(fetch_commits(repo, since_iso))
        except Exception as e:
            print(f"[Evidence] Commits failed for {repo}: {e}", file=sys.stderr)

        try:
            all_prs.extend(fetch_merged_prs(repo, since_iso))
        except Exception as e:
            print(f"[Evidence] PRs failed for {repo}: {e}", file=sys.stderr)

        try:
            all_issues.extend(fetch_issues(repo, since_iso))
        except Exception as e:
            print(f"[Evidence] Issues failed for {repo}: {e}", file=sys.stderr)

    # Deduplicate API commits by URL
    seen_commits = set()
    deduped_commits = []
    for c in all_commits:
        if c["url"] not in seen_commits:
            seen_commits.add(c["url"])
            deduped_commits.append(c)

    # ── Merge: session pushes are authoritative; API fills in metadata ──────
    # Build a SHA+repo lookup from API results for enrichment
    api_commit_lookup = {f"{c['repo']}@{c['sha']}": c for c in deduped_commits}

    final_commits = []
    for sc in resolved_commits:
        key = f"{sc['repo']}@{sc['sha']}"
        api_data = api_commit_lookup.get(key, {})
        final_commits.append({
            "repo": sc["repo"],
            "sha": sc["sha"],
            "message": sc["message"] or api_data.get("message", ""),
            "url": sc["url"],
            "date": sc["date"] or api_data.get("date", since_date_str),
            "author": sc.get("author", ""),
            "files_changed": sc.get("files_changed", 0),
        })

    # Add API-only commits (e.g. from other agents or automation)
    for c in deduped_commits:
        key = f"{c['repo']}@{c['sha']}"
        if key not in {f"{sc['repo']}@{sc['sha']}" for sc in resolved_commits}:
            final_commits.append(c)

    # Merge issues: session-scanned issues + API issues, deduplicated
    seen_issues = set()
    final_issues = []
    raw_issues = issues_from_sessions + all_issues
    for issue in raw_issues:
        key = f"{issue['repo']}@{issue.get('number', '')}"
        if key not in seen_issues:
            seen_issues.add(key)
            final_issues.append(issue)

    # Enrich issue titles via API where missing
    final_issues = enrich_issues_via_api(final_issues)

    # Enrich repo descriptions via API where missing
    repos_created = enrich_repos_via_api(repos_created)

    # ── Build repos_touched list ──────────────────────────────────────────
    all_repo_names = set(
        c["repo"] for c in final_commits
    ) | set(
        r["repo"] for r in repos_created
    ) | set(
        i["repo"] for i in final_issues
    ) | set(REPOS)  # Include tracked repos even if only referenced

    return {
        "date": since_date_str,
        "org": ORG,
        "repos_touched": sorted(all_repo_names),
        "commits": final_commits,
        "merged_prs": all_prs,
        "issues": final_issues,
        "repos_created": repos_created,
    }

def render_evidence_section(manifest):
    """
    Render evidence manifest as a structured changelog-style text block.
    Includes repos created, commits grouped by repo, and issues.
    """
    lines = []
    repos_created = manifest.get("repos_created", [])
    commits = manifest.get("commits", [])
    issues = manifest.get("issues", [])
    org = manifest.get("org", "BuildWithDreams")

    # ── Repos Created ────────────────────────────────────────────────────────
    if repos_created:
        lines.append(f"\n📦 **New Repos — {org}**")
        for r in repos_created:
            repo = r["repo"]
            desc = r.get("description", "Repository created") or "Repository created"
            lines.append(f"  • `+` **[{repo}]({r['url']})** — {desc}")

    # ── Changelog: Commits by repo ──────────────────────────────────────────
    commits_by_repo = defaultdict(list)
    for c in commits:
        commits_by_repo[c["repo"]].append(c)

    for repo, repo_commits in sorted(commits_by_repo.items()):
        lines.append(f"\n🛠️ **[{repo}](https://github.com/{org}/{repo})** — {len(repo_commits)} commit(s)")
        for c in sorted(repo_commits, key=lambda x: x.get("sha", "")):
            sha = c.get("sha", "?")[:7]
            msg = c.get("message", "")
            files = c.get("files_changed", 0)
            files_str = f" · {files} file(s)" if files else ""
            lines.append(f"  • `{sha}` {msg}{files_str}")
            lines.append(f"    [{c['url']}]({c['url']})")

    # ── PRs ──────────────────────────────────────────────────────────────────
    for pr in manifest.get("merged_prs", []):
        lines.append(f"\n🔀 **[PR #{pr['number']}]({pr['url']})** — {pr['title']}")

    # ── Issues ───────────────────────────────────────────────────────────────
    for issue in issues:
        icon = "✅" if issue.get("state") == "open" else "❌"
        lines.append(f"\n{icon} **[#{issue['number']}]({issue['url']})** — {issue.get('title', issue.get('msg', ''))}")

    if not lines:
        lines.append("\n_(No GitHub activity recorded this period)_")

    return "\n".join(lines)


if __name__ == "__main__":
    # Default: last 24 hours
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d")
    if len(sys.argv) > 1:
        since = sys.argv[1]

    if not GITHUB_TOKEN:
        print("[Evidence] ERROR: GITHUB_TOKEN or GITHUB_PAT not set", file=sys.stderr)
        sys.exit(1)

    manifest = build_evidence_manifest(since)

    # Write JSON manifest for downstream consumers
    out_path = os.path.expanduser("~/.hermes/scripts/session_evidence.json")
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Also print to stdout for cron log visibility
    repos = manifest["repos_touched"]
    repos_new = [r["repo"] for r in manifest.get("repos_created", [])]
    print(f"[Evidence] {len(manifest['commits'])} commits, {len(manifest['merged_prs'])} PRs, {len(manifest['issues'])} issues, {len(repos_new)} new repos")
    print(f"[Evidence] Repos touched: {', '.join(repos) or 'none'}")
    if repos_new:
        print(f"[Evidence] New repos: {', '.join(repos_new)}")
