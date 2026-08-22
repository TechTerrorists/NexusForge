"""ToolOutputGuard — wraps untrusted tool output in a safety envelope."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from packages.security.prompt_guard import PromptGuard, RiskLevel

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 20_000
TRUNCATION_NOTICE = "\n[... output truncated by ToolOutputGuard ...]"


# --------------------------------------------------------------------------- #
# ToolOutputGuard                                                               #
# --------------------------------------------------------------------------- #

class ToolOutputGuard:
    """Sanitises output from external tools before it reaches the model.

    Behaviour:
        1. Wraps output in ``<UNTRUSTED_TOOL_OUTPUT>`` envelope.
        2. Runs ``PromptGuard.scan_prompt`` on the output.
        3. If HIGH risk → redacts the entire output body.
        4. Truncates at ``MAX_OUTPUT_CHARS`` to prevent context overflow.

    Usage::

        guard = ToolOutputGuard()
        safe = guard.sanitize_tool_output(raw_llm_response)
    """

    def __init__(
        self,
        max_chars: int = MAX_OUTPUT_CHARS,
        prompt_guard: PromptGuard | None = None,
    ) -> None:
        self.max_chars = max_chars
        self.prompt_guard = prompt_guard or PromptGuard()

    def sanitize_tool_output(self, output: str) -> str:
        """Wrap *output* in a safety envelope, optionally redacting content."""
        if not output:
            return self._wrap(output or "")

        truncated = output
        was_truncated = False

        if len(truncated) > self.max_chars:
            truncated = truncated[: self.max_chars]
            was_truncated = True

        score = self.prompt_guard.scan_prompt(truncated)

        if score.is_high:
            logger.warning(
                "ToolOutputGuard: HIGH risk in tool output — redacting body (%d matches)",
                len(score.matches),
            )
            body = "[REDACTED: tool output contained prompt-injection signals]"
        else:
            body = truncated

        envelope = self._wrap(body)

        if was_truncated:
            envelope += TRUNCATION_NOTICE

        return envelope

    @staticmethod
    def _wrap(body: str) -> str:
        return f"<UNTRUSTED_TOOL_OUTPUT>\n{body}\n</UNTRUSTED_TOOL_OUTPUT>"
