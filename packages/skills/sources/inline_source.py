"""InlineSkillSource — creates SkillProtocol instances from programmatic definitions."""

from __future__ import annotations

import hashlib
from typing import Any

from packages.skills.registry import Skill, SkillSource


class InlineSkillSource:
    """Builds skills directly from Python dicts / keyword arguments.

    Useful for tests, dynamic skill generation, or skills that don't
    originate from files.

    Usage::

        source = InlineSkillSource()
        skill = source.create(
            name="Greet User",
            description="Greets the user by name.",
            tags=["greeting", "utility"],
            steps=[
                {"instruction": "Extract the user's name from the message."},
                {"instruction": "Say hello to the user."},
            ],
            resources={"template": "Hello, {name}!"},
            scripts={"main": "print('Hello from inline skill')"},
        )
    """

    def create(
        self,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
        required_tools: list[str] | None = None,
        steps: list[dict[str, Any]] | None = None,
        resources: dict[str, str] | None = None,
        scripts: dict[str, str] | None = None,
        skill_id: str | None = None,
    ) -> Skill:
        """Create a Skill from an inline definition."""
        if skill_id is None:
            skill_id = _generate_id(name)

        source = SkillSource(source_type="inline")

        return Skill(
            _skill_id=skill_id,
            _name=name,
            _description=description,
            _tags=tags or [],
            _required_tools=required_tools or [],
            _steps=steps or [],
            _resources=resources or {},
            _scripts=scripts or {},
            _source=source,
        )

    def create_from_dict(self, definition: dict[str, Any]) -> Skill:
        """Create a Skill from a single dict (e.g. parsed JSON)."""
        return self.create(
            name=definition["name"],
            description=definition.get("description", ""),
            tags=definition.get("tags", []),
            required_tools=definition.get("required_tools", []),
            steps=definition.get("steps", []),
            resources=definition.get("resources", {}),
            scripts=definition.get("scripts", {}),
            skill_id=definition.get("id"),
        )


def _generate_id(name: str) -> str:
    """Deterministic skill ID derived from the name."""
    slug = name.lower().strip().replace(" ", "-")
    slug = slug.encode("utf-8").decode("ascii", errors="ignore")
    if len(slug) > 48:
        digest = hashlib.sha256(name.encode()).hexdigest()[:8]
        slug = slug[:40] + "-" + digest
    return slug
