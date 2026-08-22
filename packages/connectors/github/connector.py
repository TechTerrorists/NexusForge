from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class GitHubConnector(BaseConnector):
    """Connector for GitHub REST API v3."""

    vendor: str = "github"

    def __init__(self, token: str | None = None, **kwargs):
        super().__init__(token=token, base_url="https://api.github.com", **kwargs)

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def create_issue(
        self, owner: str, repo: str, title: str, body: str, **kwargs
    ) -> dict:
        """Create an issue on a GitHub repository."""
        if not self.is_enabled():
            raise ConnectorDisabled("GitHub connector is disabled – provide a token")
        payload = {"title": title, "body": body, **kwargs}
        return await self.post(f"/repos/{owner}/{repo}/issues", json=payload)

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str,
        **kwargs,
    ) -> dict:
        """Create a pull request on a GitHub repository."""
        if not self.is_enabled():
            raise ConnectorDisabled("GitHub connector is disabled – provide a token")
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            **kwargs,
        }
        return await self.post(f"/repos/{owner}/{repo}/pulls", json=payload)

    async def get_repo(self, owner: str, repo: str) -> dict:
        """Get repository information."""
        if not self.is_enabled():
            raise ConnectorDisabled("GitHub connector is disabled – provide a token")
        return await self.get(f"/repos/{owner}/{repo}")

    async def list_issues(
        self, owner: str, repo: str, state: str = "open", per_page: int = 30
    ) -> list[dict]:
        """List issues for a repository."""
        if not self.is_enabled():
            raise ConnectorDisabled("GitHub connector is disabled – provide a token")
        params = {"state": state, "per_page": per_page}
        return await self.get(f"/repos/{owner}/{repo}/issues", params=params)

    async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict:
        """Get a pull request by number."""
        if not self.is_enabled():
            raise ConnectorDisabled("GitHub connector is disabled – provide a token")
        return await self.get(f"/repos/{owner}/{repo}/pulls/{pull_number}")

    async def create_comment(
        self, owner: str, repo: str, issue_number: int, body: str
    ) -> dict:
        """Create a comment on an issue or pull request."""
        if not self.is_enabled():
            raise ConnectorDisabled("GitHub connector is disabled – provide a token")
        payload = {"body": body}
        return await self.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments", json=payload
        )
