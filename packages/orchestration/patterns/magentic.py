"""Magentic pattern — LLM-powered manager with dynamic planning and adaptive replanning.

Inspired by the Magentic-One architecture: a manager LLM maintains a
dynamic plan, delegates to specialist agents, tracks progress, and
replans when things go off track.

Key features:
  - Dynamic plan creation and maintenance
  - Progress tracking against milestones
  - Adaptive replanning on failure or deviation
  - Budget-aware execution
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Structured plan model                                                        #
# --------------------------------------------------------------------------- #

class PlanStep(BaseModel):
    step_id: int
    description: str
    assigned_agent: str
    status: str = "pending"  # pending | in_progress | completed | failed
    depends_on: list[int] = Field(default_factory=list)
    result: str | None = None


class Plan(BaseModel):
    goal: str
    steps: list[PlanStep]
    created_at: float = Field(default_factory=time.time)
    version: int = 1


class ProgressReport(BaseModel):
    completed_steps: int
    total_steps: int
    failed_steps: int
    percent_complete: float
    blockers: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Manager system prompt                                                        #
# --------------------------------------------------------------------------- #

_MANAGER_SYSTEM = """You are the Manager Agent for NexusForge's Magentic pattern.

Your role: maintain a dynamic execution plan, delegate to specialist agents,
track progress, and replan when things go off track.

You have these specialist agents available:
{agent_descriptions}

For each task, you must:
1. Break the goal into discrete steps
2. Assign each step to the most appropriate agent
3. Track completion and dependencies
4. Replan when agents fail or produce unexpected results

Output your plan as JSON with this structure:
{{
  "goal": "high-level description",
  "steps": [
    {{
      "step_id": 1,
      "description": "what to do",
      "assigned_agent": "agent_name",
      "depends_on": []
    }}
  ]
}}

