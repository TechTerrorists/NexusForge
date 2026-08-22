"""Skill sources — loaders that produce SkillProtocol instances from various origins."""

from packages.skills.sources.file_source import FileSkillSource
from packages.skills.sources.inline_source import InlineSkillSource

__all__ = ["FileSkillSource", "InlineSkillSource"]
