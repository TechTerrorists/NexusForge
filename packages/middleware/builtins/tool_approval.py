"""ToolApprovalMiddleware — requires human approval for sensitive tool calls."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from packages.middleware.pipeline import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Data structures                                                               #
# --------------------------------------------------------------------------- #

@dataclass
class ApprovalRequest:
    """Represents a pending approval request for a tool call."""
    request_id: str
    tool_name: str
    args: dict
    agent_name: str
    approved: bool | None = None
    reason: str = ""

    def approve(self, reason: str = "") -> None:
        self.approved = True
        self.reason = reason

    def reject(self, reason: str = "Rejected by human") -> None:
        self.approved = False
        self.reason = reason


@dataclass
class ToolApprovalMiddlewareState:
    """Internal bookkeeping for the middleware."""
    pending: dict[str, ApprovalRequest] = field(default_factory=dict)
    history: list[ApprovalRequest] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Middleware                                                                    #
# --------------------------------------------------------------------------- #

class ToolApprovalMiddleware(Middleware):
    """Pauses tool execution when a tool is flagged for human approval.

    Configuration:
        tools_requiring_approval: set of tool names that must be approved.
        approval_timeout: seconds to wait before auto-rejecting.
        auto_approve_callback: optional async callback that decides
            programmatically (e.g. from a database) whether to approve.

    Flow:
        1. ``wrap_tool_call`` intercepts calls to tools in the approval set.
        2. An ``ApprovalRequest`` is created and stored.
        3. The middleware waits (polls) for the approval to be resolved.
        4. If approved within *approval_timeout*, the tool call proceeds.
        5. If rejected or timed out, the call is skipped and an error is
           returned to the model.
    """

    name = "tool_approval"

    def __init__(
        self,
        tools_requiring_approval: set[str] | None = None,
        approval_timeout: float = 300.0,
        auto_approve_callback: Callable[[ApprovalRequest], Awaitable[bool]] | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self.tools_requiring_approval = tools_requiring_approval or set()
        self.approval_timeout = approval_timeout
        self.auto_approve_callback = auto_approve_callback
        self.poll_interval = poll_interval
        self._state = ToolApprovalMiddlewareState()

    # ---- public API -------------------------------------------------------- #

    def request_approval(self, tool_name: str, args: dict, agent_name: str) -> ApprovalRequest:
        """Create an approval request and return it for external resolution."""
        req = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            tool_name=tool_name,
            args=args,
            agent_name=agent_name,
        )
        self._state.pending[req.request_id] = req
        logger.info("ToolApproval: request %s for tool '%s'", req.request_id, tool_name)
        return req

    def resolve_approval(self, request_id: str, approved: bool, reason: str = "") -> bool:
        """Resolve a pending approval.  Returns True if found."""
        req = self._state.pending.pop(request_id, None)
        if req is None:
            return False
        if approved:
            req.approve(reason)
        else:
            req.reject(reason)
        self._state.history.append(req)
        return True

    def is_pending(self, request_id: str) -> bool:
        return request_id in self._state.pending

    # ---- middleware hooks --------------------------------------------------- #

    async def wrap_tool_call(
        self,
        ctx: MiddlewareContext,
        tool_name: str,
        args: dict,
        call: Callable[[], Awaitable[Any]],
    ) -> Any:
        if tool_name not in self.tools_requiring_approval:
            return await call()

        req = self.request_approval(tool_name, args, ctx.agent_name)

        # Store request in context so callers can access it.
        ctx.state.setdefault("approval_requests", []).append({
            "request_id": req.request_id,
            "tool_name": tool_name,
            "args": args,
        })

        # Auto-approve callback (e.g. from DB or policy engine).
        if self.auto_approve_callback is not None:
            try:
                should_approve = await self.auto_approve_callback(req)
                if should_approve:
                    req.approve("auto-approved")
                    self._state.history.append(req)
                    logger.info("ToolApproval: auto-approved %s", req.request_id)
                    return await call()
            except Exception as exc:
                logger.error("ToolApproval: auto-approve callback failed: %s", exc)

        # Poll for resolution.
        elapsed = 0.0
        while elapsed < self.approval_timeout:
            if req.approved is not None:
                break
            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        if req.approved is None:
            req.reject("Timed out waiting for approval")
            self._state.pending.pop(req.request_id, None)
            self._state.history.append(req)
            logger.warning("ToolApproval: request %s timed out", req.request_id)
            return {
                "error": f"Tool call '{tool_name}' was not approved within {self.approval_timeout}s",
                "tool_name": tool_name,
                "approved": False,
            }

        if not req.approved:
            logger.info("ToolApproval: request %s rejected — %s", req.request_id, req.reason)
            return {
                "error": f"Tool call '{tool_name}' rejected: {req.reason}",
                "tool_name": tool_name,
                "approved": False,
            }

        logger.info("ToolApproval: request %s approved — %s", req.request_id, req.reason)
        return await call()
