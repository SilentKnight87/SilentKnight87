#!/usr/bin/env python3
"""Generate the GitHub profile README from profile-index.json.

Design choice: this script only publishes repos explicitly listed in the manifest.
It may query GitHub to refresh visibility/fork metadata, but it will not auto-add
new private repo names to a public profile. Surprise privacy leaks are a dumb way
to automate a README.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "profile-index.json"
DEFAULT_README = ROOT / "README.md"
PRIVATE_MARK = " 🔒"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def github_get(owner: str, repo: str, token: str | None) -> dict[str, Any] | None:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "SilentKnight87-profile-index-updater",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in {401, 403, 404}:
            return None
        raise


def enrich_repo(owner: str, item: dict[str, Any], token: str | None, refresh: bool) -> dict[str, Any]:
    repo = dict(item)
    if not refresh:
        return repo

    data = github_get(owner, repo["name"], token)
    if not data:
        return repo

    # API metadata wins when accessible. Manifest remains the fallback when a
    # private repo is not visible to the workflow token.
    repo["private"] = bool(data.get("private", repo.get("private", False)))
    repo["html_url"] = data.get("html_url") or repo.get("html_url")
    if data.get("fork") and not repo.get("suffix"):
        repo["suffix"] = "fork"
    return repo


def render_repo(owner: str, repo: dict[str, Any]) -> str:
    name = repo["name"]
    emoji = repo.get("emoji", "•")
    url = repo.get("html_url") or f"https://github.com/{owner}/{name}"
    suffix = f" {repo['suffix']}" if repo.get("suffix") else ""
    private = PRIVATE_MARK if repo.get("private") else ""
    description = repo.get("description", "").strip()
    return f"| {emoji} [`{name}`]({url}){suffix}{private} | {description} |"


def render(manifest: dict[str, Any], *, refresh: bool, token: str | None) -> str:
    owner = manifest["owner"]
    profile = manifest["profile"]
    excluded = set(manifest.get("exclude", []))
    lines: list[str] = []

    lines.extend([
        f"# {profile['title']}",
        "",
        profile["tagline"],
        "",
        profile["note"],
        "",
        f"> {profile['legend']}",
        "",
    ])

    for section in manifest["sections"]:
        visible_repos = [r for r in section["repos"] if r["name"] not in excluded]
        if not visible_repos:
            continue

        lines.extend([
            f"## {section['title']}",
            "",
            "| Repo | What it is |",
            "| --- | --- |",
        ])
        for item in visible_repos:
            repo = enrich_repo(owner, item, token, refresh)
            if repo["name"] in excluded:
                continue
            lines.append(render_repo(owner, repo))
        lines.append("")

    lines.extend([
        "## Current build thesis",
        "",
        profile["thesis"],
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update the profile README from profile-index.json")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--check", action="store_true", help="fail if README is not already up to date")
    parser.add_argument("--no-refresh", action="store_true", help="do not query GitHub for repo metadata")
    args = parser.parse_args()

    token = os.environ.get("GH_PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN")
    manifest = load_json(args.manifest)
    readme = render(manifest, refresh=not args.no_refresh, token=token)

    current = args.readme.read_text(encoding="utf-8") if args.readme.exists() else ""
    if current == readme:
        print("README.md is up to date")
        return 0

    if args.check:
        print("README.md is out of date. Run: python3 scripts/update_profile_readme.py", file=sys.stderr)
        return 1

    args.readme.write_text(readme, encoding="utf-8")
    print(f"Updated {args.readme.relative_to(ROOT)} at {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
