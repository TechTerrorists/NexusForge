"""Group Chat pattern — orchestrator-directed multi-agent conversation.

An orchestrator LLM decides which agent speaks next in each round,
simulating a structured group chat.  Agents contribute to a shared
conversation, and the orchestrator can terminate when a consensus or
sufficient information is reached.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from packages.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)

_ORCHESTRATOR_SYSTEM = (
    "You are the orchestrator of a multi-agent group chat.  "
    "Your job is to decide which agent should speak next based on the "
    "conversation so far.  You can also decide the conversation is complete "
    "by outputting 'END'.  Be efficient — don't repeat agents unnecessarily."
)


class GroupChatAgent:
    """Wraps an agent with a system prompt and chat-compatible interface."""

    def __init__(self, agent: Any, system_prompt: str | None = None) -> None:
        self.agent = agent
        self.name = getattr(agent, "name", "unknown")
        self.system_prompt = system_prompt or f"You are {self.name}."

    async def safe_run(self, state: WorkflowState) -> dict:
        return await self.agent.safe_run(state)


class GroupChatPattern:
    """Orchestrator-directed multi-agent conversation pattern.

    Usage::

        pattern = GroupChatPattern(
            orchestrator_model=model,
            agents=[analyst, coder, reviewer],
            max_rounds=20,
        )
        result = await pattern.run(initial_state)
    """

    def __init__(
        self,
        orchestrator_model: BaseChatModel,
        agents: list[Any],
        name: str = "group_chat",
        max_rounds: int = 20,
        orchestrator_prompt: str | None = None,
        termination_condition: Callable[[WorkflowState], bool] | None = None,
    ) -> None:
        self.name = name
        self.max_rounds = max_rounds
        self.termination_condition = termination_condition

        self.orchestrator_model = orchestrator_model
        self.orchestrator_prompt = orchestrator_prompt or _ORCHESTRATOR_SYSTEM

        self.agents: dict[str, GroupChatAgent] = {}
        for agent in agents:
            agent_name = getattr(agent, "name", f"agent_{len(self.agents)}")
            self.agents[agent_name] = GroupChatAgent(agent)

        self._chat_log: list[dict[str, Any]] = []

    async def _orchestrate(self, agent_names: list[str], chat_log: list[dict]) -> str:
        """Ask the orchestrator LLM which agent should speak next."""
        summary = "\n".join(
            f"- {entry['agent']}: {entry.get('summary', '(no summary)')}"
            for entry in chat_log[-10:]  # last 10 messages for context
        )

        prompt = [
            SystemMessage(content=self.orchestrator_prompt),
            HumanMessage(
                content=f"Available agents: {agent_names}\n\n"
                f"Conversation so far:\n{summary}\n\n"
                f"Which agent should speak next? Reply with just the agent name "
                f"or 'END' if the conversation is complete."
            ),
        ]

        response = await self.orchestrator_model.ainvoke(prompt)
        content = response.content.strip() if isinstance(response.content, str) else str(response.content)

        # Clean up the response
        for name in agent_names:
            if name.lower() in content.lower():
                return name
        if "END" in content.upper():
            return "END"
        return agent_names[0] if agent_names else "END"

    async def run(
        self,
        initial_state: WorkflowState,
        *,
        start_agent: str | None = None,
    ) -> dict:
        """Execute the group chat until the orchestrator terminates it."""
        working_state = dict(initial_state)
        merged_patch: dict[str, Any] = {}
        self._chat_log = []

        agent_names = list(self.agents.keys())
        if not agent_names:
            logger.warning("GroupChat '%s': no agents configured", self.name)
            return merged_patch

        current_agent_name = start_agent or agent_names[0]

        logger.info(
            "GroupChat '%s' starting | agents=%s | max_rounds=%d",
            self.name, agent_names, self.max_rounds,
        )

        for round_num in range(self.max_rounds):
            if current_agent_name == "END" or current_agent_name not in self.agents:
                break

            if self.termination_condition and self.termination_condition(working_state):
                logger.info("GroupChat '%s' terminated by condition", self.name)
                break

            cap = self.agents[current_agent_name]
            logger.info("GroupChat '%s' round %d: %s", self.name, round_num, current_agent_name)

            try:
                patch = await cap.safe_run(working_state)
            except Exception as exc:
                logger.error("GroupChat '%s' agent '%s' failed: %s", self.name, current_agent_name, exc)
                merged_patch.setdefault("errors", []).append(f"{current_agent_name}: {exc}")
                break

            merged_patch.update(patch)
            working_state.update(patch)

            # Extract a summary for the chat log
            messages = patch.get("messages", [])
            summary = ""
            if messages:
                last = messages[-1]
                content = getattr(last, "content", "")
                summary = str(content)[:200] if content else ""

            self._chat_log.append({
                "agent": current_agent_name,
                "round": round_num,
                "summary": summary or f"completed round {round_num}",
            })

            # Ask orchestrator for next agent
            current_agent_name = await self._orchestrate(agent_names, self._chat_log)

        merged_patch["group_chat_log"] = list(self._chat_log)
        logger.info("GroupChat '%s' complete | rounds=%d", self.name, len(self._chat_log))
        return merged_patch
