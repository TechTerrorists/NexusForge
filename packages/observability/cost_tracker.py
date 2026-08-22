import logging
from typing import Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class CostTracker:
    MODEL_COSTS = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
        "gemini-pro": {"input": 0.50, "output": 1.50},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "llama-3-70b": {"input": 0.59, "output": 0.79},
        "llama-3-8b": {"input": 0.05, "output": 0.10},
    }

    def __init__(self, budget_limit_usd: float = 100.0):
        self._budget_limit = budget_limit_usd
        self._total_cost = 0.0
        self._agent_costs: dict[str, float] = defaultdict(float)
        self._model_costs: dict[str, float] = defaultdict(float)
        self._usage_records: list[dict[str, Any]] = []

    def calculate_cost(
        self, 
        model: str, 
        input_tokens: int, 
        output_tokens: int
    ) -> float:
        """Calculate cost for given token usage."""
        model_lower = model.lower()
        
        if model_lower not in self.MODEL_COSTS:
            logger.warning(f"Unknown model: {model}, using default costs")
            rates = {"input": 1.00, "output": 3.00}
        else:
            rates = self.MODEL_COSTS[model_lower]
        
        input_cost = (input_tokens / 1_000_000) * rates["input"]
        output_cost = (output_tokens / 1_000_000) * rates["output"]
        
        return input_cost + output_cost

    def record_usage(
        self, 
        agent_id: str, 
        model: str, 
        input_tokens: int, 
        output_tokens: int
    ) -> float:
        """Record usage and return cost."""
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        
        self._total_cost += cost
        self._agent_costs[agent_id] += cost
        self._model_costs[model.lower()] += cost
        
        self._usage_records.append({
            "agent_id": agent_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost
        })
        
        if not self.check_budget():
            logger.warning(
                f"Budget exceeded! Total: ${self._total_cost:.4f} "
                f"/ ${self._budget_limit:.2f}"
            )
        
        return cost

    def get_total_cost(self) -> float:
        """Get total cost across all usage."""
        return self._total_cost

    def get_agent_cost(self, agent_id: str) -> float:
        """Get cost for a specific agent."""
        return self._agent_costs.get(agent_id, 0.0)

    def check_budget(self) -> bool:
        """Check if within budget. Returns True if within budget."""
        return self._total_cost <= self._budget_limit

    def get_cost_breakdown(self) -> dict[str, Any]:
        """Get detailed cost breakdown."""
        return {
            "total_cost_usd": self._total_cost,
            "budget_limit_usd": self._budget_limit,
            "remaining_budget_usd": self._budget_limit - self._total_cost,
            "budget_utilization_pct": (
                (self._total_cost / self._budget_limit) * 100 
                if self._budget_limit > 0 
                else 0
            ),
            "by_agent": dict(self._agent_costs),
            "by_model": dict(self._model_costs),
            "record_count": len(self._usage_records)
        }

    def set_budget(self, budget_usd: float) -> None:
        """Set or update budget limit."""
        self._budget_limit = budget_usd
        logger.info(f"Budget limit set to ${budget_usd:.2f}")

    def get_usage_records(
        self, 
        agent_id: str = None, 
        model: str = None
    ) -> list[dict[str, Any]]:
        """Get filtered usage records."""
        records = self._usage_records
        
        if agent_id:
            records = [r for r in records if r["agent_id"] == agent_id]
        
        if model:
            records = [
                r for r in records 
                if r["model"].lower() == model.lower()
            ]
        
        return records

    def reset(self) -> None:
        """Reset all tracked costs."""
        self._total_cost = 0.0
        self._agent_costs.clear()
        self._model_costs.clear()
        self._usage_records.clear()
        logger.info("Cost tracker reset")
