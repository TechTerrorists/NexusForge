import logging
import json
from typing import Any

logger = logging.getLogger(__name__)


class EvaluationEngine:
    def __init__(self, llm_client=None):
        self._llm_client = llm_client

    async def evaluate(
        self,
        response: str,
        context: str,
        criteria: list[str]
    ) -> dict[str, Any]:
        """Evaluate a response against criteria using LLM-as-judge pattern."""
        if not self._llm_client:
            logger.warning("No LLM client configured, returning default scores")
            return self._default_scores()

        evaluation_prompt = self._build_evaluation_prompt(
            response, context, criteria
        )

        try:
            result = await self._llm_client.complete(evaluation_prompt)
            parsed = self._parse_evaluation_result(result)
            return parsed
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return self._default_scores()

    def _build_evaluation_prompt(
        self,
        response: str,
        context: str,
        criteria: list[str]
    ) -> str:
        """Build the evaluation prompt for LLM-as-judge."""
        criteria_text = "\n".join(f"- {c}" for c in criteria)

        prompt = (
            "You are an expert evaluator. Analyze the following response "
            "and provide scores.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"RESPONSE TO EVALUATE:\n{response}\n\n"
            f"EVALUATION CRITERIA:\n{criteria_text}\n\n"
            "Provide your evaluation as JSON with these fields:\n"
            "- faithfulness: (0.0-1.0) How faithful is the response to the context?\n"
            "- relevance: (0.0-1.0) How relevant is the response to the query?\n"
            "- coherence: (0.0-1.0) How coherent and well-structured is the response?\n"
            "- hallucination_detected: (boolean) Does the response contain "
            "information not supported by the context?\n"
            "- reasoning: (string) Brief explanation of your scores\n\n"
            "Return ONLY valid JSON, no other text."
        )
        return prompt

    def _parse_evaluation_result(self, result: str) -> dict[str, Any]:
        """Parse the LLM evaluation result."""
        try:
            result = result.strip()
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(lines[1:-1])

            parsed = json.loads(result)

            return {
                "faithfulness": max(
                    0.0, min(1.0, float(parsed.get("faithfulness", 0.5)))
                ),
                "relevance": max(
                    0.0, min(1.0, float(parsed.get("relevance", 0.5)))
                ),
                "coherence": max(
                    0.0, min(1.0, float(parsed.get("coherence", 0.5)))
                ),
                "hallucination_detected": bool(
                    parsed.get("hallucination_detected", False)
                ),
                "reasoning": str(parsed.get("reasoning", "")),
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse evaluation result: {e}")
            return self._default_scores()

    def _default_scores(self) -> dict[str, Any]:
        """Return default evaluation scores when evaluation is unavailable."""
        return {
            "faithfulness": 0.5,
            "relevance": 0.5,
            "coherence": 0.5,
            "hallucination_detected": False,
            "reasoning": "Default scores - evaluation engine unavailable",
        }

    async def batch_evaluate(
        self,
        items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Evaluate multiple items in batch."""
        results = []
        for item in items:
            result = await self.evaluate(
                response=item.get("response", ""),
                context=item.get("context", ""),
                criteria=item.get("criteria", []),
            )
            results.append(result)
        return results

    def aggregate_scores(
        self, evaluations: list[dict[str, Any]]
    ) -> dict[str, float]:
        """Aggregate multiple evaluation scores."""
        if not evaluations:
            return self._default_scores()

        num = len(evaluations)
        return {
            "faithfulness": sum(e["faithfulness"] for e in evaluations) / num,
            "relevance": sum(e["relevance"] for e in evaluations) / num,
            "coherence": sum(e["coherence"] for e in evaluations) / num,
            "hallination_detected": any(
                e["hallucination_detected"] for e in evaluations
            ),
        }
