from __future__ import annotations

import logging
from typing import Any

import yaml

from packages.agents.base import BaseAgent
from packages.agents.types.models import AgentConfig

logger = logging.getLogger(__name__)

_MODEL_REGISTRY: dict[str, str] = {
    "openai": "langchain_openai.ChatOpenAI",
    "anthropic": "langchain_anthropic.ChatAnthropic",
    "azure": "langchain_openai.AzureChatOpenAI",
    "ollama": "langchain_ollama.ChatOllama",
}


def _get_model(provider: str, model_name: str, temperature: float, max_tokens: int) -> Any:
    """Resolve a LangChain chat model from a provider string and model name."""
    dotted = _MODEL_REGISTRY.get(provider)
    if dotted is None:
        raise ValueError(
            f"Unknown model provider {provider!r}. "
            f"Supported: {', '.join(sorted(_MODEL_REGISTRY))}"
        )
    module_path, class_name = dotted.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(model=model_name, temperature=temperature, max_tokens=max_tokens)


class AgentFactory:
    def __init__(
        self,
        tools: dict[str, Any] | None = None,
        middleware: list[Any] | None = None,
    ) -> None:
        self._tools = tools or {}
        self._middleware = middleware or []

    def create_agent(
        self,
        config: AgentConfig,
        agent_class: type[BaseAgent] | None = None,
    ) -> BaseAgent:
        model = _get_model(
            provider=config.model_provider,
            model_name=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        bound_tools = [self._tools[t] for t in config.tools if t in self._tools]

        if agent_class is None:
            agent_class = _build_default_agent_class(config.name)

        agent = agent_class(
            name=config.name,
            model=model,
            tools=bound_tools,
            system_prompt=config.description,
        )
        agent._config = config  # type: ignore[attr-defined]
        return agent

    def create_from_yaml(self, yaml_string: str) -> BaseAgent:
        data = yaml.safe_load(yaml_string)
        if data is None:
            raise ValueError("Empty YAML configuration")
        return self.create_from_dict(data)

    def create_from_dict(self, data: dict[str, Any]) -> BaseAgent:
        config = AgentConfig(**data)
        return self.create_agent(config)


def _build_default_agent_class(name: str) -> type[BaseAgent]:
    """Build a minimal concrete BaseAgent subclass on the fly."""

    class _DefaultAgent(BaseAgent):
        async def run(self, state: dict) -> dict:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=self.system_prompt),
            ]
            for msg in state.get("messages", []):
                if isinstance(msg, dict):
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "user":
                        messages.append(HumanMessage(content=str(content)))
                else:
                    messages.append(msg)
            response = await self.model.ainvoke(messages)
            return {"messages": [response]}

    _DefaultAgent.__name__ = f"Agent({name})"
    _DefaultAgent.__qualname__ = f"Agent({name})"
    return _DefaultAgent
