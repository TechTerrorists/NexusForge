"""Import agency-agents skills into the database with optional embeddings."""

from __future__ import annotations

import logging
from pathlib import Path
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models import RoleTemplateVersion, SkillDefinitionVersion, SkillVersion
from packages.task_runtime.skill_import import discover_skills

logger = logging.getLogger(__name__)


async def import_skills(
    session_factory: async_sessionmaker[AsyncSession],
    source_dir: Path,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, int]:
    """Import Agency Agents as role templates and compatibility skill rows.

    Returns dict with counts: {"imported": N, "skipped": N, "total": N}
    """
    skills = discover_skills(source_dir)
    imported = 0
    skipped = 0

    async with session_factory() as db:
        if db.bind and db.bind.dialect.name == "postgresql":
            await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('nexusforge-workforce-import'))"))
        for skill in skills:
            existing_role = await db.scalar(
                select(RoleTemplateVersion).where(
                    RoleTemplateVersion.slug == skill.slug,
                    RoleTemplateVersion.source_hash == skill.source_hash,
                )
            )
            if existing_role is None:
                current_role = await db.scalar(
                    select(RoleTemplateVersion).where(
                        RoleTemplateVersion.slug == skill.slug,
                        RoleTemplateVersion.is_active.is_(True),
                    )
                )
                if current_role is not None:
                    current_role.is_active = False
                db.add(
                    RoleTemplateVersion(
                        slug=skill.slug,
                        name=skill.name,
                        description=skill.description,
                        division=skill.division,
                        prompt=skill.prompt,
                        source_path=skill.source_path,
                        source_hash=skill.source_hash,
                        version=(current_role.version + 1) if current_role else 1,
                        capabilities=_infer_capabilities(
                            skill.division, skill.name, skill.description
                        ),
                        compatible_tools=[],
                        is_executable=skill.division in {
                            "engineering",
                            "testing",
                            "security",
                            "design",
                            "product",
                            "project-management",
                        },
                    )
                )

            existing_definition = await db.scalar(
                select(SkillDefinitionVersion).where(
                    SkillDefinitionVersion.slug == skill.slug,
                    SkillDefinitionVersion.tenant_id.is_(None),
                    SkillDefinitionVersion.source_hash == skill.source_hash,
                )
            )
            if existing_definition is None:
                current_definition = await db.scalar(
                    select(SkillDefinitionVersion).where(
                        SkillDefinitionVersion.slug == skill.slug,
                        SkillDefinitionVersion.tenant_id.is_(None),
                        SkillDefinitionVersion.is_active.is_(True),
                    )
                )
                if current_definition is not None:
                    current_definition.is_active = False
                db.add(
                    SkillDefinitionVersion(
                        slug=skill.slug,
                        name=skill.name,
                        description=skill.description,
                        procedure=skill.prompt,
                        required_capabilities=_infer_capabilities(
                            skill.division, skill.name, skill.description
                        ),
                        source_path=skill.source_path,
                        source_hash=skill.source_hash,
                        version=(current_definition.version + 1) if current_definition else 1,
                    )
                )

            existing = await db.scalar(
                select(SkillVersion).where(
                    SkillVersion.slug == skill.slug,
                    SkillVersion.source_hash == skill.source_hash,
                )
            )
            if existing:
                skipped += 1
                continue

            current_legacy = await db.scalar(
                select(SkillVersion).where(
                    SkillVersion.slug == skill.slug,
                    SkillVersion.is_active.is_(True),
                )
            )
            if current_legacy is not None:
                current_legacy.is_active = False
            version_row = SkillVersion(
                slug=skill.slug,
                name=skill.name,
                description=skill.description,
                division=skill.division,
                prompt=skill.prompt,
                source_path=skill.source_path,
                source_hash=skill.source_hash,
                version=(current_legacy.version + 1) if current_legacy else 1,
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


def _infer_capabilities(division: str, name: str, description: str) -> list[str]:
    text = f"{division} {name} {description}".lower()
    capabilities = {"text_generation"}
    if division in {"engineering", "testing", "security", "design"}:
        capabilities.add("repository_read")
    if division in {"engineering", "testing"}:
        capabilities.update({"code_generation", "tool_execution"})
    if any(word in text for word in ("research", "intelligence", "analyst")):
        capabilities.add("knowledge_retrieval")
    if any(word in text for word in ("browser", "frontend", "ui", "ux")):
        capabilities.add("browser_automation")
    if any(word in text for word in ("review", "audit", "quality", "test")):
        capabilities.add("evaluation")
    return sorted(capabilities)
