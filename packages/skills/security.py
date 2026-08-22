"""SkillSecurity — path validation, symlink checks, and trust boundary enforcement."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from packages.skills.registry import SkillProtocol

logger = logging.getLogger(__name__)


class SkillSecurity:
    """Validates that skill file access and execution stay within safe bounds.

    Rules:
        1. All resource / script paths must resolve within *base_dir*.
        2. Symlinks that escape *base_dir* are rejected.
        3. Trust boundaries can be enforced per-skill via ``enforce_trust_boundary``.
    """

    def __init__(self, base_dir: str | Path = ".") -> None:
        self.base_dir = Path(base_dir).resolve()

    def validate_path(self, path: str | Path, base_dir: str | Path | None = None) -> bool:
        """Check that *path* resolves within *base_dir* (no traversal).

        Returns True if the path is safe, False otherwise.
        """
        base = Path(base_dir).resolve() if base_dir else self.base_dir
        resolved = (base / path).resolve()

        try:
            resolved.relative_to(base)
        except ValueError:
            logger.warning(
                "SkillSecurity: path traversal blocked — '%s' escapes '%s'",
                path,
                base,
            )
            return False

        return True

    def check_symlinks(self, path: str | Path) -> bool:
        """Reject any path that is or contains a symlink.

        Returns True if the path is safe (no symlinks).
        """
        p = Path(path)

        # Walk the path from the outermost component inward.
        parts = []
        current = p.resolve()
        while current != current.parent:
            parts.append(current)
            current = current.parent
        parts.reverse()

        for part in parts:
            if part.is_symlink():
                link_target = part.readlink()
                resolved_target = part.resolve()

                # The resolved target must still be under base_dir.
                try:
                    resolved_target.relative_to(self.base_dir)
                except ValueError:
                    logger.warning(
                        "SkillSecurity: symlink escape — '%s' -> '%s' escapes '%s'",
                        part,
                        resolved_target,
                        self.base_dir,
                    )
                    return False

        return True

    def enforce_trust_boundary(self, skill: SkillProtocol, context: dict) -> bool:
        """Verify that a skill is allowed to run in the given context.

        Trust rules:
            - If ``context["allowed_skills"]`` is set, the skill ID must be in it.
            - If ``context["denied_skills"]`` is set, the skill ID must NOT be in it.
            - If the skill has a ``_source`` with ``source_type="file"``, the
              source path must pass ``validate_path``.
        """
        # Check allow / deny lists.
        allowed = context.get("allowed_skills")
        if allowed is not None and skill.skill_id not in allowed:
            logger.warning(
                "SkillSecurity: skill '%s' not in allowlist", skill.skill_id
            )
            return False

        denied = context.get("denied_skills")
        if denied is not None and skill.skill_id in denied:
            logger.warning(
                "SkillSecurity: skill '%s' is in denylist", skill.skill_id
            )
            return False

        # If the skill came from a file, validate the source path.
        source = getattr(skill, "source", None)
        if source is not None and getattr(source, "source_type", "") == "file":
            source_path = getattr(source, "source_path", "")
            if source_path and not self.validate_path(source_path):
                return False

        return True

    def sanitize_filename(self, name: str) -> str:
        """Strip path separators and traversal sequences from a filename."""
        # Remove directory components.
        name = os.path.basename(name)
        # Block double-dots.
        name = name.replace("..", "")
        return name
