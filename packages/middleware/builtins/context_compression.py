"""ContextCompressionMiddleware — truncates conversation history when approaching the context window."""

from __future__ import annotations

import logging
from typing import Any

from packages.middleware.pipeline import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

# Approximate character-to-token ratio (English text).  Used for fast
# budget estimation without tiktoken.
CHARS_PER_TOKEN = 4


class ContextCompressionMiddleware(Middleware):
    """Keeps conversation history within a token budget.

    Strategy:
        1. Always keep the system prompt (unchanged).
        2. Always keep the first user message (the original request).
        3. Keep the last *tail_count* messages verbatim.
        4. Summarise the middle (body) region if it exceeds *body_token_budget*.

    This is a conservative heuristic.  More sophisticated summarisation
    can be plugged in via *summarizer_fn*.
    """

    name = "context_compression"

    def __init__(
        self,
        max_tokens: int = 128_000,
        system_token_reserve: int = 4_000,
        response_reserve: int = 4_000,
        tail_count: int = 10,
        body_token_budget: int = 10_000,
        summarizer_fn: Any = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.system_token_reserve = system_token_reserve
        self.response_reserve = response_reserve
        self.tail_count = tail_count
        self.body_token_budget = body_token_budget
        self.summarizer_fn = summarizer_fn

    def _estimate_tokens(self, text: str) -> int:
        """Fast token estimate without tiktoken."""
        return max(1, len(text) // CHARS_PER_TOKEN)

    def _message_tokens(self, msg: Any) -> int:
        content = ""
        if isinstance(msg, dict):
            content = msg.get("content", "") or ""
        elif hasattr(msg, "content"):
            content = getattr(msg, "content", "") or ""
        if not isinstance(content, str):
            content = str(content)
        return self._estimate_tokens(content)

    def _summarise_body(self, messages: list[Any]) -> str:
        """Produce a compact summary of the body messages."""
        if self.summarizer_fn is not None:
            # Delegate to user-provided summarizer (e.g. LLM call).
            return self.summarizer_fn(messages)

        # Fallback: extract-role-label summary.
        parts: list[str] = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "unknown")
                content = msg.get("content", "") or ""
            elif hasattr(msg, "type"):
                role = getattr(msg, "type", "unknown")
                content = getattr(msg, "content", "") or ""
            else:
                continue
            if not isinstance(content, str):
                content = str(content)
            snippet = content[:120].replace("\n", " ")
            if len(content) > 120:
                snippet += "…"
            parts.append(f"[{role}]: {snippet}")

        body = "\n".join(parts)
        return (
            "[COMPRESSED SUMMARY of conversation body — "
            f"{len(messages)} messages omitted]\n{body}"
        )

    # ---- middleware hooks --------------------------------------------------- #

    async def before_agent(self, ctx: MiddlewareContext) -> MiddlewareContext:
        messages = ctx.state.get("messages", [])
        if not messages:
            return ctx

        # Calculate token budget.
        available = self.max_tokens - self.system_token_reserve - self.response_reserve

        # Estimate current total.
        total_tokens = sum(self._message_tokens(m) for m in messages)

        if total_tokens <= available:
            return ctx  # Nothing to compress.

        logger.info(
            "ContextCompression: %d tokens exceeds %d budget, compressing",
            total_tokens,
            available,
        )

        system_messages = [m for m in messages if self._get_role(m) == "system"]
        non_system = [m for m in messages if self._get_role(m) != "system"]

        if len(non_system) <= self.tail_count + 1:
            # Too few messages to split; just truncate oldest non-system.
            non_system = non_system[-(self.tail_count + 1):]
        else:
            first_msg = non_system[0]
            tail = non_system[-self.tail_count:]
            body = non_system[1:-self.tail_count] if len(non_system) > self.tail_count + 1 else []

            # Check if body fits within budget.
            body_tokens = sum(self._message_tokens(m) for m in body)
            if body_tokens > self.body_token_budget:
                body_text = self._summarise_body(body)
                summary_msg = {"role": "system", "content": body_text}
                non_system = [first_msg, summary_msg] + tail
            else:
                non_system = [first_msg] + body + tail

        ctx.state["messages"] = system_messages + non_system
        new_total = sum(self._message_tokens(m) for m in ctx.state["messages"])
        logger.info("ContextCompression: reduced from %d to ~%d tokens", total_tokens, new_total)

        return ctx

    @staticmethod
    def _get_role(msg: Any) -> str:
        if isinstance(msg, dict):
            return msg.get("role", "")
        if hasattr(msg, "type"):
            return getattr(msg, "type", "")
        return ""
