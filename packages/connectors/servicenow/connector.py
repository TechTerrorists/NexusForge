from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class ServiceNowConnector(BaseConnector):
    """Connector for ServiceNow REST API (Table API)."""

    vendor: str = "servicenow"

    def __init__(self, token: str | None = None, base_url: str = "", **kwargs):
        super().__init__(token=token, base_url=base_url, **kwargs)

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_incident(
        self,
        short_description: str,
        description: str = "",
        urgency: str = "2",
        impact: str = "2",
        assignment_group: str = "",
        **kwargs,
    ) -> dict:
        """Create an incident in ServiceNow."""
        if not self.is_enabled():
            raise ConnectorDisabled("ServiceNow connector is disabled – provide a token")
        payload = {
            "short_description": short_description,
            "description": description,
            "urgency": urgency,
            "impact": impact,
            "state": "1",
            **kwargs,
        }
        if assignment_group:
            payload["assignment_group"] = assignment_group
        return await self.post("/api/now/table/incident", json=payload)

    async def create_change_request(self, change_data: dict[str, Any]) -> dict:
        """Create a change request in ServiceNow."""
        if not self.is_enabled():
            raise ConnectorDisabled("ServiceNow connector is disabled – provide a token")
        payload = {
            "type": "standard",
            "state": "-5",
            **change_data,
        }
        return await self.post("/api/now/table/change_request", json=payload)

    async def query_table(
        self,
        table: str,
        query: str = "",
        limit: int = 100,
        fields: str = "",
    ) -> list[dict]:
        """Query any ServiceNow table with an encoded query string."""
        if not self.is_enabled():
            raise ConnectorDisabled("ServiceNow connector is disabled – provide a token")
        params: dict[str, Any] = {"sysparm_limit": limit}
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = fields
        result = await self.get(f"/api/now/table/{table}", params=params)
        return result.get("result", [])

    async def get_record(self, table: str, sys_id: str) -> dict:
        """Get a single record by sys_id."""
        if not self.is_enabled():
            raise ConnectorDisabled("ServiceNow connector is disabled – provide a token")
        result = await self.get(f"/api/now/table/{table}/{sys_id}")
        return result.get("result", {})

    async def update_record(
        self, table: str, sys_id: str, data: dict[str, Any]
    ) -> dict:
        """Update a record by sys_id."""
        if not self.is_enabled():
            raise ConnectorDisabled("ServiceNow connector is disabled – provide a token")
        result = await self.put(f"/api/now/table/{table}/{sys_id}", json=data)
        return result.get("result", {})
