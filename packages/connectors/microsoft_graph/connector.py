from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class MicrosoftGraphConnector(BaseConnector):
    """Connector for Microsoft Graph API v1.0."""

    vendor: str = "microsoft_graph"

    def __init__(self, token: str | None = None, **kwargs):
        super().__init__(token=token, base_url="https://graph.microsoft.com/v1.0", **kwargs)

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def send_email(
        self,
        to: list[str] | str,
        subject: str,
        body: str,
        content_type: str = "HTML",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict:
        """Send an email via Microsoft Graph."""
        if not self.is_enabled():
            raise ConnectorDisabled("Microsoft Graph connector is disabled – provide a token")
        if isinstance(to, str):
            to = [to]
        message = {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in to
            ],
        }
        if cc:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc
            ]
        if bcc:
            message["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in bcc
            ]
        payload = {"message": message, "saveToSentItems": "true"}
        return await self.post("/me/sendMail", json=payload)

    async def create_calendar_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: list[str] | None = None,
        body: str = "",
        location: str = "",
        is_online: bool = True,
    ) -> dict:
        """Create a calendar event in the user's default calendar.
        
        Args:
            subject: Event title.
            start: ISO 8601 start datetime (e.g., '2025-01-15T10:00:00').
            end: ISO 8601 end datetime.
            attendees: List of email addresses.
            body: Event description.
            location: Location name or address.
            is_online: Whether to create an online meeting.
        """
        if not self.is_enabled():
            raise ConnectorDisabled("Microsoft Graph connector is disabled – provide a token")
        event_payload: dict[str, Any] = {
            "subject": subject,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
            "isOnlineMeeting": is_online,
            "onlineMeetingProvider": "teamsForBusiness" if is_online else None,
        }
        if body:
            event_payload["body"] = {"contentType": "HTML", "content": body}
        if location:
            event_payload["location"] = {"displayName": location}
        if attendees:
            event_payload["attendees"] = [
                {
                    "emailAddress": {"address": addr, "name": addr.split("@")[0]},
                    "type": "required",
                }
                for addr in attendees
            ]
        return await self.post("/me/events", json=event_payload)

    async def send_teams_message(
        self,
        team_id: str,
        channel_id: str,
        message: str,
        content_type: str = "html",
    ) -> dict:
        """Send a message to a Microsoft Teams channel."""
        if not self.is_enabled():
            raise ConnectorDisabled("Microsoft Graph connector is disabled – provide a token")
        payload = {
            "body": {
                "contentType": content_type,
                "content": message,
            }
        }
        return await self.post(
            f"/teams/{team_id}/channels/{channel_id}/messages",
            json=payload,
        )

    async def get_my_profile(self) -> dict:
        """Get the current user's profile."""
        if not self.is_enabled():
            raise ConnectorDisabled("Microsoft Graph connector is disabled – provide a token")
        return await self.get("/me")

    async def list_calendar_events(self, top: int = 10) -> list[dict]:
        """List upcoming calendar events."""
        if not self.is_enabled():
            raise ConnectorDisabled("Microsoft Graph connector is disabled – provide a token")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        params = {
            "$filter": f"start/dateTime ge '{now}'",
            "$orderby": "start/dateTime",
            "$top": str(top),
            "$select": "subject,start,end,attendees,location,isOnlineMeeting",
        }
        result = await self.get("/me/events", params=params)
        return result.get("value", [])

    async def list_teams(self) -> list[dict]:
        """List teams the user is a member of."""
        if not self.is_enabled():
            raise ConnectorDisabled("Microsoft Graph connector is disabled – provide a token")
        result = await self.get("/me/joinedTeams")
        return result.get("value", [])
