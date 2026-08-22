"""ProgressiveDisclosure — advertise, load, and execute skills incrementally."""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from packages.skills.registry import SkillProtocol, SkillRegistry
from packages.skills.security import SkillSecurity

logger = logging.getLogger(__name__)


class ProgressiveDisclosure:
    """Manages the lifecycle of skill discovery and execution.

    Pipeline:
        1. ``advertise`` -> generates a concise system-prompt section listing
           available skills so the model can request one.
        2. ``load`` -> retrieves the full SkillProtocol for a requested skill.
        3. ``read_resource`` -> fetches a named resource (file, URL, blob)
           bundled with the skill.
        4. ``run_script`` -> executes a named script from the skill.

    The security layer (``SkillSecurity``) is enforced at every stage.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        security: SkillSecurity | None = None,
        script_runners: dict[str, Callable[[str, dict[str, Any]], Awaitable[Any]]] | None = None,
        resource_readers: dict[str, Callable[[str], Awaitable[str]]] | None = None,
    ) -> None:
        self.registry = registry
        self.security = security or SkillSecurity()
        self.script_runners = script_runners or {}
        self.resource_readers = resource_readers or {}

    # ---- stage 1: advertise ------------------------------------------------ #

    def advertise(self, skills: list[SkillProtocol] | None = None, max_skills: int = 50) -> str:
        """Build a system-prompt fragment listing available skills.

        If *skills* is ``None``, all registered skills are advertised.
        """
        if skills is None:
            skills = self.registry.list_skills()

        skills = skills[:max_skills]

        if not skills:
            return ""

        lines = [
            "# Available Skills",
            "",
            "You can request any of the following skills by name.  "
            "Each skill provides step-by-step guidance for a specific task.",
            "",
        ]

        for skill in skills:
            tags_str = ", ".join(skill.tags) if skill.tags else "general"
            tools_str = ""
            if skill.required_tools:
                tools_str = f"  Required tools: {', '.join(skill.required_tools)}"
            lines.append(f"- **{skill.name}** (id: `{skill.skill_id}`) -- {skill.description}")
            lines.append(f"  Tags: {tags_str}{tools_str}")

        lines.append("")
        lines.append(
            "To use a skill, respond with: `use_skill:<skill_id>` or "
            "`use_skill:<skill_name>`."
        )

        return "\n".join(lines)

    def advertise_short(self, skills: list[SkillProtocol] | None = None) -> str:
        """One-liner listing of skill names for lightweight prompts."""
        if skills is None:
            skills = self.registry.list_skills()
        names = [f"{s.name} ({s.skill_id})" for s in skills]
        return "Skills: " + ", ".join(names) if names else ""

    # ---- stage 2: load ----------------------------------------------------- #

    def load(self, skill_id: str, context: dict[str, Any] | None = None) -> SkillProtocol | None:
        """Retrieve the full skill protocol, enforcing trust boundaries."""
        skill = self.registry.get(skill_id)
        if skill is None:
            logger.warning("ProgressiveDisclosure: skill '%s' not found", skill_id)
            return None

        context = context or {}
        if not self.security.enforce_trust_boundary(skill, context):
            logger.warning("ProgressiveDisclosure: trust boundary violated for '%s'", skill_id)
            return None

        logger.info("ProgressiveDisclosure: loaded skill '%s'", skill.name)
        return skill

    def load_by_name(self, name: str, context: dict[str, Any] | None = None) -> SkillProtocol | None:
        """Load a skill by its human-readable name."""
        matches = self.registry.discover(name)
        if not matches:
            logger.warning("ProgressiveDisclosure: no skill matching '%s'", name)
            return None
        return self.load(matches[0].skill_id, context)

    # ---- stage 3: read resources ------------------------------------------- #

    async def read_resource(self, skill_id: str, resource_name: str) -> str | None:
        """Read a named resource from a skill."""
        skill = self.load(skill_id)
        if skill is None:
            return None

        if resource_name not in skill.resources:
            logger.warning(
                "ProgressiveDisclosure: resource '%s' not in skill '%s'",
                resource_name,
                skill_id,
            )
            return None

        raw = skill.resources[resource_name]

        reader = self.resource_readers.get(resource_name)
        if reader is not None:
            return await reader(raw)

        return raw

    # ---- stage 4: run scripts ---------------------------------------------- #

    async def run_script(
        self,
        skill_id: str,
        script_name: str,
        variables: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a named script from a skill."""
        skill = self.load(skill_id)
        if skill is None:
            return {"error": f"Skill '{skill_id}' not found or not trusted"}

        if script_name not in skill.scripts:
            return {"error": f"Script '{script_name}' not in skill '{skill_id}'"}

        script_content = skill.scripts[script_name]
        runner = self.script_runners.get("default")

        if runner is None:
            return {"error": "No script runner registered"}

        logger.info("ProgressiveDisclosure: running script '%s' from skill '%s'", script_name, skill_id)
        return await runner(script_content, variables or {})

    # ---- convenience: full pipeline ---------------------------------------- #

    async def execute_skill(
        self,
        skill_id: str,
        variables: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the full advertise -> load -> resources -> scripts pipeline.

        Returns a dict with keys: ``skill``, ``resources``, ``scripts_result``.
        """
        skill = self.load(skill_id, context)
        if skill is None:
            return {"error": f"Skill '{skill_id}' not available"}

        resources: dict[str, str | None] = {}
        for name in skill.resources:
            resources[name] = await self.read_resource(skill_id, name)

        scripts_result: dict[str, Any] = {}
        for name in skill.scripts:
            scripts_result[name] = await self.run_script(skill_id, name, variables)

        return {
            "skill": {
                "id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "steps": skill.steps,
            },
            "resources": resources,
            "scripts_result": scripts_result,
        }
