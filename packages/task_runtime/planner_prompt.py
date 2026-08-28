"""LLM planner system prompt and response schema."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class PlannedStepSchema(BaseModel):
    key: str = ""
    title: str = ""
    instructions: str = ""
    skill_slug: str = ""
    depends_on: list[str] = []
    writes_code: bool = False
    nexus_phase: str = "build"
    role: str = ""
    parallel_group: str | None = None
    max_retries: int = 3
    acceptance_criteria: str = ""
    expected_artifacts: list[str] = []
    tool_grants: list[str] = []
    side_effect_class: str = "workspace"

    @field_validator("nexus_phase", mode="before")
    @classmethod
    def coerce_nexus_phase(cls, v: object) -> str:
        if isinstance(v, int):
            phase_map = {0: "discover", 1: "design", 2: "build", 3: "verify", 4: "harden", 5: "deploy", 6: "monitor"}
            return phase_map.get(v, "build")
        if isinstance(v, str):
            return v.lower().strip()
        return "build"

    @field_validator("parallel_group", "key", "title", "instructions", "skill_slug", "role", mode="before")
    @classmethod
    def coerce_str(cls, v: object) -> str:
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return v
        return ""

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def coerce_acceptance(cls, v: object) -> str:
        if isinstance(v, list):
            return "\n".join(str(item) for item in v)
        if isinstance(v, str):
            return v
        return ""

    @field_validator("expected_artifacts", "tool_grants", mode="before")
    @classmethod
    def coerce_string_list(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item) for item in v]
        return []

    @field_validator("depends_on", mode="before")
    @classmethod
    def coerce_depends(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [d.strip() for d in v.split(",") if d.strip()] if v else []
        if isinstance(v, list):
            return [str(d) for d in v]
        return []


class PlanResponse(BaseModel):
    steps: list[PlannedStepSchema] = []


PLANNER_SYSTEM_PROMPT = """You are a software project planner for NexusForge, an AI-powered multi-agent workflow system.

You have access to the following skills/agents:

{skills_list}

Your job is to create an execution plan for the given task. Each step must use one of the available skills (referenced by slug).

## Rules
1. Every step MUST reference an existing skill_slug from the list above.
2. Steps that depend on other steps must list them in depends_on using the step key.
3. Choose the appropriate NEXUS phase for each step: discover, design, build, verify, harden, deploy, monitor.
4. Assign a meaningful role to each step (e.g. "researcher", "engineer", "reviewer").
5. Keep steps focused and atomic — one clear objective per step.
6. If a step writes code, set writes_code to true.
7. Provide acceptance_criteria describing what "done" looks like for each step.
8. List expected_artifacts and the minimum tool_grants required by the step.
9. Set side_effect_class to one of: read_only, workspace, external, privileged.
10. Prefer parallel, independent work when it cannot create conflicting file writes.

## Response Format
Return a JSON object with a "steps" array. Each step has: key, title, instructions, skill_slug, depends_on, writes_code, nexus_phase, role, parallel_group (optional), max_retries, acceptance_criteria, expected_artifacts, tool_grants, side_effect_class.
"""
