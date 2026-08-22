"""FileSkillSource — loads SkillProtocol instances from SKILL.md files on disk."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import yaml

from packages.skills.registry import Skill, SkillSource

logger = logging.getLogger(__name__)

# Required frontmatter fields.
REQUIRED_FIELDS = {"id", "name", "description"}


class FileSkillSource:
    """Loads skills from ``SKILL.md`` files (YAML frontmatter + markdown body).

    File format::

        ---
        id: code-review
        name: Code Review Skill
        description: Reviews code for quality, security, and correctness.
        tags: [code, review, quality]
        required_tools: [github, shell]
        ---
        # Code Review Skill

        ## Steps

        1. Read the diff from the pull request.
        2. Check for common issues.
        3. ...
    """

    def load_from_file(self, path: str | Path) -> Skill:
        """Parse a SKILL.md file and return a Skill instance.

        Raises:
            FileNotFoundError: if the file does not exist.
            ValueError: if required fields are missing.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {path}")

        content = path.read_text(encoding="utf-8")
        frontmatter, body = self._parse_frontmatter(content)

        # Validate required fields.
        missing = REQUIRED_FIELDS - set(frontmatter.keys())
        if missing:
            raise ValueError(f"Skill file '{path}' missing required fields: {missing}")

        # Parse optional list fields.
        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        required_tools = frontmatter.get("required_tools", [])
        if isinstance(required_tools, str):
            required_tools = [t.strip() for t in required_tools.split(",")]

        # Parse resources and scripts from the body.
        resources, scripts = self._extract_resources_and_scripts(body)

        source = SkillSource(
            source_type="file",
            source_path=str(path.resolve()),
        )

        return Skill(
            _skill_id=frontmatter["id"],
            _name=frontmatter["name"],
            _description=frontmatter["description"],
            _tags=tags,
            _required_tools=required_tools,
            _steps=self._parse_steps(body),
            _resources=resources,
            _scripts=scripts,
            _source=source,
        )

    def load_from_directory(self, directory: str | Path) -> list[Skill]:
        """Load all SKILL.md files in *directory* (recursively)."""
        directory = Path(directory)
        skills: list[Skill] = []

        for root, _dirs, files in os.walk(directory):
            for fname in files:
                if fname == "SKILL.md":
                    try:
                        skill = self.load_from_file(Path(root) / fname)
                        skills.append(skill)
                    except (ValueError, FileNotFoundError) as exc:
                        logger.warning("FileSkillSource: skipping %s: %s", root, exc)

        logger.info("FileSkillSource: loaded %d skills from %s", len(skills), directory)
        return skills

    # ---- internal helpers -------------------------------------------------- #

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict, str]:
        """Split YAML frontmatter from markdown body."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
                return frontmatter, body

        return {}, content

    @staticmethod
    def _parse_steps(body: str) -> list[dict[str, str]]:
        """Extract numbered steps from the markdown body."""
        steps: list[dict[str, str]] = []
        step_pattern = re.compile(r"^\d+\.\s+(.+)$", re.MULTILINE)

        for match in step_pattern.finditer(body):
            steps.append({"instruction": match.group(1).strip()})

        return steps

    @staticmethod
    def _extract_resources_and_scripts(body: str) -> tuple[dict[str, str], dict[str, str]]:
        """Extract resource and script blocks from the body.

        Resources are marked with ``## Resource: <name>`` headers.
        Scripts are marked with ``## Script: <name>`` headers.
        """
        resources: dict[str, str] = {}
        scripts: dict[str, str] = {}

        # Split on level-2 headers.
        sections = re.split(r"^## ", body, flags=re.MULTILINE)

        for section in sections:
            if not section.strip():
                continue

            first_line, _, rest = section.partition("\n")
            first_line = first_line.strip()
            content = rest.strip()

            if first_line.startswith("Resource:"):
                name = first_line[len("Resource:"):].strip()
                resources[name] = content
            elif first_line.startswith("Script:"):
                name = first_line[len("Script:"):].strip()
                scripts[name] = content

        return resources, scripts
