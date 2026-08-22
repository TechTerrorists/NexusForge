"""SkillRegistry — manages registration, lookup, and discovery of skills."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Protocol                                                                      #
# --------------------------------------------------------------------------- #

@runtime_checkable
class SkillProtocol(Protocol):
    """Contract every skill must fulfil."""

    @property
    def skill_id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def tags(self) -> list[str]: ...

    @property
    def required_tools(self) -> list[str]: ...

    @property
    def steps(self) -> list[dict[str, Any]]: ...

    @property
    def resources(self) -> dict[str, str]: ...

    @property
    def scripts(self) -> dict[str, str]: ...

    def matches_query(self, query: str) -> bool: ...


@dataclass
class SkillSource:
    """Metadata about where a skill was loaded from."""
    source_type: str  # "file", "inline", "registry", "remote"
    source_path: str = ""
    loaded_at: float = 0.0


# --------------------------------------------------------------------------- #
# Concrete skill                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class Skill:
    """Standard dataclass implementing SkillProtocol."""
    _skill_id: str
    _name: str
    _description: str
    _tags: list[str] = field(default_factory=list)
    _required_tools: list[str] = field(default_factory=list)
    _steps: list[dict[str, Any]] = field(default_factory=list)
    _resources: dict[str, str] = field(default_factory=dict)
    _scripts: dict[str, str] = field(default_factory=dict)
    _source: SkillSource | None = None

    @property
    def skill_id(self) -> str:
        return self._skill_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def tags(self) -> list[str]:
        return self._tags

    @property
    def required_tools(self) -> list[str]:
        return self._required_tools

    @property
    def steps(self) -> list[dict[str, Any]]:
        return self._steps

    @property
    def resources(self) -> dict[str, str]:
        return self._resources

    @property
    def scripts(self) -> dict[str, str]:
        return self._scripts

    @property
    def source(self) -> SkillSource | None:
        return self._source

    def matches_query(self, query: str) -> bool:
        """Simple substring match against name, description, and tags."""
        q = query.lower()
        if q in self._name.lower():
            return True
        if q in self._description.lower():
            return True
        return any(q in tag.lower() for tag in self._tags)


# --------------------------------------------------------------------------- #
# Registry                                                                      #
# --------------------------------------------------------------------------- #

class SkillRegistry:
    """Central registry for all discovered / registered skills.

    Usage::

        registry = SkillRegistry()
        registry.register(my_skill)
        skill = registry.get("my-skill-id")
        matches = registry.discover("code review")
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillProtocol] = {}

    # ---- mutation ---------------------------------------------------------- #

    def register(self, skill: SkillProtocol) -> None:
        """Register a skill.  Overwrites any existing skill with the same ID."""
        self._skills[skill.skill_id] = skill
        logger.info("SkillRegistry: registered '%s' (%s)", skill.name, skill.skill_id)

    def unregister(self, skill_id: str) -> bool:
        """Remove a skill by ID.  Returns True if it existed."""
        removed = self._skills.pop(skill_id, None)
        if removed:
            logger.info("SkillRegistry: unregistered '%s'", skill_id)
        return removed is not None

    # ---- lookup ------------------------------------------------------------ #

    def get(self, skill_id: str) -> SkillProtocol | None:
        return self._skills.get(skill_id)

    def list_skills(self) -> list[SkillProtocol]:
        return list(self._skills.values())

    def list_by_tag(self, tag: str) -> list[SkillProtocol]:
        return [s for s in self._skills.values() if tag in s.tags]

    def list_requiring_tool(self, tool_name: str) -> list[SkillProtocol]:
        return [s for s in self._skills.values() if tool_name in s.required_tools]

    # ---- discovery --------------------------------------------------------- #

    def discover(self, query: str) -> list[SkillProtocol]:
        """Return skills matching *query* (ranked by relevance)."""
        matches = [s for s in self._skills.values() if s.matches_query(query)]
        # Sort: exact name match first, then by tag count.
        matches.sort(key=lambda s: (query.lower() not in s.name.lower(), -len(s.tags)))
        return matches

    def discover_by_tags(self, tags: list[str]) -> list[SkillProtocol]:
        """Return skills that match any of the given tags."""
        tag_set = set(t.lower() for t in tags)
        return [
            s for s in self._skills.values()
            if any(t.lower() in tag_set for t in s.tags)
        ]

    def discover_by_tools(self, available_tools: list[str]) -> list[SkillProtocol]:
        """Return skills whose tool requirements are all met by *available_tools*."""
        available = set(available_tools)
        return [
            s for s in self._skills.values()
            if all(t in available for t in s.required_tools)
        ]

    # ---- introspection ----------------------------------------------------- #

    def count(self) -> int:
        return len(self._skills)

    def clear(self) -> None:
        self._skills.clear()
