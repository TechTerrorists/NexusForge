"""LLM-driven planner with RAG skill retrieval and NEXUS phase mapping."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from packages.task_runtime.nexus_phases import NEXUS_PHASES
from packages.task_runtime.planner_prompt import PLANNER_SYSTEM_PROMPT, PlanResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannedStep:
    key: str
    title: str
    instructions: str
    skill_slug: str
    depends_on: list[str]
    writes_code: bool
    nexus_phase: str = "build"
    role: str = ""
    parallel_group: str | None = None
    max_retries: int = 3
    acceptance_criteria: str = ""


def _build_skills_context(skills: list[Any]) -> str:
    lines = []
    for s in skills:
        slug = getattr(s, "slug", "")
        name = getattr(s, "name", "")
        desc = getattr(s, "description", "")
        division = getattr(s, "division", "")
        score = getattr(s, "score", None)
        score_str = f" (relevance: {score:.2f})" if score is not None else ""
        lines.append(
            f"- slug: {slug} | name: {name} | division: {division}{score_str}"
            f"\n  description: {desc[:200]}"
        )
    return "\n".join(lines)


def _decode_json_payload(content: str) -> Any:
    """Decode JSON even when a model wraps it in prose or Markdown fences."""
    stripped = content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()

    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        return parsed

    # Preserve the useful line/column error produced by the standard decoder.
    return json.loads(stripped)


def _parse_plan_response(content: str) -> PlanResponse:
    parsed = _decode_json_payload(content)
    if isinstance(parsed, dict) and "steps" in parsed:
        return PlanResponse(**parsed)
    if isinstance(parsed, list):
        return PlanResponse(steps=parsed)
    raise ValueError("The LLM response does not contain a steps array")


async def llm_create_plan(
    goal: str,
    skills: list[Any],
    *,
    model_provider: str | None = None,
    model_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    custom_provider: bool = False,
) -> list[PlannedStep]:
    from app.config import get_settings

    fallback = _deterministic_plan(goal, skills)

    settings = get_settings()
    effective_api_key = (
        api_key
        if api_key is not None
        else settings.opencode_llm.api_key.get_secret_value()
    )
    if not effective_api_key:
        if custom_provider and model_provider != "anthropic":
            # OpenAI-compatible local servers (Ollama, LM Studio, vLLM) often
            # accept any non-empty SDK key while performing no authentication.
            effective_api_key = "not-required"
        else:
            logger.warning(
                "No LLM API key is configured, falling back to deterministic plan"
            )
            return fallback

    try:
        effective_base_url = base_url or settings.opencode_llm.base_url
        skills_context = _build_skills_context(skills)
        system_prompt = PLANNER_SYSTEM_PROMPT.replace("{skills_list}", skills_context)
        model = model_name or settings.opencode_llm.model or "gpt-4o"
        user_prompt = f"Create a plan for this task:\n\n{goal}"

        async def request_content(*, strict_retry: bool = False) -> tuple[str, str]:
            retry_instruction = ""
            if strict_retry:
                retry_instruction = (
                    "\n\nYour previous response was invalid or incomplete JSON. "
                    "Regenerate the entire plan as one complete JSON object. "
                    "Return JSON only, with no Markdown fences or commentary."
                )
            prompt = f"{user_prompt}{retry_instruction}"

            if model_provider == "anthropic":
                import anthropic

                client = anthropic.AsyncAnthropic(
                    api_key=effective_api_key,
                    base_url=effective_base_url or None,
                )
                response = await client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0 if strict_retry else 0.3,
                    max_tokens=4096,
                )
                response_content = "".join(
                    block.text
                    for block in response.content
                    if hasattr(block, "text")
                )
                return response_content, str(getattr(response, "stop_reason", "unknown"))

            import openai

            kwargs: dict[str, Any] = {"api_key": effective_api_key}
            if effective_base_url:
                kwargs["base_url"] = effective_base_url
            client = openai.AsyncOpenAI(**kwargs)
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0 if strict_retry else 0.3,
                max_tokens=4096,
            )
            choice = response.choices[0]
            return choice.message.content or "{}", str(choice.finish_reason or "unknown")

        content, finish_reason = await request_content()
        try:
            plan_response = _parse_plan_response(content)
        except ValueError as exc:
            logger.warning(
                "Planner model=%s returned invalid JSON (characters=%d, "
                "finish_reason=%s, error=%s); retrying once",
                model,
                len(content),
                finish_reason,
                exc,
            )
            content, finish_reason = await request_content(strict_retry=True)
            try:
                plan_response = _parse_plan_response(content)
            except ValueError as retry_exc:
                logger.warning(
                    "Planner model=%s returned invalid JSON again "
                    "(characters=%d, finish_reason=%s, error=%s)",
                    model,
                    len(content),
                    finish_reason,
                    retry_exc,
                )
                return fallback

        valid_slugs = {getattr(s, "slug", "") for s in skills}
        steps: list[PlannedStep] = []
        for s in plan_response.steps:
            if s.skill_slug not in valid_slugs:
                closest = _find_closest_slug(s.skill_slug, valid_slugs)
                if closest:
                    s = s.model_copy(update={"skill_slug": closest})
                else:
                    continue

            if s.nexus_phase not in NEXUS_PHASES:
                s = s.model_copy(update={"nexus_phase": "build"})

            steps.append(PlannedStep(
                key=s.key,
                title=s.title,
                instructions=s.instructions,
                skill_slug=s.skill_slug,
                depends_on=s.depends_on,
                writes_code=s.writes_code,
                nexus_phase=s.nexus_phase,
                role=s.role,
                parallel_group=s.parallel_group,
                max_retries=s.max_retries,
                acceptance_criteria=s.acceptance_criteria,
            ))

        if not steps:
            return fallback

        _validate_dag(steps)
        return steps

    except Exception:
        logger.exception("LLM planner failed, using deterministic fallback")
        return fallback


def _find_closest_slug(target: str, valid_slugs: set[str]) -> str | None:
    target_lower = target.lower()
    for slug in valid_slugs:
        if target_lower in slug or slug in target_lower:
            return slug
    for slug in valid_slugs:
        if any(part in slug for part in target_lower.split("-") if len(part) > 2):
            return slug
    return None


def _validate_dag(steps: list[PlannedStep]) -> None:
    keys = {s.key for s in steps}
    for step in steps:
        for dep in step.depends_on:
            if dep not in keys:
                raise ValueError(f"Step '{step.key}' depends on unknown step '{dep}'")

    visited: set[str] = set()
    path: set[str] = set()

    def dfs(key: str) -> None:
        if key in path:
            raise ValueError(f"Circular dependency detected involving '{key}'")
        if key in visited:
            return
        path.add(key)
        for step in steps:
            if step.key == key:
                for dep in step.depends_on:
                    dfs(dep)
        path.discard(key)
        visited.add(key)

    for step in steps:
        dfs(step.key)


def _deterministic_plan(goal: str, skills: list[Any]) -> list[PlannedStep]:
    all_skills = list(skills)
    researcher = _pick_skill(
        all_skills,
        ("architect", "research", "analyst"),
        "software-architect",
    )
    engineer = _pick_skill(
        all_skills,
        ("engineer", "developer", "backend", "frontend"),
        "software-engineer",
    )
    reviewer = _pick_skill(
        all_skills,
        ("test", "review", "quality"),
        "quality-engineer",
    )
    return [
        PlannedStep(
            key="understand",
            title="Understand repository and task",
            skill_slug=researcher,
            instructions=(
                "Inspect the repository read-only and produce a concise "
                f"implementation plan for: {goal}"
            ),
            depends_on=[],
            writes_code=False,
            nexus_phase="discover",
            role="researcher",
            acceptance_criteria="Written analysis of codebase and task requirements",
        ),
        PlannedStep(
            key="implement",
            title="Implement the approved change",
            skill_slug=engineer,
            instructions=(
                f"Implement the requested change: {goal}. Work only in the "
                "assigned worktree and report changed files."
            ),
            depends_on=["understand"],
            writes_code=True,
            nexus_phase="build",
            role="engineer",
            acceptance_criteria="Code implemented, tests passing locally",
        ),
        PlannedStep(
            key="review",
            title="Review and validate the change",
            skill_slug=reviewer,
            instructions=(
                f"Review the implementation for: {goal}. Run only "
                "repository-approved checks and report evidence."
            ),
            depends_on=["implement"],
            writes_code=False,
            nexus_phase="harden",
            role="reviewer",
            acceptance_criteria="Code review complete, no blocking issues found",
        ),
    ]


def _pick_skill(skills: list[Any], hints: tuple[str, ...], fallback: str) -> str:
    for skill in skills:
        haystack = (
            f"{getattr(skill, 'name', '')} "
            f"{getattr(skill, 'description', '')} "
            f"{getattr(skill, 'division', '')}"
        ).lower()
        if any(hint in haystack for hint in hints):
            return str(skill.slug)
    return fallback
