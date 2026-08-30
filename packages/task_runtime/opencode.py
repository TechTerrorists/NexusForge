"""OpenCode runner adapter. Credentials stay in the worker environment."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenCodeResult:
    text: str
    events: list[dict]
    session_id: str | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0


class OpenCodeRunner:
    def __init__(self, binary: str | None = None, timeout_seconds: int = 1800) -> None:
        self.binary = binary or os.getenv("OPENCODE_BINARY", "opencode")
        self.timeout_seconds = timeout_seconds
        self.default_model = os.getenv("NEXUSFORGE_OPENCODE_MODEL") or None

    async def run(
        self,
        *,
        prompt: str,
        workdir: Path,
        model: str | None = None,
        agent: str | None = None,
        env_extras: dict[str, str] | None = None,
        provider: str | None = None,
        adapter: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        custom_provider: bool = False,
        event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        mode: str | None = None,
    ) -> OpenCodeResult:
        selected_model = model or self.default_model
        selected_mode = mode or os.getenv("NEXUSFORGE_RUNNER_MODE", "http")
        if selected_mode == "docker":
            return await self._run_docker(
                prompt=prompt, workdir=workdir, model=selected_model,
                agent=agent, env_extras=env_extras, provider=provider,
                adapter=adapter, base_url=base_url, api_key=api_key,
                custom_provider=custom_provider,
                event_sink=event_sink,
            )
        if selected_mode == "local":
            return await self._run_local(
                prompt=prompt, workdir=workdir, model=selected_model,
                agent=agent, env_extras=env_extras, provider=provider,
                adapter=adapter, base_url=base_url, api_key=api_key,
                custom_provider=custom_provider,
                event_sink=event_sink,
            )
        return await self._run_http(
            prompt=prompt, workdir=workdir, model=selected_model,
            agent=agent, adapter=adapter, base_url=base_url, api_key=api_key,
            custom_provider=custom_provider,
            event_sink=event_sink,
        )

    async def _run_http(
        self,
        *,
        prompt: str,
        workdir: Path,
        model: str | None,
        agent: str | None,
        adapter: str | None,
        base_url: str | None,
        api_key: str | None,
        custom_provider: bool,
        event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> OpenCodeResult:
        from app.config import get_settings

        settings = get_settings()
        api_key = (
            api_key
            if api_key is not None
            else settings.opencode_llm.api_key.get_secret_value()
        )
        base_url = base_url or settings.opencode_llm.base_url
        selected_model = model or settings.opencode_llm.model

        if not api_key and custom_provider and adapter != "anthropic":
            api_key = "not-required"
        if not api_key or not base_url:
            raise RuntimeError(
                "An LLM endpoint and API key must be configured for the HTTP runner"
            )

        repo_context = ""
        readme = workdir / "README.md"
        if readme.exists():
            try:
                repo_context = f"\n\nRepository README:\n{readme.read_text()[:3000]}"
            except Exception:
                pass

        system_msg = f"You are an AI agent{' specializing in ' + agent if agent else ''}. Execute the task precisely. Be concise."
        user_msg = f"{prompt}{repo_context}"

        if adapter == "anthropic":
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
            response = await client.messages.create(
                model=selected_model,
                system=system_msg,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.2,
                max_tokens=8192,
            )
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            tokens_used = int(getattr(response.usage, "input_tokens", 0) or 0) + int(getattr(response.usage, "output_tokens", 0) or 0)
        else:
            import openai

            client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
            response = await client.chat.completions.create(
                model=selected_model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=8192,
            )
            text = response.choices[0].message.content or ""
            tokens_used = int(getattr(response.usage, "total_tokens", 0) or 0) if response.usage else 0
        events = [{"type": "agent_output", "text": text, "agent": agent, "model": selected_model}]
        if event_sink:
            await event_sink(events[0])
        return OpenCodeResult(text=text, events=events, tokens_used=tokens_used, cost_usd=_response_cost(response))

    async def _run_local(
        self,
        *,
        prompt: str,
        workdir: Path,
        model: str | None,
        agent: str | None,
        env_extras: dict[str, str] | None = None,
        provider: str | None = None,
        adapter: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        custom_provider: bool = False,
        event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> OpenCodeResult:
        configured_provider = bool(custom_provider and base_url and model)
        openrouter = configured_provider and self._is_openrouter(provider, base_url)
        selected_model = (
            f"openrouter/{self._openrouter_model_id(model)}"
            if openrouter
            else f"nexusforge/{model}" if configured_provider else model
        )
        command = [
            self.binary,
            "--print-logs",
            "--log-level",
            "ERROR",
            "run",
            "--format",
            "json",
            "--dir",
            str(workdir),
        ]
        if selected_model:
            command.extend(["--model", selected_model])
        if agent:
            command.extend(["--agent", agent])
        command.append(prompt)
        safe_env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "LC_ALL", "OPENCODE_AUTH_JSON", "OPENCODE_SERVER_PASSWORD"}
            or key.startswith("OPENCODE_")
        }
        if env_extras:
            safe_env.update(env_extras)
        if configured_provider and base_url and model:
            if openrouter:
                safe_env["OPENROUTER_API_KEY"] = api_key or ""
                safe_env["OPENCODE_CONFIG_CONTENT"] = self._openrouter_config(model)
            else:
                safe_env["NEXUSFORGE_OPENCODE_API_KEY"] = api_key or "not-required"
                safe_env["OPENCODE_CONFIG_CONTENT"] = self._provider_config(
                    provider=provider,
                    adapter=adapter,
                    base_url=base_url,
                    model=model,
                )
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=safe_env,
        )
        try:
            events, text_parts, stderr = await asyncio.wait_for(
                self._stream_process(process, event_sink),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("OpenCode worker timed out")
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise RuntimeError(self._failure_message("OpenCode worker", events, stderr))
        tokens_used, cost_usd = _event_usage(events)
        return OpenCodeResult(text="\n".join(text_parts).strip(), events=events, tokens_used=tokens_used, cost_usd=cost_usd)

    async def _run_docker(
        self,
        *,
        prompt: str,
        workdir: Path,
        model: str | None,
        agent: str | None,
        env_extras: dict[str, str] | None = None,
        provider: str | None = None,
        adapter: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        custom_provider: bool = False,
        event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> OpenCodeResult:
        image = os.getenv("NEXUSFORGE_RUNNER_IMAGE", "nexusforge-opencode-runner:latest")
        common_git = self._worktree_common_git_dir(workdir)
        command = [
            "docker", "run", "--rm", "--network", os.getenv("NEXUSFORGE_RUNNER_NETWORK", "none"),
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", os.getenv("NEXUSFORGE_RUNNER_MEMORY", "4g"), "--cpus", os.getenv("NEXUSFORGE_RUNNER_CPUS", "2"),
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m", "-v", f"{workdir}:/workspace:rw",
        ]
        if common_git is not None:
            # Git worktree links contain an absolute gitdir. Mount only the
            # managed clone's metadata at that same path, never the source repo.
            command.extend(["-v", f"{common_git}:{common_git}:rw"])
        docker_environment = os.environ.copy()
        docker_environment["NEXUSFORGE_TASK_PROMPT"] = prompt
        command.extend(["-e", "NEXUSFORGE_TASK_PROMPT"])
        for key in (
            "NEXUSFORGE_OPENCODE_API_KEY",
            "OPENCODE_AUTH_JSON_B64",
            "OPENCODE_CONFIG",
            "OPENCODE_SERVER_PASSWORD",
        ):
            if custom_provider and key != "OPENCODE_SERVER_PASSWORD":
                continue
            if value := os.getenv(key):
                docker_environment[key] = value
                command.extend(["-e", key])
        if env_extras:
            for key, value in env_extras.items():
                docker_environment[key] = value
                command.extend(["-e", key])
        if custom_provider and base_url and model:
            if self._is_openrouter(provider, base_url):
                openrouter_model = self._openrouter_model_id(model)
                docker_environment["OPENROUTER_API_KEY"] = api_key or ""
                docker_environment["OPENCODE_CONFIG_CONTENT"] = self._openrouter_config(
                    openrouter_model
                )
                docker_environment["NEXUSFORGE_MODEL"] = f"openrouter/{openrouter_model}"
                command.extend(
                    [
                        "-e",
                        "OPENROUTER_API_KEY",
                        "-e",
                        "OPENCODE_CONFIG_CONTENT",
                        "-e",
                        "NEXUSFORGE_MODEL",
                    ]
                )
            else:
                docker_environment["NEXUSFORGE_OPENCODE_API_KEY"] = api_key or "not-required"
                docker_environment["NEXUSFORGE_PROVIDER_CONFIGURED"] = "1"
                docker_environment["OPENCODE_CONFIG_CONTENT"] = self._provider_config(
                    provider=provider,
                    adapter=adapter,
                    base_url=base_url,
                    model=model,
                )
                docker_environment["NEXUSFORGE_MODEL"] = f"nexusforge/{model}"
                command.extend(
                    [
                        "-e",
                        "NEXUSFORGE_OPENCODE_API_KEY",
                        "-e",
                        "NEXUSFORGE_PROVIDER_CONFIGURED",
                        "-e",
                        "OPENCODE_CONFIG_CONTENT",
                        "-e",
                        "NEXUSFORGE_MODEL",
                    ]
                )
        elif model:
            docker_environment["NEXUSFORGE_MODEL"] = model
            command.extend(["-e", "NEXUSFORGE_MODEL"])
        if agent:
            docker_environment["NEXUSFORGE_AGENT"] = agent
            command.extend(["-e", "NEXUSFORGE_AGENT"])
        command.append(image)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=docker_environment,
        )
        try:
            events, text_parts, stderr = await asyncio.wait_for(
                self._stream_process(process, event_sink),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("OpenCode sandbox timed out")
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise RuntimeError(self._failure_message("OpenCode sandbox", events, stderr))
        tokens_used, cost_usd = _event_usage(events)
        return OpenCodeResult(text="\n".join(text_parts).strip(), events=events, tokens_used=tokens_used, cost_usd=cost_usd)

    def _worktree_common_git_dir(self, workdir: Path) -> Path | None:
        dot_git = workdir / ".git"
        if not dot_git.is_file():
            return dot_git if dot_git.is_dir() else None
        try:
            value = dot_git.read_text().strip()
        except OSError:
            return None
        if not value.startswith("gitdir: "):
            return None
        git_dir = Path(value.removeprefix("gitdir: ")).resolve()
        if git_dir.parent.name != "worktrees":
            return None
        return git_dir.parent.parent

    async def _stream_process(
        self,
        process: asyncio.subprocess.Process,
        event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None,
    ) -> tuple[list[dict[str, Any]], list[str], str]:
        """Parse runner JSONL while it is produced instead of after exit."""
        assert process.stdout is not None and process.stderr is not None
        events: list[dict[str, Any]] = []
        text_parts: list[str] = []

        async def read_stderr() -> str:
            return (await process.stderr.read()).decode("utf-8", "replace")

        stderr_task = asyncio.create_task(read_stderr())
        while line_bytes := await process.stdout.readline():
            line = line_bytes.decode("utf-8", "replace").rstrip()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"type": "runner_output", "text": line}
            if not isinstance(event, dict):
                event = {"type": "runner_output", "value": event}
            events.append(event)
            if event_sink:
                await event_sink(event)
            text_parts.extend(_event_text_parts(event))
        await process.wait()
        return events, text_parts, await stderr_task

    def _provider_config(
        self,
        *,
        provider: str | None,
        adapter: str | None,
        base_url: str,
        model: str,
    ) -> str:
        npm_package = (
            "@ai-sdk/anthropic" if adapter == "anthropic" else "@ai-sdk/openai-compatible"
        )
        return json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "nexusforge": {
                    "npm": npm_package,
                    "name": provider or "NexusForge configured provider",
                    "options": {
                        "baseURL": base_url,
                        "apiKey": "{env:NEXUSFORGE_OPENCODE_API_KEY}",
                    },
                    "models": {model: {"name": model}},
                }
            },
        })

    @staticmethod
    def _is_openrouter(provider: str | None, base_url: str | None) -> bool:
        return "openrouter" in (provider or "").lower() or "openrouter.ai" in (
            base_url or ""
        ).lower()

    @staticmethod
    def _openrouter_config(model: str) -> str:
        model = OpenCodeRunner._openrouter_model_id(model)
        return json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "provider": {"openrouter": {"models": {model: {"name": model}}}},
            }
        )

    @staticmethod
    def _openrouter_model_id(model: str) -> str:
        return model.removeprefix("openrouter/")

    @staticmethod
    def _failure_message(prefix: str, events: list[dict[str, Any]], stderr: str) -> str:
        details: list[str] = []
        for event in reversed(events):
            if event.get("type") != "error":
                continue
            error = event.get("error")
            if not isinstance(error, dict):
                continue
            data = error.get("data")
            message = data.get("message") if isinstance(data, dict) else error.get("message")
            reference = data.get("ref") if isinstance(data, dict) else None
            if isinstance(message, str) and message:
                details.append(message)
            if isinstance(reference, str) and reference:
                details.append(f"reference {reference}")
            break
        clean_stderr = _strip_ansi(stderr).strip()
        if clean_stderr:
            details.append(clean_stderr[-2000:])
        return f"{prefix} failed" + (f": {'; '.join(details)}" if details else "")


async def stream_container_events(*, image: str, worktree: Path, prompt_file: Path) -> AsyncIterator[dict]:
    yield {"event": "sandbox_prepared", "image": image, "worktree": str(worktree)}


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)


def _event_text_parts(event: dict[str, Any]) -> list[str]:
    """Extract assistant text from both legacy and current OpenCode JSONL."""

    values: list[Any] = [event.get("text"), event.get("content")]
    part = event.get("part")
    if isinstance(part, dict):
        values.extend([part.get("text"), part.get("content")])
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text = item["text"]
                    if text and text not in result:
                        result.append(text)
    return result


def _response_cost(response: Any) -> float:
    for source in (getattr(response, "usage", None), getattr(response, "model_extra", None)):
        if isinstance(source, dict) and isinstance(source.get("cost"), (int, float)):
            return float(source["cost"])
        value = getattr(source, "cost", None)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _event_usage(events: list[dict[str, Any]]) -> tuple[int, float]:
    tokens, cost = 0, 0.0
    for event in events:
        part = event.get("part")
        usage = event.get("usage")
        candidates = [event]
        if isinstance(usage, dict):
            candidates.append(usage)
        if isinstance(part, dict):
            candidates.append(part)
        for candidate in candidates:
            for key in ("total_tokens", "tokens_used", "tokens"):
                value = candidate.get(key)
                if isinstance(value, (int, float)):
                    tokens = max(tokens, int(value))
                elif isinstance(value, dict):
                    explicit_total = value.get("total") or value.get("total_tokens")
                    if isinstance(explicit_total, (int, float)):
                        tokens = max(tokens, int(explicit_total))
                    else:
                        token_total = sum(
                            int(item)
                            for name, item in value.items()
                            if name in {"input", "output", "reasoning"}
                            and isinstance(item, (int, float))
                        )
                        tokens = max(tokens, token_total)
            value = candidate.get("cost_usd", candidate.get("cost"))
            if isinstance(value, (int, float)):
                cost = max(cost, float(value))
    return tokens, cost
