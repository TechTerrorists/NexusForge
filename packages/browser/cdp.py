import json
import logging
import base64
from typing import Any, Optional

import httpx

from .isolation import BrowserProfile

logger = logging.getLogger(__name__)


class CDPClient:
    def __init__(self, profile: BrowserProfile, base_url: str = "http://127.0.0.1:9222"):
        self._profile = profile
        self._base_url = base_url
        self._http_client: Optional[httpx.AsyncClient] = None
        self._message_id = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=30.0,
            )
        return self._http_client

    async def _send_command(
        self, method: str, params: dict[str, Any] = None
    ) -> dict[str, Any]:
        client = await self._get_client()
        self._message_id += 1
        payload = {
            "id": self._message_id,
            "method": method,
            "params": params or {},
        }

        tabs = await self._get_tabs()
        if not tabs:
            raise ConnectionError("No browser tabs available")

        ws_url = tabs[0].get("webSocketDebuggerUrl")
        if not ws_url:
            raise ConnectionError("No WebSocket URL available for tab")

        try:
            http_url = ws_url.replace("ws://", "http://")
            response = await client.post(http_url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"CDP command failed: {method} - {e}")
            raise

    async def _get_tabs(self) -> list[dict[str, Any]]:
        client = await self._get_client()
        try:
            response = await client.get("/json")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get browser tabs: {e}")
            return []

    async def navigate(self, url: str) -> dict[str, Any]:
        result = await self._send_command("Page.navigate", {"url": url})
        logger.info(f"Navigated to {url}")
        return result

    async def click(self, selector: str) -> dict[str, Any]:
        escaped = selector.replace("\\", "\\\\").replace('"', '\\"')
        js = (
            '(function() {'
            'var el = document.querySelector("' + escaped + '");'
            'if (!el) throw new Error("Element not found: ' + escaped + '");'
            'el.click();'
            'return {clicked: true, selector: "' + escaped + '"};'
            '})()'
        )
        return await self.evaluate(js)

    async def type_text(self, selector: str, text: str) -> dict[str, Any]:
        esc_sel = selector.replace("\\", "\\\\").replace('"', '\\"')
        esc_txt = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        js = (
            '(function() {'
            'var el = document.querySelector("' + esc_sel + '");'
            'if (!el) throw new Error("Element not found");'
            'el.focus();'
            'el.value = "' + esc_txt + '";'
            'el.dispatchEvent(new Event("input", {bubbles: true}));'
            'el.dispatchEvent(new Event("change", {bubbles: true}));'
            'return {typed: true};'
            '})()'
        )
        return await self.evaluate(js)

    async def screenshot(self, format: str = "png", quality: int = 80) -> bytes:
        client = await self._get_client()
        self._message_id += 1
        tabs = await self._get_tabs()
        if not tabs:
            raise ConnectionError("No browser tabs available")
        ws_url = tabs[0].get("webSocketDebuggerUrl")
        if not ws_url:
            raise ConnectionError("No WebSocket URL available for tab")
        try:
            http_url = ws_url.replace("ws://", "http://")
            params: dict[str, Any] = {"format": format}
            if format == "jpeg":
                params["quality"] = quality
            response = await client.post(
                http_url,
                json={
                    "id": self._message_id,
                    "method": "Page.captureScreenshot",
                    "params": params,
                },
            )
            response.raise_for_status()
            result = response.json()
            if "result" in result and "data" in result["result"]:
                return base64.b64decode(result["result"]["data"])
            raise RuntimeError(f"Screenshot failed: {result}")
        except httpx.HTTPError as e:
            logger.error(f"Screenshot failed: {e}")
            raise

    async def evaluate(self, expression: str) -> Any:
        result = await self._send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "result" in result:
            remote_result = result["result"]
            if "result" in remote_result:
                return remote_result["result"].get("value")
            return remote_result
        return result

    async def get_page_content(self) -> str:
        result = await self.evaluate("document.documentElement.outerHTML")
        if isinstance(result, str):
            return result
        return str(result)

    async def get_current_url(self) -> str:
        result = await self.evaluate("window.location.href")
        if isinstance(result, str):
            return result
        return str(result)

    async def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> bool:
        escaped = selector.replace("\\", "\\\\").replace('"', '\\"')
        js = (
            '(function() {'
            'return new Promise(function(resolve) {'
            'var el = document.querySelector("' + escaped + '");'
            'if (el) { resolve(true); return; }'
            'var observer = new MutationObserver(function() {'
            'var el2 = document.querySelector("' + escaped + '");'
            'if (el2) { observer.disconnect(); resolve(true); }'
            '});'
            'observer.observe(document.body, {childList: true, subtree: true});'
            'setTimeout(function() { observer.disconnect(); resolve(false); }, '
            + str(timeout_ms) + ');'
            '});'
            '})()'
        )
        result = await self.evaluate(js)
        return bool(result)

    async def scroll_to_bottom(self) -> dict[str, Any]:
        js = "window.scrollTo(0, document.body.scrollHeight); ({scrolled: true})"
        result = await self.evaluate(js)
        return result if isinstance(result, dict) else {"scrolled": True}

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
