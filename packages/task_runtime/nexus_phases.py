"""NEXUS 7-phase doctrine definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NexusPhase:
    key: str
    name: str
    description: str


NEXUS_PHASES: dict[str, NexusPhase] = {
    p.key: p
    for p in [
        NexusPhase("discover", "Discover", "Understand the problem, gather requirements, analyse existing code"),
        NexusPhase("design", "Design", "Architecture decisions, API contracts, data models"),
        NexusPhase("build", "Build", "Implement features, write code, create tests"),
        NexusPhase("verify", "Verify", "Run tests, lint, type-check, validate correctness"),
        NexusPhase("harden", "Harden", "Security review, performance audit, edge-case hardening"),
        NexusPhase("deploy", "Deploy", "Packaging, CI/CD, release orchestration"),
        NexusPhase("monitor", "Monitor", "Observability, logging, alerting, post-deploy validation"),
    ]
}


def map_task_to_phases(task_description: str) -> list[str]:
    """Heuristic mapping of a task description to likely NEXUS phases."""
    lower = task_description.lower()
    phases: list[str] = []
    if any(w in lower for w in ("research", "understand", "explore", "analyse", "analyze", "inspect")):
        phases.append("discover")
    if any(w in lower for w in ("design", "architect", "plan", "schema", "api contract")):
        phases.append("design")
    if any(w in lower for w in ("implement", "build", "create", "add", "write", "code", "fix", "refactor")):
        phases.append("build")
    if any(w in lower for w in ("test", "verify", "lint", "check", "validate")):
        phases.append("verify")
    if any(w in lower for w in ("security", "harden", "audit", "performance", "optimise", "optimize")):
        phases.append("harden")
    if any(w in lower for w in ("deploy", "release", "package", "ci", "cd")):
        phases.append("deploy")
    if any(w in lower for w in ("monitor", "log", "alert", "observ", "metric")):
        phases.append("monitor")
    if not phases:
        phases = ["discover", "build", "verify"]
    return phases
