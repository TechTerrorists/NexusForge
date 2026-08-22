"""MiddlewarePipeline — composable hook chain that wraps agent execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Context                                                                      #
# --------------------------------------------------------------------------- #

@dataclass
class MiddlewareContext:
    """Mutable context threaded through every middleware hook."""

    agent_name: str
    state: dict
    model: Any = None
    tools: list = field(default_factory=list)
    system_prompt: str = ""

    # Mutable control flags — middlewares may set these to alter flow.
    cancelled: bool = False
    cancel_reason: str = ""
    jump_to: str | None = None  # "model", "tools", "end"


# --------------------------------------------------------------------------- #
# Base middleware                                                               #
# --------------------------------------------------------------------------- #

class Middleware:
    """Base class for pipeline middlewares.  Override the hooks you need."""

    name: str = "base"

    async def before_agent(self, ctx: MiddlewareContext) -> MiddlewareContext:
        return ctx

    async def after_agent(self, ctx: MiddlewareContext, result: dict) -> dict:
        return result

    async def before_model(self, ctx: MiddlewareContext) -> MiddlewareContext:
        return ctx

    async def after_model(self, ctx: MiddlewareContext, response: Any) -> Any:
        return response

    async def wrap_model_call(self, ctx: MiddlewareContext, call: Callable[[], Awaitable[Any]]) -> Any:
        return await call()

    async def wrap_tool_call(
        self,
        ctx: MiddlewareContext,
        tool_name: str,
        args: dict,
        call: Callable[[], Awaitable[Any]],
    ) -> Any:
        return await call()


# --------------------------------------------------------------------------- #
# Pipeline                                                                     #
# --------------------------------------------------------------------------- #

class MiddlewarePipeline:
    """Ordered chain of middlewares executed around an agent run.

    Usage::

        pipeline = MiddlewarePipeline()
        pipeline.add(BudgetGuardMiddleware(limit=10.0))
        pipeline.add(PromptInjectionGuardMiddleware())

        ctx = MiddlewareContext(agent_name="researcher", state={})
        result = await pipeline.execute(ctx, my_agent_fn)
    """

    def __init__(self) -> None:
        self.middlewares: list[Middleware] = []

    # ---- registration ------------------------------------------------------ #

    def add(self, middleware: Middleware) -> MiddlewarePipeline:
        """Append a middleware and return *self* for chaining."""
        self.middlewares.append(middleware)
        logger.debug("Pipeline: added middleware %s", middleware.name)
        return self

    def remove(self, name: str) -> MiddlewarePipeline:
        """Remove the first middleware with the given name."""
        self.middlewares = [m for m in self.middlewares if m.name != name]
        return self

    # ---- execution --------------------------------------------------------- #

    async def execute(self, ctx: MiddlewareContext, run_fn: Callable[[MiddlewareContext], Awaitable[Any]]) -> Any:
        """Run *run_fn* wrapped by every middleware in registration order."""
        logger.debug("Pipeline: executing with %d middlewares", len(self.middlewares))

        # ---- before_agent phase ---- #
        for mw in self.middlewares:
            ctx = await mw.before_agent(ctx)
            if ctx.cancelled:
                logger.info("Pipeline: cancelled by %s — %s", mw.name, ctx.cancel_reason)
                return {"error": ctx.cancel_reason or f"Cancelled by middleware '{mw.name}'"}

        # ---- inner execution (model + tools) ---- #
        async def _inner() -> Any:
            # before_model phase
            for mw in self.middlewares:
                ctx = await mw.before_model(ctx)
                if ctx.cancelled:
                    return {"error": ctx.cancel_reason or f"Cancelled by middleware '{mw.name}'"}

            # wrap_model_call phase (onion: last added wraps outermost)
            result: Any = None

            async def _inner_model_call() -> Any:
                nonlocal result
                result = await run_fn(ctx)
                return result

            call: Callable[[], Awaitable[Any]] = _inner_model_call
            for mw in reversed(self.middlewares):
                call = _make_model_call_wrapper(mw, ctx, call)

            await call()

            # after_model phase
            for mw in self.middlewares:
                result = await mw.after_model(ctx, result)
                if isinstance(result, dict) and result.get("error"):
                    break

            return result

        result = await _inner()

        # ---- after_agent phase ---- #
        for mw in self.middlewares:
            result = await mw.after_agent(ctx, result)

        return result


def _make_model_call_wrapper(
    mw: Middleware,
    ctx: MiddlewareContext,
    inner: Callable[[], Awaitable[Any]],
) -> Callable[[], Awaitable[Any]]:
    """Create a closure that wraps *inner* with *mw.wrap_model_call*."""

    async def _wrapper() -> Any:
        return await mw.wrap_model_call(ctx, inner)

    return _wrapper
