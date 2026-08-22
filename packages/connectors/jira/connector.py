from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class JiraConnector(BaseConnector):
    """Connector for Jira Cloud REST API v3."""

    vendor: str = "jira"

    def __init__(self, token: str | None = None, base_url: str = "", **kwargs):
        super().__init__(token=token, base_url=base_url, **kwargs)

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def create_issue(
        self,
        project: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
        **fields,
    ) -> dict:
        """Create an issue in a Jira project."""
        if not self.is_enabled():
            raise ConnectorDisabled("Jira connector is disabled – provide a token")
        payload = {
            "fields": {
                "project": {"key": project},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                },
                "issuetype": {"name": issue_type},
                **fields,
            }
        }
        return await self.post("/rest/api/3/issue", json=payload)

    async def transition_issue(self, issue_key: str, transition_id: str) -> dict:
        """Transition an issue to a new status."""
        if not self.is_enabled():
            raise ConnectorDisabled("Jira connector is disabled – provide a token")
        payload = {"transition": {"id": transition_id}}
        return await self.post(
            f"/rest/api/3/issue/{issue_key}/transitions", json=payload
        )

    async def get_issue(self, issue_key: str, fields: str | None = None) -> dict:
        """Retrieve an issue by key with optional field filtering."""
        if not self.is_enabled():
            raise ConnectorDisabled("Jira connector is disabled – provide a token")
        params = {}
        if fields:
            params["fields"] = fields
        return await self.get(f"/rest/api/3/issue/{issue_key}", params=params)

    async def search_issues(self, jql: str, max_results: int = 50) -> list[dict]:
        """Search for issues using JQL."""
        if not self.is_enabled():
            raise ConnectorDisabled("Jira connector is disabled – provide a token")
        payload = {"jql": jql, "maxResults": max_results}
        result = await self.post("/rest/api/3/search", json=payload)
        return result.get("issues", [])

    async def add_comment(self, issue_key: str, body: str) -> dict:
        """Add a comment to an issue."""
        if not self.is_enabled():
            raise ConnectorDisabled("Jira connector is disabled – provide a token")
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        return await self.post(
            f"/rest/api/3/issue/{issue_key}/comment", json=payload
        )
