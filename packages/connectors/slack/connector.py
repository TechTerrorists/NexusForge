from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class SlackConnector(BaseConnector):
    """Connector for Slack Web API."""

    vendor: str = "slack"

    def __init__(self, token: str | None = None, **kwargs):
        super().__init__(token=token, base_url="https://slack.com/api", **kwargs)

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
    ) -> dict:
        """Send a message to a Slack channel or thread."""
        if not self.is_enabled():
            raise ConnectorDisabled("Slack connector is disabled – provide a token")
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts
        result = await self.post("/chat.postMessage", json=payload)
        if not result.get("ok"):
            error = result.get("error", "unknown_error")
            raise ConnectorDisabled(f"Slack API error: {error}")
        return result

    async def create_channel(
        self, name: str, is_private: bool = False
    ) -> dict:
        """Create a new Slack channel."""
        if not self.is_enabled():
            raise ConnectorDisabled("Slack connector is disabled – provide a token")
        endpoint = "/conversations.create" if not is_private else "/conversations.create"
        payload = {"name": name, "is_private": is_private}
        result = await self.post(endpoint, json=payload)
        if not result.get("ok"):
            error = result.get("error", "unknown_error")
            raise ConnectorDisabled(f"Slack API error: {error}")
        return result

    async def list_channels(self, limit: int = 100) -> list[dict]:
        """List channels the bot has access to."""
        if not self.is_enabled():
            raise ConnectorDisabled("Slack connector is disabled – provide a token")
        params = {"types": "public_channel,private_channel", "limit": limit}
        result = await self.get("/conversations.list", params=params)
        if not result.get("ok"):
            error = result.get("error", "unknown_error")
            raise ConnectorDisabled(f"Slack API error: {error}")
        return result.get("channels", [])

    async def join_channel(self, channel: str) -> dict:
        """Join a Slack channel."""
        if not self.is_enabled():
            raise ConnectorDisabled("Slack connector is disabled – provide a token")
        payload = {"channel": channel}
        result = await self.post("/conversations.join", json=payload)
        if not result.get("ok"):
            error = result.get("error", "unknown_error")
            raise ConnectorDisabled(f"Slack API error: {error}")
        return result

    async def get_channel_info(self, channel: str) -> dict:
        """Get information about a channel."""
        if not self.is_enabled():
            raise ConnectorDisabled("Slack connector is disabled – provide a token")
        params = {"channel": channel}
        result = await self.get("/conversations.info", params=params)
        if not result.get("ok"):
            error = result.get("error", "unknown_error")
            raise ConnectorDisabled(f"Slack API error: {error}")
        return result.get("channel", {})
