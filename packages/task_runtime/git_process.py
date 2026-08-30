"""Isolated Git subprocess helpers for host-mounted repositories."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

_ORCHESTRATOR_GIT_CONFIG = (
    "-c",
    "user.name=NexusForge Orchestrator",
    "-c",
    "user.email=orchestrator@nexusforge.local",
    "-c",
    "commit.gpgSign=false",
)


async def git_capture(
    cwd: Path,
    *args: str,
    stderr_to_stdout: bool = False,
) -> tuple[int, str]:
    """Run Git with an ephemeral protected safe-directory configuration.

    A local clone starts ``git upload-pack`` as a child process. A ``git -c``
    option is not sufficient for its dubious-ownership check, while a global
    config is protected configuration and is inherited by the whole process
    tree. Pointing ``GIT_CONFIG_GLOBAL`` at a private temporary file provides
    that behavior without changing the worker image or the host user's config.
    """

    descriptor, config_name = tempfile.mkstemp(prefix="nexusforge-git-", suffix=".config")
    config_path = Path(config_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as config_file:
            config_file.write("[safe]\n\tdirectory = *\n")

        environment = os.environ.copy()
        # Remove Compose-era command-scope configuration so the temporary
        # protected config is the single, predictable source of Git trust.
        environment.pop("GIT_CONFIG_COUNT", None)
        for key in tuple(environment):
            if key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
                environment.pop(key, None)
        environment["GIT_CONFIG_GLOBAL"] = str(config_path)

        process = await asyncio.create_subprocess_exec(
            "git",
            *_ORCHESTRATOR_GIT_CONFIG,
            *args,
            cwd=cwd,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT if stderr_to_stdout else asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        combined = stdout if stderr_to_stdout else stdout + (stderr or b"")
        return process.returncode or 0, combined.decode("utf-8", "replace").strip()
    finally:
        config_path.unlink(missing_ok=True)
