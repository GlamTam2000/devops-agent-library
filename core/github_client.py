"""
GitHub REST API client.

Uses plain `requests` rather than PyGithub to keep dependencies small and
make the exact API surface explicit — useful when porting to an enterprise
GitHub where endpoints or headers sometimes need to be adjusted.

The client is deliberately narrow: only the operations the PR agent
actually needs. Add methods as new agents come online.
"""

from __future__ import annotations

import os
from typing import Any

import requests


DEFAULT_API_URL = "https://api.github.com"
BOT_COMMENT_MARKER = "<!-- devops-agents:pr-agent -->"


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        api_url: str | None = None,
    ) -> None:
        resolved_token = token or os.environ.get("GITHUB_TOKEN")
        if not resolved_token:
            raise RuntimeError("GITHUB_TOKEN not set")
        # GHES uses a different base URL, e.g. https://github.mycorp.com/api/v3
        self.api_url = (api_url or os.environ.get("GITHUB_API_URL") or DEFAULT_API_URL).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {resolved_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "devops-agents/0.1",
            }
        )

    # ------------------------------------------------------------------ PR reads

    def get_pr(self, repo: str, pr_number: int) -> dict[str, Any]:
        r = self._session.get(f"{self.api_url}/repos/{repo}/pulls/{pr_number}")
        r.raise_for_status()
        return r.json()

    def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Fetch the PR as a unified diff (text)."""
        r = self._session.get(
            f"{self.api_url}/repos/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        r.raise_for_status()
        return r.text

    def get_pr_files(self, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """List files changed in the PR (paginated; we cap at 300 for sanity)."""
        files: list[dict[str, Any]] = []
        page = 1
        while page <= 3:  # max 300 files; anything bigger is a human-review PR
            r = self._session.get(
                f"{self.api_url}/repos/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    # ------------------------------------------------------------------ Comments

    def find_bot_comment(
        self, repo: str, pr_number: int, marker: str = BOT_COMMENT_MARKER
    ) -> dict[str, Any] | None:
        """Find the agent's existing comment so we can edit in place instead of spamming new ones."""
        r = self._session.get(
            f"{self.api_url}/repos/{repo}/issues/{pr_number}/comments",
            params={"per_page": 100},
        )
        r.raise_for_status()
        for comment in r.json():
            if marker in (comment.get("body") or ""):
                return comment
        return None

    def post_comment(self, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        r = self._session.post(
            f"{self.api_url}/repos/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        r.raise_for_status()
        return r.json()

    def update_comment(self, repo: str, comment_id: int, body: str) -> dict[str, Any]:
        r = self._session.patch(
            f"{self.api_url}/repos/{repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        r.raise_for_status()
        return r.json()

    def upsert_bot_comment(self, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        """Update the agent's comment if it exists, otherwise post a new one."""
        existing = self.find_bot_comment(repo, pr_number)
        if existing:
            return self.update_comment(repo, existing["id"], body)
        return self.post_comment(repo, pr_number, body)
