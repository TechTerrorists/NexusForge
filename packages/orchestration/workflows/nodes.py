"""Deterministic workflow node primitives for structured, non-LLM workflows.

Each node is a self-contained unit that can be composed into a DAG.  Nodes
execute deterministically — no LLM calls, no randomness — and produce a
partial state update dict that LangGraph merges into ``WorkflowState``.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import operator
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

import httpx

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Base class                                                                   #
# --------------------------------------------------------------------------- #

class WorkflowNode(ABC):
    """Base class for all deterministic workflow nodes."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._started_at: float = 0.0
        self._completed_at: float = 0.0

    @abstractmethod
    async def execute(self, state: WorkflowState) -> dict:
        """Execute the node and return a partial state update."""

    async def __call__(self, state: WorkflowState) -> dict:
        """LangGraph-compatible callable — wraps execute with timing."""
        self._started_at = time.monotonic()
        logger.info("Node '%s' starting", self.name)
        try:
            result = await self.execute(state)
        except Exception as exc:
            logger.error("Node '%s' failed: %s", self.name, exc)
            result = {
                "errors": list(state.get("errors", [])) + [f"{self.name}: {exc}"],
            }
            raise
        finally:
            self._completed_at = time.monotonic()
            elapsed = self._completed_at - self._started_at
            logger.info("Node '%s' completed in %.3fs", self.name, elapsed)
        return result


# --------------------------------------------------------------------------- #
# Start / End sentinel nodes                                                   #
# --------------------------------------------------------------------------- #

class StartNode(WorkflowNode):
    """Entry point — records workflow start, no-op by default."""

    def __init__(self) -> None:
        super().__init__(name="start")

    async def execute(self, state: WorkflowState) -> dict:
        return {
            "current_stage": "started",
            "executed_actions": list(state.get("executed_actions", [])) + ["workflow_started"],
        }


class EndNode(WorkflowNode):
    """Terminal node — records workflow completion."""

    def __init__(self) -> None:
        super().__init__(name="end")

    async def execute(self, state: WorkflowState) -> dict:
        return {
            "current_stage": "done",
            "current_node": "end",
            "executed_actions": list(state.get("executed_actions", [])) + ["workflow_completed"],
        }


# --------------------------------------------------------------------------- #
# IfElseNode — conditional branching                                           #
# --------------------------------------------------------------------------- #

class IfElseNode(WorkflowNode):
    """Conditional branch — evaluates a predicate and records the chosen path.

    The ``condition_func`` receives the full ``WorkflowState`` and returns
    ``True`` or ``False``.  The node sets ``current_node`` to either
    ``<name>_true`` or ``<name>_false`` so downstream nodes can inspect
    which branch was taken.
    """

    def __init__(
        self,
        name: str,
        condition_func: Callable[[WorkflowState], bool],
        true_branch: list[WorkflowNode] | None = None,
        false_branch: list[WorkflowNode] | None = None,
    ) -> None:
        super().__init__(name=name)
        self.condition_func = condition_func
        self.true_branch = true_branch or []
        self.false_branch = false_branch or []

    async def execute(self, state: WorkflowState) -> dict:
        condition_result = self.condition_func(state)
        branch = "true" if condition_result else "false"
        chosen_nodes = self.true_branch if condition_result else self.false_branch

        logger.info(
            "IfElse '%s' evaluated to %s (%d nodes in branch)",
            self.name,
            branch,
            len(chosen_nodes),
        )

        # Execute the chosen branch sequentially, merging results
        merged_updates: dict[str, Any] = {}
        working_state = dict(state)
        for node in chosen_nodes:
            result = await node(working_state)
            merged_updates.update(result)
            working_state.update(result)

        merged_updates["current_node"] = f"{self.name}_{branch}"
        return merged_updates


# --------------------------------------------------------------------------- #
# IteratorNode — loop over state keys                                          #
# --------------------------------------------------------------------------- #

