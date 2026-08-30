from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.task_runtime.git_process import git_capture
from packages.task_runtime.scheduler import TaskScheduler, _redact


@pytest.mark.asyncio
async def test_scheduler_git_commands_use_process_local_safe_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[object, ...]] = []
    protected_configs: list[str] = []
    protected_config_paths: list[Path] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"ok", b""

    async def fake_subprocess(*args: object, **kwargs: object) -> FakeProcess:
        calls.append(args)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        config_path = environment["GIT_CONFIG_GLOBAL"]
        protected_config_paths.append(Path(config_path))
        protected_configs.append(protected_config_paths[-1].read_text(encoding="utf-8"))
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    scheduler = TaskScheduler(SimpleNamespace())  # type: ignore[arg-type]

    code, output = await scheduler._git_capture(tmp_path, "status", "--porcelain")

    assert code == 0
    assert output == "ok"
    assert calls == [
        (
            "git",
            "-c",
            "user.name=NexusForge Orchestrator",
            "-c",
            "user.email=orchestrator@nexusforge.local",
            "-c",
            "commit.gpgSign=false",
            "status",
            "--porcelain",
        )
    ]
    assert protected_configs == ["[safe]\n\tdirectory = *\n"]
    assert all(not path.exists() for path in protected_config_paths)


@pytest.mark.asyncio
async def test_protected_config_reaches_local_clone_upload_pack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "managed" / "integration"
    source.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True, capture_output=True)
    (source / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=NexusForge Test",
            "-c",
            "user.email=test@nexusforge.local",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=source,
        check=True,
        capture_output=True,
    )
    destination.parent.mkdir()
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")

    code, output = await git_capture(
        destination.parent,
        "clone",
        "--no-hardlinks",
        "--branch",
        "main",
        str(source),
        str(destination),
    )

    assert code == 0, output
    assert (destination / "README.md").read_text(encoding="utf-8") == "# fixture\n"


@pytest.mark.asyncio
async def test_managed_cherry_pick_has_an_orchestrator_identity(tmp_path: Path) -> None:
    source = tmp_path / "source"
    integration = tmp_path / "integration"
    source.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True, capture_output=True)
    (source / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=source, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@nexusforge.local",
            "commit",
            "-m",
            "base",
        ],
        cwd=source,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "checkout", "-b", "agent-step"], cwd=source, check=True, capture_output=True)
    (source / "artifact.txt").write_text("agent output\n", encoding="utf-8")
    subprocess.run(["git", "add", "artifact.txt"], cwd=source, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=NexusForge Agent",
            "-c",
            "user.email=agents@nexusforge.local",
            "commit",
            "-m",
            "agent output",
        ],
        cwd=source,
        check=True,
        capture_output=True,
    )
    step_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "checkout", "main"], cwd=source, check=True, capture_output=True)
    clone_code, clone_output = await git_capture(tmp_path, "clone", str(source), str(integration))
    assert clone_code == 0, clone_output

    code, output = await git_capture(integration, "cherry-pick", step_commit)

    assert code == 0, output
    assert (integration / "artifact.txt").read_text(encoding="utf-8") == "agent output\n"


def test_usage_counts_are_visible_while_credentials_are_redacted() -> None:
    assert _redact(
        {
            "tokens": 150,
            "run_tokens": 300,
            "api_key": "provider-secret",
            "access_token": "access-secret",
        }
    ) == {
        "tokens": 150,
        "run_tokens": 300,
        "api_key": "[REDACTED]",
        "access_token": "[REDACTED]",
    }
