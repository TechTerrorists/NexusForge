"""EmailAllowlist — fnmatch-based recipient filtering."""

from __future__ import annotations

import fnmatch
from typing import Sequence


class EmailAllowlist:
    """Determines whether an email recipient is allowed.

    Rules:
        - An empty allowlist is a wildcard (all recipients allowed) — useful
          in development.
        - Patterns use :func:`fnmatch.fnmatch` (case-insensitive):
          ``*@example.com``, ``admin-*@corp.net``, etc.

    Usage::

        allowlist = EmailAllowlist(["*@mycompany.com", "admin-*@partner.org"])
        assert allowlist.is_recipient_allowed("alice@mycompany.com")
        assert not allowlist.is_recipient_allowed("eve@attacker.com")
    """

    def __init__(self, allowlist: Sequence[str] | None = None) -> None:
        self._patterns: list[str] = list(allowlist) if allowlist else []

    @property
    def patterns(self) -> list[str]:
        return list(self._patterns)

    @property
    def is_wildcard(self) -> bool:
        return len(self._patterns) == 0

    def is_recipient_allowed(self, email: str, allowlist: Sequence[str] | None = None) -> bool:
        """Check if *email* is permitted by *allowlist*.

        If *allowlist* is ``None``, the instance's own list is used.
        """
        effective = allowlist if allowlist is not None else self._patterns

        # Empty list = wildcard.
        if not effective:
            return True

        email_lower = email.lower().strip()
        return any(fnmatch.fnmatch(email_lower, pat.lower()) for pat in effective)

    def add(self, pattern: str) -> None:
        """Append a pattern."""
        self._patterns.append(pattern)

    def remove(self, pattern: str) -> bool:
        """Remove the first matching pattern.  Returns True if removed."""
        try:
            self._patterns.remove(pattern)
            return True
        except ValueError:
            return False

    def filter_allowed(self, emails: Sequence[str], allowlist: Sequence[str] | None = None) -> list[str]:
        """Return only the allowed emails from *emails*."""
        return [e for e in emails if self.is_recipient_allowed(e, allowlist)]

    def filter_blocked(self, emails: Sequence[str], allowlist: Sequence[str] | None = None) -> list[str]:
        """Return only the blocked emails from *emails*."""
        return [e for e in emails if not self.is_recipient_allowed(e, allowlist)]
