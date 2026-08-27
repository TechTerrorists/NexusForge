"""Import agency-agents skills into the database with optional embeddings."""

from __future__ import annotations

import logging
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models import SkillVersion
from packages.task_runtime.skill_import import discover_skills

logger = logging.getLogger(__name__)


async def import_skills(
    session_factory: async_sessionmaker[AsyncSession],
    source_dir: Path,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, int]:
    """Import skills from agency-agents directory into SkillVersion table.

    Returns dict with counts: {"imported": N, "skipped": N, "total": N}
    """
    skills = discover_skills(source_dir)
    imported = 0
    skipped = 0

    async with session_factory() as db:
        for skill in skills:
            existing = await db.scalar(
                select(SkillVersion).where(
                    SkillVersion.slug == skill.slug,
                    SkillVersion.source_hash == skill.source_hash,
                )
            )
            if existing:
                skipped += 1
                continue

            version_row = SkillVersion(
                slug=skill.slug,
                name=skill.name,
                description=skill.description,
                division=skill.division,
                prompt=skill.prompt,
                source_path=skill.source_path,
                source_hash=skill.source_hash,
                version=1,
                is_active=True,
            )
            db.add(version_row)
            imported += 1

        await db.commit()

    logger.info(
        "Skill import complete: imported=%d skipped=%d total=%d",
        imported, skipped, len(skills),
    )
    return {"imported": imported, "skipped": skipped, "total": len(skills)}
