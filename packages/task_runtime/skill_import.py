"""Import the Agency Agents Markdown roster into versioned NexusForge skills."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


FRONT_MATTER = re.compile(r"^---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)$", re.DOTALL)


@dataclass(frozen=True)
class ImportedSkill:
    slug: str
    name: str
    description: str
    division: str
    prompt: str
    source_path: str
    source_hash: str


def _metadata(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip().strip('"\'')
    return values


def discover_skills(root: Path) -> list[ImportedSkill]:
    """Load only agent Markdown files with front matter, never integrations/docs."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("Agency Agents source directory does not exist")
    result: list[ImportedSkill] = []
    for file in root.rglob("*.md"):
        if any(part in {".git", "integrations", "examples"} for part in file.parts):
            continue
        raw = file.read_text(encoding="utf-8")
        match = FRONT_MATTER.match(raw)
        if not match:
            continue
        meta = _metadata(match.group("meta"))
        name = meta.get("name") or meta.get("title")
        if not name:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        result.append(ImportedSkill(
            slug=slug, name=name, description=meta.get("description", ""),
            division=file.relative_to(root).parts[0] if len(file.relative_to(root).parts) > 1 else "general",
            prompt=match.group("body").strip(), source_path=str(file),
            source_hash=hashlib.sha256(raw.encode()).hexdigest(),
        ))
    return sorted(result, key=lambda item: item.slug)
