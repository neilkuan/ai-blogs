#!/usr/bin/env python3
"""
Fetch only the new CHANGELOG.md content between two tags using GitHub Compare API.
Outputs upstream_changelog.md with only the added lines.
"""

import json
import os
import urllib.request

UPSTREAM_REPO = os.environ.get("UPSTREAM_REPO", "anthropics/claude-code")
GH_TOKEN = os.environ["GH_TOKEN"]
LAST_TAG = os.environ["LAST_TAG"]
LATEST_TAG = os.environ["LATEST_TAG"]
CHANGELOG_PATH = os.environ.get("CHANGELOG_PATH", "CHANGELOG.md")


def fetch_compare_diff():
    """Use GitHub Compare API to get CHANGELOG.md diff between two tags."""
    url = f"https://api.github.com/repos/{UPSTREAM_REPO}/compare/{LAST_TAG}...{LATEST_TAG}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    # Find CHANGELOG.md in the changed files
    for f in data.get("files", []):
        if f["filename"] == CHANGELOG_PATH:
            patch = f.get("patch", "")
            if not patch:
                print(f"⚠️ No patch content for {CHANGELOG_PATH}")
                return None
            return extract_additions(patch)

    print(f"⚠️ {CHANGELOG_PATH} not found in diff")
    return None


def extract_additions(patch: str) -> str:
    """Extract only added lines (starting with +) from a unified diff patch."""
    lines = []
    for line in patch.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])  # Remove the leading +
    return "\n".join(lines)


def fallback_full_download():
    """Fallback: download the full file if diff approach fails."""
    print("⚠️ Falling back to full CHANGELOG download")
    url = (
        f"https://api.github.com/repos/{UPSTREAM_REPO}"
        f"/contents/{CHANGELOG_PATH}?ref={LATEST_TAG}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github.raw+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def main():
    content = fetch_compare_diff()

    if not content or not content.strip():
        content = fallback_full_download()

    with open("upstream_changelog.md", "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Wrote {len(content)} chars to upstream_changelog.md")


if __name__ == "__main__":
    main()
