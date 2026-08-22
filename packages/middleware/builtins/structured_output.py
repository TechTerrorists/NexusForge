"""StructuredOutputMiddleware — enforces Pydantic model output from agents."""

from __future__ import annotations

import json
import logging
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

from packages.middleware.pipeline import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredOutputMiddleware(Middleware):
    """Enforces that the agent response conforms to a Pydantic schema.

    When a ``response_model`` is set on the context state (keyed by the
    agent name), this middleware:

    1. Attaches ``with_structured_output(model)`` to the model before the call.
    2. Validates the raw model response against the schema after the call.
    3. Returns a validated Pydantic instance (or an error dict).

    Configuration:
        strict: if True, validation failures cancel the pipeline.
    """

    name = "structured_output"

    def __init__(self, strict: bool = True) -> None:
        self.strict = strict

    def _get_response_model(self, ctx: MiddlewareContext) -> Type[BaseModel] | None:
        """Look up the expected Pydantic model for this agent."""
        # Check state["response_models"][agent_name]
        response_models = ctx.state.get("response_models", {})
        model = response_models.get(ctx.agent_name)
        if model is not None:
            return model

        # Check state["response_model"] (global fallback).
        global_model = ctx.state.get("response_model")
        if global_model is not None:
            return global_model

        return None

    def _validate(self, data: Any, model_cls: Type[BaseModel]) -> BaseModel | dict:
        """Validate *data* against *model_cls*."""
        if isinstance(data, model_cls):
            return data

        if isinstance(data, dict):
            try:
                return model_cls.model_validate(data)
            except ValidationError as exc:
                return {"error": f"Structured output validation failed: {exc}"}

        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                return {"error": f"Structured output is not valid JSON: {data[:200]}"}
            try:
                return model_cls.model_validate(parsed)
            except ValidationError as exc:
                return {"error": f"Structured output validation failed: {exc}"}

        return {"error": f"Unexpected structured output type: {type(data).__name__}"}

    # ---- middleware hooks --------------------------------------------------- #

    async def before_model(self, ctx: MiddlewareContext) -> MiddlewareContext:
        model_cls = self._get_response_model(ctx)
        if model_cls is None or ctx.model is None:
            return ctx

        # Wrap model with with_structured_output if the method exists.
        if hasattr(ctx.model, "with_structured_output"):
            try:
                ctx.model = ctx.model.with_structured_output(model_cls)
                logger.debug(
                    "StructuredOutput: configured with_structured_output(%s) for agent '%s'",
                    model_cls.__name__,
                    ctx.agent_name,
                )
            except Exception:
                logger.warning(
                    "StructuredOutput: with_structured_output failed for %s",
                    model_cls.__name__,
                )

        return ctx

    async def after_model(self, ctx: MiddlewareContext, response: Any) -> Any:
        model_cls = self._get_response_model(ctx)
        if model_cls is None:
            return response

        # Skip validation if the model already returned a Pydantic instance
        # (i.e. with_structured_output did its job).
        if isinstance(response, model_cls):
            return response

        # Extract content from various response shapes.
        raw: Any = response
        if hasattr(response, "content"):
            raw = response.content
        elif isinstance(response, dict):
            raw = response.get("content", response)

        result = self._validate(raw, model_cls)

        if isinstance(result, dict) and result.get("error"):
            if self.strict:
                ctx.cancelled = True
                ctx.cancel_reason = result["error"]
                logger.warning("StructuredOutput: %s", result["error"])
                return result
            logger.warning("StructuredOutput: validation failed (non-strict): %s", result["error"])

        return result
