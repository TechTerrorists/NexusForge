from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from ..models import User
from ..auth.dependencies import get_current_active_user

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class StoreRequest(BaseModel):
    namespace: str
    key: str
    value: str
    metadata: dict = {}


class QueryRequest(BaseModel):
    namespace: str
    query: str
    top_k: int = 5


@router.post("/store")
async def store_memory(
    req: StoreRequest, user: User = Depends(get_current_active_user),
):
    return {"status": "stored", "namespace": req.namespace, "key": req.key}


@router.post("/query")
async def query_memory(
    req: QueryRequest, user: User = Depends(get_current_active_user),
):
    return {"results": [], "query": req.query}


@router.delete("/store/{namespace}/{key}")
async def delete_memory(
    namespace: str, key: str, user: User = Depends(get_current_active_user),
):
    return {"status": "deleted", "namespace": namespace, "key": key}


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_active_user)):
    return {"sessions": []}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: User = Depends(get_current_active_user)):
    return {"session_id": session_id, "messages": []}
