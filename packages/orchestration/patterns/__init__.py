"""Orchestration patterns — reusable multi-agent coordination templates."""

from packages.orchestration.patterns.sequential import SequentialPattern
from packages.orchestration.patterns.concurrent import ConcurrentPattern
from packages.orchestration.patterns.handoff import HandoffPattern
from packages.orchestration.patterns.group_chat import GroupChatPattern
from packages.orchestration.patterns.magentic import MagenticPattern

__all__ = [
    "SequentialPattern",
    "ConcurrentPattern",
    "HandoffPattern",
    "GroupChatPattern",
    "MagenticPattern",
]
