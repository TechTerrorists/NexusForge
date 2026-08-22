"""PIIRedactor — regex-based PII scrubbing with Luhn validation for credit cards."""

from __future__ import annotations

import re
from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# Luhn algorithm                                                                #
# --------------------------------------------------------------------------- #

def _luhn_check(number: str) -> bool:
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
# Pattern definitions                                                           #
# --------------------------------------------------------------------------- #

@dataclass
class PIIPattern:
    category: str
    pattern: re.Pattern[str]
    luhn_validated: bool = False


_PATTERNS: list[PIIPattern] = [
    PIIPattern("email", re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    )),
    PIIPattern("phone", re.compile(
        r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
    )),
    PIIPattern("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    PIIPattern("credit_card", re.compile(
        r"\b(?:\d[ \-]*?){13,19}\b"
    ), luhn_validated=True),
    PIIPattern("ipv4", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),
    PIIPattern("ipv6", re.compile(
        r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|"
        r"(?:[0-9a-fA-F]{1,4}:){1,7}:|"
        r"::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}"
    )),
    PIIPattern("api_key", re.compile(
        r"\b(?:sk|pk|rk|api)[\-_][A-Za-z0-9]{20,}\b", re.IGNORECASE
    )),
    PIIPattern("aws_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
]


# --------------------------------------------------------------------------- #
# Public types                                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class RedactionMatch:
    """Records a single redaction."""
    category: str
    original: str
    span: tuple[int, int]


# --------------------------------------------------------------------------- #
# PIIRedactor                                                                   #
# --------------------------------------------------------------------------- #

class PIIRedactor:
    """Scrub PII from text.

    Usage::

        redactor = PIIRedactor()
        clean_text, matches = redactor.redact("Contact me at alice@example.com")
        # clean_text == "Contact me at [REDACTED:email]"
    """

    def redact(self, text: str) -> tuple[str, list[RedactionMatch]]:
        """Replace PII in *text* with ``[REDACTED:category]`` tokens."""
        redactions: list[RedactionMatch] = []
        result = text

        for pii in reversed(_PATTERNS):
            def _replacer(
                m: re.Match[str],
                _cat: str = pii.category,
                _luhn: bool = pii.luhn_validated,
            ) -> str:
                original = m.group()
                if _luhn and not _luhn_check(original):
                    return original
                redactions.append(
                    RedactionMatch(category=_cat, original=original, span=(m.start(), m.end()))
                )
                return f"[REDACTED:{_cat}]"

            result = pii.pattern.sub(_replacer, result)

        return result, redactions

    def has_pii(self, text: str) -> bool:
        """Quick check for any PII presence."""
        for pii in _PATTERNS:
            if pii.pattern.search(text):
                if pii.luhn_validated:
                    for m in pii.pattern.finditer(text):
                        if _luhn_check(m.group()):
                            return True
                else:
                    return True
        return False

    def find_all(self, text: str) -> list[RedactionMatch]:
        """Find all PII matches without redacting."""
        matches: list[RedactionMatch] = []
        for pii in _PATTERNS:
            for m in pii.pattern.finditer(text):
                if pii.luhn_validated and not _luhn_check(m.group()):
                    continue
                matches.append(
                    RedactionMatch(
                        category=pii.category,
                        original=m.group(),
                        span=(m.start(), m.end()),
                    )
                )
        matches.sort(key=lambda r: r.span[0])
        return matches
