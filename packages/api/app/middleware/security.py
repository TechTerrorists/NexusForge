from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

if TYPE_CHECKING:
    from starlette.requests import Request

PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("phone", re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("date_of_birth", re.compile(r"\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/\d{4}\b")),
]

PROMPT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|system\|>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"###\s*system", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you", re.IGNORECASE),
    re.compile(r"pretend\s+(you|that|to)\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(all|any|previous|your)\s+", re.IGNORECASE),
    re.compile(r"override\s+(your|the|all)\s+", re.IGNORECASE),
    re.compile(r"\bDAN\b.*\bmode\b", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"<\|endoftext\|>", re.IGNORECASE),
]


class SecurityMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = frozenset({"/health", "/metrics", "/docs", "/redoc", "/openapi.json"})

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            body = await request.body()
            if body:
                try:
                    json_body = json.loads(body)
                    risk_level = self._analyze_request(json_body)

                    if risk_level == "high":
                        return JSONResponse(
                            status_code=400,
                            content={
                                "detail": "Request blocked due to security policy violation",
                                "code": "SECURITY_VIOLATION",
                            },
                        )

                    # Preserve a redacted copy for observability without
                    # changing the payload consumed by route handlers. UUIDs,
                    # emails, and other valid application data can resemble
                    # PII patterns and must not be silently corrupted.
                    request.state.sanitized_body = self._redact_pii(json_body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

        response = await call_next(request)
        return response

    def _analyze_request(self, data: Any) -> str:
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, str):
                    risk = self._scan_text(value)
                    if risk == "high":
                        return "high"
                elif isinstance(value, (dict, list)):
                    nested_risk = self._analyze_request(value)
                    if nested_risk == "high":
                        return "high"
        elif isinstance(data, list):
            for item in data:
                risk = self._analyze_request(item)
                if risk == "high":
                    return "high"
        return "low"

    def _scan_text(self, text: str) -> str:
        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                return "high"
        return "low"

    def _redact_pii(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: self._redact_pii(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._redact_pii(item) for item in data]
        elif isinstance(data, str):
            return self._redact_text(data)
        return data

    def _redact_text(self, text: str) -> str:
        redacted = text
        for pii_type, pattern in PII_PATTERNS:
            if pii_type == "email":
                redacted = pattern.sub("[REDACTED_EMAIL]", redacted)
            elif pii_type == "phone":
                redacted = pattern.sub("[REDACTED_PHONE]", redacted)
            elif pii_type == "ssn":
                redacted = pattern.sub("[REDACTED_SSN]", redacted)
            elif pii_type == "credit_card":
                redacted = pattern.sub("[REDACTED_CC]", redacted)
            elif pii_type == "ip_address":
                redacted = pattern.sub("[REDACTED_IP]", redacted)
            elif pii_type == "date_of_birth":
                redacted = pattern.sub("[REDACTED_DOB]", redacted)
        return redacted
