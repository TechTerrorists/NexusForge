"""Middleware registry — lookup and instantiate middlewares by name."""

from __future__ import annotations

import logging
from typing import Type

from packages.middleware.pipeline import Middleware

logger = logging.getLogger(__name__)

_registry: dict[str, Type[Middleware]] = {}


def register_middleware(name: str, cls: Type[Middleware]) -> None:
    """Register a middleware class under a short name."""
    _registry[name] = cls
    logger.debug("Middleware registered: %s -> %s", name, cls.__name__)


def get_middleware(name: str) -> Type[Middleware] | None:
    """Look up a middleware class by name."""
    return _registry.get(name)


def list_middleware() -> dict[str, Type[Middleware]]:
    """Return a copy of the full registry."""
    return dict(_registry)


def create_middleware(name: str, **kwargs) -> Middleware:
    """Instantiate a registered middleware with the given keyword arguments."""
    cls = _registry.get(name)
    if cls is None:
        raise KeyError(f"Unknown middleware: {name!r}. Available: {list(_registry)}")
    return cls(**kwargs)


def load_builtin_middleware() -> None:
    """Import all builtins so they self-register."""
    from packages.middleware.builtins import (  # noqa: F401
        budget_guard,
        context_compression,
        pii_redactor,
        prompt_guard,
        structured_output,
        tool_approval,
    )
