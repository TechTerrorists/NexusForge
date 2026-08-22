from __future__ import annotations

from typing import Any

from ..base import BaseConnector, ConnectorDisabled


class SAPConnector(BaseConnector):
    """Connector for SAP S/4HANA OData API with CSRF token management."""

    vendor: str = "sap"

    def __init__(self, token: str | None = None, base_url: str = "", **kwargs):
        super().__init__(token=token, base_url=base_url, **kwargs)
        self._csrf_token: str | None = None
        self._csrf_header: str | None = None

    def auth_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _fetch_csrf_token(self) -> None:
        """Fetch a new CSRF token from SAP."""
        import httpx

        url = f"{self.base_url}/sap/opu/odata/sap/API_SALES_ORDER_SRV/"
        headers = {
            **self.auth_header(),
            "X-CSRF-Token": "Fetch",
            "x-http-method-override": "GET",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=False) as client:
            response = await client.get(url, headers=headers)
            self._csrf_token = response.headers.get("x-csrf-token")
            self._csrf_header = response.headers.get("x-sap-csrf-token", "x-csrf-token")

    def _csrf_headers(self) -> dict[str, str]:
        """Return headers for CSRF-protected requests."""
        if not self._csrf_token:
            return {}
        header_name = self._csrf_header or "x-csrf-token"
        return {header_name: self._csrf_token}

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        if not self.is_enabled():
            return self._mock_response(method, path)

        if method in ("POST", "PUT", "PATCH", "DELETE") and not self._csrf_token:
            await self._fetch_csrf_token()

        extra_headers = kwargs.pop("extra_headers", None) or {}
        extra_headers.update(self._csrf_headers())

        try:
            return await super()._request(method, path, extra_headers=extra_headers, **kwargs)
        except Exception:
            self._csrf_token = None
            raise

    async def get_orders(self) -> list[dict]:
        """Retrieve sales orders from SAP."""
        if not self.is_enabled():
            raise ConnectorDisabled("SAP connector is disabled – provide a token")
        result = await self.get(
            "/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder",
            params={"$format": "json", "$top": "100"},
        )
        return result.get("d", {}).get("results", [])

    async def create_order(self, order_data: dict[str, Any]) -> dict:
        """Create a sales order in SAP."""
        if not self.is_enabled():
            raise ConnectorDisabled("SAP connector is disabled – provide a token")
        return await self.post(
            "/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder",
            json=order_data,
        )

    async def get_invoices(self) -> list[dict]:
        """Retrieve invoices from SAP."""
        if not self.is_enabled():
            raise ConnectorDisabled("SAP connector is disabled – provide a token")
        result = await self.get(
            "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV/A_BillingDocument",
            params={"$format": "json", "$top": "100"},
        )
        return result.get("d", {}).get("results", [])

    async def get_purchase_orders(self) -> list[dict]:
        """Retrieve purchase orders from SAP."""
        if not self.is_enabled():
            raise ConnectorDisabled("SAP connector is disabled – provide a token")
        result = await self.get(
            "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder",
            params={"$format": "json", "$top": "100"},
        )
        return result.get("d", {}).get("results", [])

    async def get_materials(self) -> list[dict]:
        """Retrieve material master data from SAP."""
        if not self.is_enabled():
            raise ConnectorDisabled("SAP connector is disabled – provide a token")
        result = await self.get(
            "/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product",
            params={"$format": "json", "$top": "100"},
        )
        return result.get("d", {}).get("results", [])