class IteratorNode(WorkflowNode):
    """Iterates over a list stored at ``state[iterable_key]`` and executes
    ``body_nodes`` for each item, injecting the current item as ``_iterator_item``
    and the loop index as ``_iterator_index`` into a copy of the state.
    """

    def __init__(
        self,
        name: str,
        iterable_key: str,
        body_nodes: list[WorkflowNode],
    ) -> None:
        super().__init__(name=name)
        self.iterable_key = iterable_key
        self.body_nodes = body_nodes

    async def execute(self, state: WorkflowState) -> dict:
        items = state.get(self.iterable_key, [])
        if not isinstance(items, list):
            items = list(items)

        logger.info(
            "Iterator '%s' iterating over %d items from key '%s'",
            self.name,
            len(items),
            self.iterable_key,
        )

        collected_results: list[Any] = []
        merged_updates: dict[str, Any] = {}

        for idx, item in enumerate(items):
            # Build a per-iteration working state
            iter_state = dict(state)
            iter_state.update(merged_updates)
            iter_state["_iterator_item"] = item
            iter_state["_iterator_index"] = idx

            for node in self.body_nodes:
                result = await node(iter_state)
                merged_updates.update(result)
                iter_state.update(result)
                collected_results.append(result)

        merged_updates["current_node"] = f"{self.name}_complete"
        return merged_updates


# --------------------------------------------------------------------------- #
# AssignerNode — set variables in state                                       #
# --------------------------------------------------------------------------- #

class AssignerNode(WorkflowNode):
    """Assigns a value to a state key using a callable or a static expression.

    If ``expression`` is callable it receives ``(state, current_value)`` and
    returns the new value.  If it is a plain value it is used directly.
    """

    def __init__(
        self,
        name: str,
        variable: str,
        expression: Any,
    ) -> None:
        super().__init__(name=name)
        self.variable = variable
        self.expression = expression

    async def execute(self, state: WorkflowState) -> dict:
        current_value = state.get(self.variable)

        if callable(self.expression):
            new_value = self.expression(state, current_value)
        else:
            new_value = self.expression

        logger.info(
            "Assigner '%s': %s = %r (was %r)",
            self.name,
            self.variable,
            new_value,
            current_value,
        )
        return {self.variable: new_value}


# --------------------------------------------------------------------------- #
# HTTPNode — outbound HTTP requests                                            #
# --------------------------------------------------------------------------- #

class HTTPNode(WorkflowNode):
    """Makes an HTTP request and stores the response in state.

    Response is stored at ``<name>_response`` with keys ``status_code``,
    ``headers``, and ``body``.
    """

    def __init__(
        self,
        name: str,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(name=name)
        self.method = method.upper()
        self.url = url
        self.headers = headers or {}
        self.body = body
        self.timeout = timeout

    async def execute(self, state: WorkflowState) -> dict:
        # Allow dynamic URL / headers / body via state interpolation
        url = self._interpolate(self.url, state)
        headers = {k: self._interpolate(v, state) for k, v in self.headers.items()}
        body = self._interpolate_obj(self.body, state) if self.body else None

        logger.info("HTTP %s %s", self.method, url)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method=self.method,
                url=url,
                headers=headers,
                json=body if isinstance(body, (dict, list)) else None,
                content=body if isinstance(body, str) else None,
            )

        response_key = f"{self.name}_response"
        response_body: Any
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text

        return {
            response_key: {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
            }
        }

    @staticmethod
    def _interpolate(template: str, state: WorkflowState) -> str:
        """Replace ``{key}`` placeholders with state values."""
        result = template
        for key, value in state.items():
            if isinstance(value, str):
                result = result.replace(f"{{{key}}}", value)
        return result

    @classmethod
    def _interpolate_obj(cls, obj: Any, state: WorkflowState) -> Any:
        """Recursively interpolate string templates in dicts/lists."""
        if isinstance(obj, str):
            return cls._interpolate(obj, state)
        if isinstance(obj, dict):
            return {k: cls._interpolate_obj(v, state) for k, v in obj.items()}
        if isinstance(obj, list):
            return [cls._interpolate_obj(item, state) for item in obj]
        return obj


