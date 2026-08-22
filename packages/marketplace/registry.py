import os
import uuid
import shutil
import yaml
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA = {
    "required": ["name", "version", "description", "agents", "workflows"],
    "optional": ["dependencies", "author", "license", "tags", "domain"],
}


class TemplateRegistry:
    def __init__(self, templates_dir: str):
        self._templates_dir = templates_dir
        self._templates: dict[str, dict[str, Any]] = {}
        os.makedirs(templates_dir, exist_ok=True)
        self._load_templates()

    def _load_templates(self) -> None:
        """Load all templates from the templates directory."""
        for entry in os.scandir(self._templates_dir):
            if entry.is_dir():
                manifest_path = os.path.join(entry.path, "manifest.yaml")
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, "r") as f:
                            manifest = yaml.safe_load(f)
                        if manifest and "name" in manifest:
                            template_id = manifest.get("id", entry.name)
                            manifest["id"] = template_id
                            manifest["_path"] = entry.path
                            self._templates[template_id] = manifest
                    except Exception as e:
                        logger.error(
                            f"Failed to load template from {entry.path}: {e}"
                        )

    def _validate_manifest(self, manifest: dict[str, Any]) -> list[str]:
        """Validate manifest schema. Returns list of errors."""
        errors = []
        for field in MANIFEST_SCHEMA["required"]:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")

        if "version" in manifest:
            version = manifest["version"]
            if not isinstance(version, str):
                errors.append("Version must be a string")

        if "agents" in manifest and not isinstance(manifest["agents"], dict):
            errors.append("Agents must be a dictionary")

        if "workflows" in manifest and not isinstance(manifest["workflows"], dict):
            errors.append("Workflows must be a dictionary")

        return errors

    def register(self, manifest: dict[str, Any]) -> str:
        """Register a new template. Returns template_id."""
        errors = self._validate_manifest(manifest)
        if errors:
            raise ValueError(
                f"Invalid manifest: {'; '.join(errors)}"
            )

        template_id = manifest.get("id", str(uuid.uuid4()))
        manifest["id"] = template_id

        template_dir = os.path.join(self._templates_dir, template_id)
        os.makedirs(template_dir, exist_ok=True)

        manifest_path = os.path.join(template_dir, "manifest.yaml")
        save_manifest = {k: v for k, v in manifest.items() if not k.startswith("_")}
        with open(manifest_path, "w") as f:
            yaml.dump(save_manifest, f, default_flow_style=False)

        manifest["_path"] = template_dir
        self._templates[template_id] = manifest
        logger.info(f"Registered template: {template_id}")
        return template_id

    def get(self, template_id: str) -> Optional[dict[str, Any]]:
        """Get a template by ID."""
        return self._templates.get(template_id)

    def list_templates(self, domain: str = None) -> list[dict[str, Any]]:
        """List all templates, optionally filtered by domain."""
        templates = list(self._templates.values())
        if domain:
            templates = [t for t in templates if t.get("domain") == domain]
        return [
            {k: v for k, v in t.items() if not k.startswith("_")}
            for t in templates
        ]

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search templates by name or description."""
        query_lower = query.lower()
        results = []
        for template in self._templates.values():
            name = template.get("name", "").lower()
            desc = template.get("description", "").lower()
            tags = [t.lower() for t in template.get("tags", [])]
            if (
                query_lower in name
                or query_lower in desc
                or any(query_lower in t for t in tags)
            ):
                results.append(
                    {k: v for k, v in template.items() if not k.startswith("_")}
                )
        return results

    def delete(self, template_id: str) -> bool:
        """Delete a template."""
        if template_id not in self._templates:
            return False

        template = self._templates[template_id]
        template_path = template.get("_path")
        if template_path and os.path.exists(template_path):
            shutil.rmtree(template_path)

        del self._templates[template_id]
        logger.info(f"Deleted template: {template_id}")
        return True
