import logging
from typing import Any

logger = logging.getLogger(__name__)


class TemplateInstaller:
    def __init__(self, registry, db_session=None):
        self._registry = registry
        self._db_session = db_session
        self._installations: dict[str, dict[str, Any]] = {}

    async def install(
        self, template_id: str, tenant_id: str
    ) -> dict[str, Any]:
        """Install a template for a tenant."""
        template = self._registry.get(template_id)
        if not template:
            return {
                "success": False,
                "error": f"Template {template_id} not found",
            }

        install_key = f"{template_id}:{tenant_id}"
        if install_key in self._installations:
            return {
                "success": False,
                "error": "Template already installed for this tenant",
            }

        deps = template.get("dependencies", [])
        missing_deps = []
        for dep in deps:
            if not self._registry.get(dep):
                missing_deps.append(dep)

        if missing_deps:
            return {
                "success": False,
                "error": f"Missing dependencies: {', '.join(missing_deps)}",
            }

        agents = {}
        for agent_name, agent_config in template.get("agents", {}).items():
            agent_id = f"{template_id}_{agent_name}_{tenant_id}"
            agents[agent_name] = {
                "id": agent_id,
                "config": agent_config,
                "status": "created",
            }
            logger.info(f"Created agent: {agent_id}")

        workflows = {}
        for wf_name, wf_config in template.get("workflows", {}).items():
            wf_id = f"{template_id}_{wf_name}_{tenant_id}"
            workflows[wf_name] = {
                "id": wf_id,
                "config": wf_config,
                "status": "created",
            }
            logger.info(f"Created workflow: {wf_id}")

        installation = {
            "template_id": template_id,
            "tenant_id": tenant_id,
            "agents": agents,
            "workflows": workflows,
            "status": "installed",
        }
        self._installations[install_key] = installation

        if self._db_session:
            try:
                await self._persist_installation(installation)
            except Exception as e:
                logger.error(f"Failed to persist installation: {e}")

        return {"success": True, "installation": installation}

    async def uninstall(
        self, template_id: str, tenant_id: str
    ) -> dict[str, Any]:
        """Uninstall a template for a tenant."""
        install_key = f"{template_id}:{tenant_id}"
        if install_key not in self._installations:
            return {
                "success": False,
                "error": "Installation not found",
            }

        installation = self._installations.pop(install_key)
        installation["status"] = "uninstalled"

        for agent_name, agent in installation["agents"].items():
            logger.info(f"Removed agent: {agent['id']}")

        for wf_name, wf in installation["workflows"].items():
            logger.info(f"Removed workflow: {wf['id']}")

        return {"success": True, "uninstalled": installation}

    async def update(
        self, template_id: str, tenant_id: str
    ) -> dict[str, Any]:
        """Update an installed template to the latest version."""
        install_key = f"{template_id}:{tenant_id}"
        if install_key not in self._installations:
            return {
                "success": False,
                "error": "Installation not found",
            }

        template = self._registry.get(template_id)
        if not template:
            return {
                "success": False,
                "error": f"Template {template_id} not found in registry",
            }

        old_installation = self._installations[install_key]
        uninstall_result = await self.uninstall(template_id, tenant_id)
        if not uninstall_result["success"]:
            return uninstall_result

        install_result = await self.install(template_id, tenant_id)
        if install_result["success"]:
            install_result["installation"]["previous_agents"] = old_installation["agents"]
            install_result["installation"]["previous_workflows"] = old_installation["workflows"]
            install_result["updated_from"] = old_installation["status"]

        return install_result

    async def _persist_installation(
        self, installation: dict[str, Any]
    ) -> None:
        """Persist installation to database."""
        if not self._db_session:
            return

        await self._db_session.execute(
            """
            INSERT INTO template_installations
            (template_id, tenant_id, agents, workflows, status)
            VALUES (:template_id, :tenant_id, :agents, :workflows, :status)
            """,
            {
                "template_id": installation["template_id"],
                "tenant_id": installation["tenant_id"],
                "agents": str(installation["agents"]),
                "workflows": str(installation["workflows"]),
                "status": installation["status"],
            },
        )
        await self._db_session.commit()

    def get_installation(
        self, template_id: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Get an installation by template and tenant."""
        install_key = f"{template_id}:{tenant_id}"
        return self._installations.get(install_key)

    def list_installations(
        self, tenant_id: str = None
    ) -> list[dict[str, Any]]:
        """List all installations, optionally filtered by tenant."""
        results = list(self._installations.values())
        if tenant_id:
            results = [i for i in results if i["tenant_id"] == tenant_id]
        return results
