from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class SalesforceConnector(BaseConnector):
    """Connector for Salesforce REST API using OAuth 2.0 bearer tokens."""

    vendor: str = "salesforce"

    def __init__(
        self,
        token: str | None = None,
        instance_url: str = "",
        **kwargs,
    ):
        super().__init__(token=token, base_url=instance_url, **kwargs)
        self.instance_url = instance_url.rstrip("/") if instance_url else ""

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        if not self.is_enabled():
            return self._mock_response(method, path)
        return await super()._request(method, path, **kwargs)

    async def create_lead(self, lead_data: dict[str, Any]) -> dict:
        """Create a lead in Salesforce."""
        if not self.is_enabled():
            raise ConnectorDisabled("Salesforce connector is disabled – provide a token")
        return await self.post("/services/data/v59.0/sobjects/Lead", json=lead_data)

    async def create_opportunity(self, opp_data: dict[str, Any]) -> dict:
        """Create an opportunity in Salesforce."""
        if not self.is_enabled():
            raise ConnectorDisabled("Salesforce connector is disabled – provide a token")
        return await self.post("/services/data/v59.0/sobjects/Opportunity", json=opp_data)

    async def soql_query(self, query: str) -> list[dict]:
        """Execute a SOQL query and return the list of records."""
        if not self.is_enabled():
            raise ConnectorDisabled("Salesforce connector is disabled – provide a token")
        result = await self.get(
            "/services/data/v59.0/query",
            params={"q": query},
        )
        return result.get("records", [])

    async def get_sobject(self, sobject_type: str, record_id: str) -> dict:
        """Retrieve a single SObject record by ID."""
        if not self.is_enabled():
            raise ConnectorDisabled("Salesforce connector is disabled – provide a token")
        return await self.get(f"/services/data/v59.0/sobjects/{sobject_type}/{record_id}")

    async def update_sobject(
        self, sobject_type: str, record_id: str, data: dict[str, Any]
    ) -> None:
        """Update an SObject record. Returns None on success."""
        if not self.is_enabled():
            raise ConnectorDisabled("Salesforce connector is disabled – provide a token")
        await self.patch(f"/services/data/v59.0/sobjects/{sobject_type}/{record_id}", json=data)
