"""Deterministic hybrid retrieval for versioned role templates.

The first production-shaped release deliberately has a strong lexical path so
planning still works when no embedding provider is configured.  Stored vector
scores can be supplied by callers and are blended with the lexical score.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable


TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.-]+")
SOFTWARE_DIVISIONS = frozenset(
    {"engineering", "testing", "security", "design", "product", "project-management"}
)


@dataclass(frozen=True)
class RetrievedRole:
    role: Any
    score: float
    reasons: tuple[str, ...]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.role, name)


def _tokens(value: str) -> set[str]:
    return set(TOKEN.findall(value.lower()))


def retrieve_roles(
    goal: str,
    roles: Iterable[Any],
    *,
    limit: int = 14,
    vector_scores: dict[str, float] | None = None,
) -> list[RetrievedRole]:
    """Rank roles without placing the entire catalog in the planner prompt."""

    query = _tokens(goal)
    vector_scores = vector_scores or {}
    ranked: list[RetrievedRole] = []
    for role in roles:
        if not getattr(role, "is_active", True):
            continue
        slug = str(getattr(role, "slug", ""))
        division = str(getattr(role, "division", "general"))
        haystack = _tokens(
            " ".join(
                (
                    slug,
                    str(getattr(role, "name", "")),
                    str(getattr(role, "description", "")),
                    division,
                    " ".join(getattr(role, "capabilities", []) or []),
                )
            )
        )
        overlap = query & haystack
        lexical = len(overlap) / math.sqrt(max(1, len(query) * len(haystack)))
        phrase_bonus = 0.0
        lower_goal = goal.lower()
        if any(term in lower_goal and term in haystack for term in ("test", "review", "security", "frontend", "backend", "database", "deploy", "document")):
            phrase_bonus = 0.2
        division_bonus = 0.16 if division in SOFTWARE_DIVISIONS else 0.0
        executable_bonus = 0.12 if getattr(role, "is_executable", False) else 0.0
        vector = max(0.0, min(1.0, vector_scores.get(slug, 0.0)))
        score = lexical * 0.52 + vector * 0.28 + phrase_bonus + division_bonus + executable_bonus
        reasons = tuple(sorted(overlap)[:5]) or (division,)
        ranked.append(RetrievedRole(role=role, score=round(score, 5), reasons=reasons))

    ranked.sort(key=lambda item: (-item.score, item.slug))
    selected = ranked[:limit]
    if not selected:
        return []

    # Guarantee the planner sees at least one implementer and one verifier.
    for keywords in (("developer", "engineer"), ("review", "test", "quality")):
        if any(any(word in item.slug for word in keywords) for item in selected):
            continue
        fallback = next(
            (item for item in ranked if any(word in item.slug for word in keywords)),
            None,
        )
        if fallback is not None:
            selected[-1] = fallback
    return sorted({item.slug: item for item in selected}.values(), key=lambda item: (-item.score, item.slug))
