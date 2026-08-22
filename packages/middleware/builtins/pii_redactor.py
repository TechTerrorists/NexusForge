"""PIIRedactorMiddleware — scrubs PII from user messages before model calls."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from packages.middleware.pipeline import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Luhn validation                                                               #
# --------------------------------------------------------------------------- #

def _luhn_check(number: str) -> bool:
    """Validate a card number via the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# --------------------------------------------------------------------------- #
# PII patterns                                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class PIIPattern:
    category: str
    pattern: re.Pattern[str]
    luhn_validated: bool = False


PII_PATTERNS: list[PIIPattern] = [
    PIIPattern("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    PIIPattern("phone", re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")),
    PIIPattern("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    PIIPattern("credit_card", re.compile(r"\b(?:\d[ \-]*?){13,19}\b"), luhn_validated=True),
    PIIPattern("api_key", re.compile(r"\b(?:sk|pk|rk|api)[-_][A-Za-z0-9]{20,}\b", re.I)),
    PIIPattern("aws_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    PIIPattern("ipv4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b")),
    PIIPattern("ipv6", re.compile(
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|"
        r"\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b|"
        r"\b::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}\b"
    )),
]


# --------------------------------------------------------------------------- #
# Redaction                                                                     #
# --------------------------------------------------------------------------- #

@dataclass
class RedactionMatch:
    """Records a single redaction made in a text."""
    category: str
    original: str
    span: tuple[int, int]


def redact(text: str) -> tuple[str, list[RedactionMatch]]:
    """Replace PII in *text* and return the redacted string plus match metadata."""
    redactions: list[RedactionMatch] = []
    redacted = text

    # Process in reverse order of pattern specificity (credit cards before generic digits).
    for pii in reversed(PII_PATTERNS):
        def _replacer(m: re.Match[str], _cat: str = pii.category, _luhn: bool = pii.luhn_validated) -> str:
            original = m.group()
            if _luhn and not _luhn_check(original):
                return original
            redactions.append(RedactionMatch(category=_cat, original=original, span=(m.start(), m.end())))
            return f"[REDACTED:{_cat}]"

        redacted = pii.pattern.sub(_replacer, redacted)

    # Rebuild spans after earlier replacements shifted indices.
    return redacted, redactions


# --------------------------------------------------------------------------- #
# Middleware                                                                    #
# --------------------------------------------------------------------------- #

class PIIRedactorMiddleware(Middleware):
    """Redacts PII from user messages before they reach the model.

    The redaction is applied in-place on the ``state["messages"]`` list so
    that downstream tools and models never see the raw PII.
    """

    name = "pii_redactor"

    def __init__(self, redact_system_messages: bool = False) -> None:
        self.redact_system_messages = redact_system_messages

    async def before_agent(self, ctx: MiddlewareContext) -> MiddlewareContext:
        messages = ctx.state.get("messages", [])
        total_redactions = 0

        for i, msg in enumerate(messages):
            # Determine the role.
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            elif hasattr(msg, "type"):
                role = getattr(msg, "type", "")
                content = getattr(msg, "content", "")
            else:
                continue

            if not isinstance(content, str):
                continue

            if role in ("user", "human"):
                redacted_text, matches = redact(content)
                if matches:
                    if isinstance(msg, dict):
                        messages[i] = {**msg, "content": redacted_text}
                    elif hasattr(msg, "content"):
                        msg.content = redacted_text
                    total_redactions += len(matches)
            elif role == "system" and self.redact_system_messages:
                redacted_text, matches = redact(content)
                if matches:
                    if isinstance(msg, dict):
                        messages[i] = {**msg, "content": redacted_text}
                    elif hasattr(msg, "content"):
                        msg.content = redacted_text
                    total_redactions += len(matches)

        ctx.state["messages"] = messages

        if total_redactions:
            logger.info("PIIRedactor: redacted %d PII instances", total_redactions)

        return ctx
