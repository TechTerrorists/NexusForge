"""BudgetGuardMiddleware — tracks cumulative LLM cost and blocks when budget exceeded."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from packages.middleware.pipeline import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Model cost table (USD per 1M tokens)                                         #
# --------------------------------------------------------------------------- #

MODEL_COST_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
}


# --------------------------------------------------------------------------- #
# Tokeniser (tiktoken with graceful fallback)                                  #
# --------------------------------------------------------------------------- #

def _count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens using tiktoken when available, else an approximate heuristic."""
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        # Fallback: ~4 chars per token (crude but fast).
        return max(1, len(text) // 4)


def estimate_cost_usd(input_tokens: int, output_tokens: int, model_name: str) -> float:
    """Estimate cost in USD for a given token split and model."""
    key = model_name.lower().strip()
    costs = MODEL_COST_TABLE.get(key)
    if costs is None:
        # Try prefix match (e.g. "gpt-4o-2024-05-13" -> "gpt-4o").
        for known in MODEL_COST_TABLE:
            if key.startswith(known):
                costs = MODEL_COST_TABLE[known]
                break
    if costs is None:
        logger.warning("BudgetGuard: unknown model '%s', using GPT-4o pricing", model_name)
        costs = MODEL_COST_TABLE["gpt-4o"]

    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


# --------------------------------------------------------------------------- #
# Middleware                                                                    #
# --------------------------------------------------------------------------- #

class BudgetGuardMiddleware(Middleware):
    """Guards the LLM budget for the lifetime of this pipeline instance.

    Configuration:
        budget_limit_usd: maximum spend before blocking.
        hard_limit_usd: absolute ceiling that cancels even in-progress calls.
        warning_threshold: fraction (0-1) at which warnings are emitted.
    """

    name = "budget_guard"

    def __init__(
        self,
        budget_limit_usd: float = 100.0,
        hard_limit_usd: float | None = None,
        warning_threshold: float = 0.8,
    ) -> None:
        self.budget_limit_usd = budget_limit_usd
        self.hard_limit_usd = hard_limit_usd or budget_limit_usd * 1.2
        self.warning_threshold = warning_threshold
        self._cumulative_cost: float = 0.0
        self._usage_log: list[dict] = []

    # ---- public API -------------------------------------------------------- #

    @property
    def total_cost(self) -> float:
        return self._cumulative_cost

    @property
    def remaining_budget(self) -> float:
        return max(0.0, self.budget_limit_usd - self._cumulative_cost)

    def pre_check(self, projected_cost_usd: float) -> bool:
        """Return True if the call is within budget."""
        projected_total = self._cumulative_cost + projected_cost_usd
        if projected_total > self.hard_limit_usd:
            logger.warning(
                "BudgetGuard: HARD LIMIT breached ($%.4f projected, $%.4f hard)",
                projected_total,
                self.hard_limit_usd,
            )
            return False
        if projected_total > self.budget_limit_usd:
            logger.warning(
                "BudgetGuard: budget exceeded ($%.4f > $%.4f)",
                projected_total,
                self.budget_limit_usd,
            )
            return False
        return True

    def record_usage(self, input_tokens: int, output_tokens: int, model_name: str) -> float:
        """Record token usage and return the incremental cost."""
        cost = estimate_cost_usd(input_tokens, output_tokens, model_name)
        self._cumulative_cost += cost
        self._usage_log.append(
            {
                "model": model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
                "cumulative_usd": self._cumulative_cost,
            }
        )
        if self._cumulative_cost >= self.budget_limit_usd * self.warning_threshold:
            logger.warning(
                "BudgetGuard: approaching budget limit ($%.4f / $%.4f)",
                self._cumulative_cost,
                self.budget_limit_usd,
            )
        return cost

    def count_tokens(self, text: str, model: str = "gpt-4o") -> int:
        return _count_tokens(text, model)

    # ---- middleware hooks --------------------------------------------------- #

    async def before_agent(self, ctx: MiddlewareContext) -> MiddlewareContext:
        if self._cumulative_cost >= self.hard_limit_usd:
            ctx.cancelled = True
            ctx.cancel_reason = (
                f"Budget hard limit exceeded: ${self._cumulative_cost:.4f} >= ${self.hard_limit_usd:.4f}"
            )
        return ctx

    async def after_model(self, ctx: MiddlewareContext, response: Any) -> Any:
        # If the response contains token usage, record it.
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            model = getattr(response, "response_metadata", {})
            model_name = model.get("model_name", "unknown") if isinstance(model, dict) else "unknown"
            self.record_usage(input_tokens, output_tokens, model_name)
        elif isinstance(response, dict):
            usage = response.get("usage", {})
            if usage:
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                model_name = response.get("model", "unknown")
                self.record_usage(input_tokens, output_tokens, model_name)
        return response