# --------------------------------------------------------------------------- #
# CodeNode — arbitrary Python / JS execution                                   #
# --------------------------------------------------------------------------- #

class CodeNode(WorkflowNode):
    """Executes arbitrary code in a sandboxed context.

    The code receives ``state`` and ``output`` (empty dict) as locals.
    The code must populate ``output`` with the state updates to return.
    Python is executed via restricted ``exec``; JavaScript is delegated
    to a ``node`` subprocess if available.
    """

    def __init__(
        self,
        name: str,
        code_string: str,
        language: str = "python",
    ) -> None:
        super().__init__(name=name)
        self.code_string = code_string
        self.language = language.lower()

    async def execute(self, state: WorkflowState) -> dict:
        if self.language == "python":
            return await self._execute_python(state)
        elif self.language in ("javascript", "js"):
            return await self._execute_javascript(state)
        else:
            raise ValueError(f"Unsupported language: {self.language}")

    async def _execute_python(self, state: WorkflowState) -> dict:
        output: dict[str, Any] = {}
        safe_builtins = {
            "len": len,
            "range": range,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "abs": abs,
            "min": min,
            "max": max,
            "sum": sum,
            "sorted": sorted,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "isinstance": isinstance,
            "type": type,
            "print": print,
        }
        local_ns: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "state": state,
            "output": output,
        }
        exec(self.code_string, {}, local_ns)  # noqa: S102
        return output

    async def _execute_javascript(self, state: WorkflowState) -> dict:
        """Execute JS code via ``node`` subprocess, passing state as JSON stdin."""
        import json as _json

        proc = await asyncio.create_subprocess_exec(
            "node",
            "-e",
            self.code_string,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdin_data = _json.dumps(state).encode()
        stdout, stderr = await proc.communicate(input=stdin_data)

        if proc.returncode != 0:
            raise RuntimeError(f"JS execution failed: {stderr.decode()}")

        try:
            return _json.loads(stdout.decode())
        except Exception:
            return {"js_output": stdout.decode()}


# --------------------------------------------------------------------------- #
# SubflowNode — delegate to a sub-workflow                                    #
# --------------------------------------------------------------------------- #

class SubflowNode(WorkflowNode):
    """Delegates execution to a registered sub-workflow by ID.

    The sub-workflow must be registered with the ``SubflowRegistry`` before
    use.  The sub-workflow receives a copy of the current state and its
    output is merged back into the parent state.
    """

    _registry: dict[str, Callable] = {}

    def __init__(self, name: str, workflow_id: str) -> None:
        super().__init__(name=name)
        self.workflow_id = workflow_id

    @classmethod
    def register(cls, workflow_id: str, handler: Callable) -> None:
        """Register a sub-workflow handler by ID."""
        cls._registry[workflow_id] = handler

    @classmethod
    def unregister(cls, workflow_id: str) -> None:
        """Remove a sub-workflow handler."""
        cls._registry.pop(workflow_id, None)

    async def execute(self, state: WorkflowState) -> dict:
        handler = self._registry.get(self.workflow_id)
        if handler is None:
            raise ValueError(
                f"Subflow '{self.workflow_id}' not registered. "
                f"Available: {list(self._registry.keys())}"
            )

        logger.info("Subflow '%s' delegating to '%s'", self.name, self.workflow_id)

        sub_state = copy.deepcopy(state)
        result = handler(sub_state)

        # Support both sync and async handlers
        if asyncio.iscoroutine(result):
            result = await result

        if not isinstance(result, dict):
            raise TypeError(f"Subflow '{self.workflow_id}' must return a dict, got {type(result)}")

        return result