Always be concrete and actionable.  Minimize the number of steps."""


# --------------------------------------------------------------------------- #
# MagenticPattern class                                                        #
# --------------------------------------------------------------------------- #

class MagenticPattern:
    """LLM-powered manager with dynamic planning, progress tracking, and replanning.

    Usage::

        pattern = MagenticPattern(
            manager_model=model,
            agents=[researcher, analyzer, executor],
            budget_usd=5.0,
        )
        result = await pattern.run(initial_state, goal="Analyse Q3 sales data")
    """

    def __init__(
        self,
        manager_model: BaseChatModel,
        agents: list[Any],
        name: str = "magentic",
        max_replans: int = 5,
        budget_usd: float = 10.0,
        termination_condition: Callable[[WorkflowState], bool] | None = None,
    ) -> None:
        self.name = name
        self.manager_model = manager_model
        self.max_replans = max_replans
        self.budget_usd = budget_usd
        self.termination_condition = termination_condition

        self.agents: dict[str, Any] = {}
        for agent in agents:
            agent_name = getattr(agent, "name", f"agent_{len(self.agents)}")
            self.agents[agent_name] = agent

        self._plan: Plan | None = None
        self._execution_log: list[dict[str, Any]] = []

    def _build_manager_prompt(self) -> str:
        descriptions = []
        for name, agent in self.agents.items():
            desc = getattr(agent, "description", f"Specialist agent: {name}")
            descriptions.append(f"- {name}: {desc}")
        return _MANAGER_SYSTEM.format(agent_descriptions="\n".join(descriptions))

    async def _create_plan(self, goal: str, state: WorkflowState) -> Plan:
        """Ask the manager LLM to create an execution plan."""
        prompt = [
            SystemMessage(content=self._build_manager_prompt()),
            HumanMessage(
                content=f"Goal: {goal}\n\n"
                f"Current state summary: stage={state.get('current_stage')}, "
                f"completed_actions={state.get('executed_actions', [])}\n\n"
                f"Create a plan to achieve this goal."
            ),
        ]

        response = await self.manager_model.ainvoke(prompt)
        content = response.content if isinstance(response.content, str) else str(response.content)

        # Parse JSON from the response (handle markdown code blocks)
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        try:
            plan_data = json.loads(json_str)
            plan = Plan(
                goal=plan_data.get("goal", goal),
                steps=[PlanStep(**s) for s in plan_data.get("steps", [])],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse plan JSON, creating minimal plan: %s", exc)
            plan = Plan(
                goal=goal,
                steps=[PlanStep(step_id=1, description=goal, assigned_agent=list(self.agents.keys())[0])],
            )

        self._plan = plan
        logger.info("Magentic plan created | steps=%d | goal=%s", len(plan.steps), goal)
        return plan

    async def _assess_progress(self, state: WorkflowState) -> ProgressReport:
        """Ask the manager LLM to assess progress and suggest replanning."""
        completed = len(state.get("executed_actions", []))
        total = len(self._plan.steps) if self._plan else 1
        failed = len(state.get("errors", []))

        prompt = [
            SystemMessage(content=self._build_manager_prompt()),
            HumanMessage(
                content=f"Current plan: {self._plan.model_dump_json() if self._plan else 'None'}\n\n"
                f"State: completed_actions={state.get('executed_actions', [])}, "
                f"errors={state.get('errors', [])}\n\n"
                f"Assess progress. Are there blockers? Should we replan? "
                f'Return JSON: {{"blockers": [...], "should_replan": bool, '
                f'"suggested_changes": "..."}}'
            ),
        ]

        response = await self.manager_model.ainvoke(prompt)
        content = response.content if isinstance(response.content, str) else str(response.content)

        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        try:
            assessment = json.loads(json_str)
            blockers = assessment.get("blockers", [])
        except (json.JSONDecodeError, TypeError):
            blockers = []

        return ProgressReport(
            completed_steps=completed,
            total_steps=total,
            failed_steps=failed,
            percent_complete=round(completed / max(total, 1) * 100, 1),
            blockers=blockers,
        )

    async def _replan(self, goal: str, state: WorkflowState, progress: ProgressReport) -> Plan:
        """Create a revised plan based on progress assessment."""
        prompt = [
            SystemMessage(content=self._build_manager_prompt()),
            HumanMessage(
                content=f"Original goal: {goal}\n\n"
                f"Original plan: {self._plan.model_dump_json() if self._plan else 'None'}\n\n"
                f"Progress: {progress.model_dump_json()}\n\n"
                f"Blockers: {progress.blockers}\n\n"
                f"Create a revised plan that addresses the blockers and "
                f"completes the remaining work."
            ),
        ]

        response = await self.manager_model.ainvoke(prompt)
        content = response.content if isinstance(response.content, str) else str(response.content)

        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        try:
            plan_data = json.loads(json_str)
            plan = Plan(
                goal=plan_data.get("goal", goal),
                steps=[PlanStep(**s) for s in plan_data.get("steps", [])],
                version=(self._plan.version + 1) if self._plan else 1,
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            plan = self._plan or Plan(goal=goal, steps=[])

        self._plan = plan
        logger.info("Magentic replan | version=%d | steps=%d", plan.version, len(plan.steps))
        return plan

    async def _execute_step(
        self,
        step: PlanStep,
        state: WorkflowState,
    ) -> tuple[dict, bool]:
        """Execute a single plan step via the assigned agent.

        Returns (patch, success).
        """
        agent = self.agents.get(step.assigned_agent)
        if agent is None:
            return {"errors": [f"Agent '{step.assigned_agent}' not found"]}, False

        try:
            patch = await agent.safe_run(state)
            return patch, True
        except Exception as exc:
            return {"errors": [f"Step {step.step_id} failed: {exc}"]}, False

    async def run(
        self,
        initial_state: WorkflowState,
        *,
        goal: str | None = None,
    ) -> dict:
        """Execute the magentic pattern: plan, execute, assess, replan.

        Args:
            initial_state: Starting state.
            goal: High-level goal string.  Falls back to ``state['input'].get('goal')``.

        Returns:
            Merged state patch with plan, execution log, and results.
        """
        if goal is None:
            goal = initial_state.get("input", {}).get("goal", "Complete the task")
        goal = str(goal)

        working_state = dict(initial_state)
        merged_patch: dict[str, Any] = {}
        self._execution_log = []

        logger.info("Magentic '%s' starting | goal=%s | budget=$%.2f", self.name, goal, self.budget_usd)

        # Phase 1: Create plan
        plan = await self._create_plan(goal, working_state)
        merged_patch["magentic_plan"] = plan.model_dump()

        # Phase 2: Execute steps with replanning
        replan_count = 0
        step_idx = 0

        while step_idx < len(plan.steps) and replan_count <= self.max_replans:
            # Check budget
            current_cost = float(working_state.get("total_cost_usd", 0))
            if current_cost >= self.budget_usd:
                logger.warning("Magentic budget exceeded: $%.2f >= $%.2f", current_cost, self.budget_usd)
                merged_patch.setdefault("errors", []).append("Budget exceeded")
                break

            # Check termination
            if self.termination_condition and self.termination_condition(working_state):
                break

            step = plan.steps[step_idx]
            if step.status in ("completed", "failed"):
                step_idx += 1
                continue

            # Check dependencies
            deps_met = all(
                any(s.step_id == dep and s.status == "completed" for s in plan.steps)
                for dep in step.depends_on
            )
            if not deps_met:
                step_idx += 1
                if step_idx >= len(plan.steps):
                    step_idx = 0  # restart scan for unblocked steps
                continue

            logger.info(
                "Magentic step %d/%d: %s -> %s",
                step.step_id, len(plan.steps), step.description, step.assigned_agent,
            )
            step.status = "in_progress"
            merged_patch["magentic_plan"] = plan.model_dump()

            patch, success = await self._execute_step(step, working_state)

            if success:
                step.status = "completed"
                step.result = str(patch.get("messages", [""])[-1])[:200] if patch.get("messages") else "done"
            else:
                step.status = "failed"
                replan_count += 1

                # Assess and replan
                progress = await self._assess_progress(working_state)
                merged_patch.setdefault("errors", []).extend(progress.blockers)

                if replan_count <= self.max_replans:
                    plan = await self._replan(goal, working_state, progress)
                    merged_patch["magentic_plan"] = plan.model_dump()
                    step_idx = 0
                    continue

            merged_patch.update(patch)
            working_state.update(patch)

            self._execution_log.append({
                "step_id": step.step_id,
                "agent": step.assigned_agent,
                "status": step.status,
                "replan_count": replan_count,
            })

            step_idx += 1

        merged_patch["magentic_execution_log"] = list(self._execution_log)
        logger.info(
            "Magentic '%s' complete | steps=%d | replans=%d",
            self.name, len(self._execution_log), replan_count,
        )
        return merged_patch
