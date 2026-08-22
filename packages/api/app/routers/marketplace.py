from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from ..models import User
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])


class TemplateInstall(BaseModel):
    template_id: str


@router.get("/templates")
async def list_templates(domain: str | None = None, user: User = Depends(get_current_active_user)):
    return {"templates": [], "domain": domain}


@router.get("/templates/{template_id}")
async def get_template(template_id: str, user: User = Depends(get_current_active_user)):
    return {"template_id": template_id, "name": "", "description": ""}


@router.post("/templates/{template_id}/install")
async def install_template(
    template_id: str,
    user: User = Depends(require_role("admin", "manager")),
):
    return {"status": "installed", "template_id": template_id}


@router.post("/templates/{template_id}/uninstall")
async def uninstall_template(
    template_id: str,
    user: User = Depends(require_role("admin", "manager")),
):
    return {"status": "uninstalled", "template_id": template_id}
