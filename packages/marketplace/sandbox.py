import os
import re
import yaml
import shutil
import logging
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    (r"subprocess\.(run|call|Popen|check_output)", "subprocess usage detected"),
    (r"os\.system\(", "os.system usage detected"),
    (r"os\.popen\(", "os.popen usage detected"),
    (r"\beval\s*\(", "eval() usage detected"),
    (r"\bexec\s*\(", "exec() usage detected"),
    (r"__import__\s*\(", "__import__() usage detected"),
    (r"compile\s*\(", "compile() usage detected"),
    (r"pickle\.loads?\s*\(", "pickle deserialization detected"),
    (r"yaml\.load\s*\(", "yaml.load() without SafeLoader detected"),
    (r"open\s*\(.*['\"]w", "file write operation detected"),
    (r"shutil\.rmtree\(", "directory removal detected"),
    (r"rm\s+-rf", "recursive removal command detected"),
]

REQUIRED_MANIFEST_FIELDS = ["name", "version", "description"]
OPTIONAL_MANIFEST_FIELDS = [
    "agents", "workflows", "dependencies",
    "author", "license", "tags", "domain",
]


class ReviewerGateway:
    def __init__(self):
        self._scan_patterns = DANGEROUS_PATTERNS

    async def validate_template(
        self, manifest: dict[str, Any], config: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Validate a template in an isolated environment.

        Returns:
            Dict with passed (bool), errors (list), warnings (list), score (float)
        """
        errors: list[str] = []
        warnings: list[str] = []
        score = 1.0

        temp_dir = tempfile.mkdtemp(prefix="template_review_")
        try:
            manifest_errors = self._validate_manifest_schema(manifest)
            errors.extend(manifest_errors)
            if manifest_errors:
                score -= 0.3 * len(manifest_errors)

            config_errors = self._validate_config(config or {})
            errors.extend(config_errors)
            if config_errors:
                score -= 0.2 * len(config_errors)

            dangerous = self._scan_dangerous_patterns(manifest, config or {})
            warnings.extend(dangerous)
            if dangerous:
                score -= 0.1 * len(dangerous)

            dep_warnings = self._check_dependencies(manifest)
            warnings.extend(dep_warnings)
            if dep_warnings:
                score -= 0.05 * len(dep_warnings)

            naming_warnings = self._check_naming_conventions(manifest)
            warnings.extend(naming_warnings)
            if naming_warnings:
                score -= 0.05 * len(naming_warnings)

            score = max(0.0, min(1.0, score))

            return {
                "passed": len(errors) == 0 and score >= 0.5,
                "errors": errors,
                "warnings": warnings,
                "score": round(score, 2),
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _validate_manifest_schema(
        self, manifest: dict[str, Any]
    ) -> list[str]:
        """Validate manifest schema fields."""
        errors = []

        for field in REQUIRED_MANIFEST_FIELDS:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")

        if "name" in manifest:
            name = manifest["name"]
            if not isinstance(name, str) or len(name) < 3:
                errors.append("Name must be a string with at least 3 characters")

        if "version" in manifest:
            version = manifest["version"]
            if not isinstance(version, str):
                errors.append("Version must be a string")
            elif not re.match(r"^\d+\.\d+\.\d+", version):
                errors.append("Version should follow semantic versioning (e.g., 1.0.0)")

        if "description" in manifest:
            desc = manifest["description"]
            if not isinstance(desc, str) or len(desc) < 10:
                errors.append("Description must be at least 10 characters")

        return errors

    def _validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate template configuration."""
        errors = []

        if not isinstance(config, dict):
            errors.append("Config must be a dictionary")
            return errors

        if "timeout" in config:
            timeout = config["timeout"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                errors.append("Timeout must be a positive number")

        if "max_retries" in config:
            retries = config["max_retries"]
            if not isinstance(retries, int) or retries < 0:
                errors.append("Max retries must be a non-negative integer")

        return errors

    def _scan_dangerous_patterns(
        self, manifest: dict[str, Any], config: dict[str, Any]
    ) -> list[str]:
        """Scan for dangerous code patterns."""
        warnings = []
        content = str(manifest) + str(config)

        for pattern, message in self._scan_patterns:
            if re.search(pattern, content):
                warnings.append(message)

        return warnings

    def _check_dependencies(self, manifest: dict[str, Any]) -> list[str]:
        """Check template dependencies."""
        warnings = []
        deps = manifest.get("dependencies", [])

        if not isinstance(deps, list):
            warnings.append("Dependencies should be a list")
            return warnings

        for dep in deps:
            if not isinstance(dep, str):
                warnings.append(f"Dependency must be a string: {dep}")
            elif len(dep) == 0:
                warnings.append("Empty dependency string found")

        return warnings

    def _check_naming_conventions(self, manifest: dict[str, Any]) -> list[str]:
        """Check naming conventions for agents and workflows."""
        warnings = []

        agents = manifest.get("agents", {})
        if isinstance(agents, dict):
            for agent_name in agents:
                if not re.match(r"^[a-z][a-z0-9_]*$", agent_name):
                    warnings.append(
                        f"Agent name '{agent_name}' should use snake_case"
                    )

        workflows = manifest.get("workflows", {})
        if isinstance(workflows, dict):
            for wf_name in workflows:
                if not re.match(r"^[a-z][a-z0-9_]*$", wf_name):
                    warnings.append(
                        f"Workflow name '{wf_name}' should use snake_case"
                    )

        return warnings
