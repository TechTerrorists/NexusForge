from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class HubSpotConnector(BaseConnector):
    """Connector for HubSpot CRM API v3."""

    vendor: str = "hubspot"

    def __init__(self, token: str | None = None, **kwargs):
        super().__init__(token=token, base_url="https://api.hubapi.com", **kwargs)

    async def upsert_contact(self, email: str, properties: dict[str, Any]) -> dict:
        """Create or update a contact by email using the CRM Associations upsert endpoint."""
        if not self.is_enabled():
            raise ConnectorDisabled("HubSpot connector is disabled – provide a token")
        payload = {
            "properties": {"email": email, **properties},
        }
        search_payload = {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "email", "operator": "EQ", "value": email}
                    ]
                }
            ],
            "properties": ["email"],
            "limit": 1,
        }
        search_result = await self.post(
            "/crm/v3/objects/contacts/search", json=search_payload
        )
        contacts = search_result.get("results", [])
        if contacts:
            contact_id = contacts[0]["id"]
            return await self.patch(
                f"/crm/v3/objects/contacts/{contact_id}", json=payload
            )
        return await self.post("/crm/v3/objects/contacts", json=payload)

    async def create_deal(self, contact_id: str, deal_data: dict[str, Any]) -> dict:
        """Create a deal and associate it with a contact."""
        if not self.is_enabled():
            raise ConnectorDisabled("HubSpot connector is disabled – provide a token")
        deal_payload = {"properties": deal_data}
        deal_result = await self.post("/crm/v3/objects/deals", json=deal_payload)
        deal_id = deal_result.get("id")
        if deal_id:
            await self._associate_objects(
                "deals", deal_id, "contacts", contact_id, "deal_to_contact"
            )
        return deal_result

    async def add_note(self, contact_id: str, note_body: str) -> dict:
        """Attach a note to a contact via the Engagements API."""
        if not self.is_enabled():
            raise ConnectorDisabled("HubSpot connector is disabled – provide a token")
        note_payload = {
            "properties": {
                "hs_note_body": note_body,
                "hs_timestamp": str(int(__import__("time").time() * 1000)),
            }
        }
        note_result = await self.post(
            "/crm/v3/objects/notes", json=note_payload
        )
        note_id = note_result.get("id")
        if note_id and contact_id:
            await self._associate_objects(
                "notes", note_id, "contacts", contact_id, "note_to_contact"
            )
        return note_result

    async def search_contacts(self, query: str) -> list[dict]:
        """Search contacts by email or name using the search endpoint."""
        if not self.is_enabled():
            raise ConnectorDisabled("HubSpot connector is disabled – provide a token")
        search_payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                },
                {
                    "filters": [
                        {
                            "propertyName": "firstname",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                },
            ],
            "properties": ["email", "firstname", "lastname", "company", "phone"],
            "limit": 50,
        }
        result = await self.post("/crm/v3/objects/contacts/search", json=search_payload)
        return result.get("results", [])

    async def _associate_objects(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        association_type: str,
    ) -> dict:
        """Create an association between two CRM objects."""
        path = (
            f"/crm/v3/objects/{from_type}/{from_id}"
            f"/associations/{to_type}/{to_id}/{association_type}"
        )
        return await self.put(path)
