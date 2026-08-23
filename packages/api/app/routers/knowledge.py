from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime

from ..database import get_db
from ..models import KnowledgeBase, User, UserRole
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class KBCreate(BaseModel):
    name: str
    description: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 512
    chunk_overlap: int = 50


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    document_count: int
    total_chunks: int
    created_at: str
    updated_at: str


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict | None = None


class QueryResult(BaseModel):
    content: str
    score: float
    metadata: dict


@router.post("/", response_model=KBResponse, status_code=201)
async def create_knowledge_base(
    req: KBCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    kb = KnowledgeBase(
        id=uuid4(), name=req.name, description=req.description,
        embedding_model=req.embedding_model,
        chunk_size=req.chunk_size, chunk_overlap=req.chunk_overlap,
        tenant_id=user.tenant_id,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return KBResponse(
        id=str(kb.id), name=kb.name, description=kb.description or "",
        embedding_model=kb.embedding_model, chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap, document_count=kb.document_count,
        total_chunks=kb.total_chunks, created_at=kb.created_at.isoformat(),
        updated_at=kb.updated_at.isoformat(),
    )


@router.get("/", response_model=list[KBResponse])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.tenant_id == user.tenant_id)
    )
    kbs = result.scalars().all()
    return [
        KBResponse(
            id=str(k.id), name=k.name, description=k.description or "",
            embedding_model=k.embedding_model, chunk_size=k.chunk_size,
            chunk_overlap=k.chunk_overlap, document_count=k.document_count,
            total_chunks=k.total_chunks, created_at=k.created_at.isoformat(),
            updated_at=k.updated_at.isoformat(),
        )
        for k in kbs
    ]


@router.get("/{kb_id}", response_model=KBResponse)
async def get_knowledge_base(
    kb_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == user.tenant_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return KBResponse(
        id=str(kb.id), name=kb.name, description=kb.description or "",
        embedding_model=kb.embedding_model, chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap, document_count=kb.document_count,
        total_chunks=kb.total_chunks, created_at=kb.created_at.isoformat(),
        updated_at=kb.updated_at.isoformat(),
    )


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.OWNER)),
):
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == user.tenant_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await db.delete(kb)
    await db.commit()


@router.post("/{kb_id}/query", response_model=list[QueryResult])
async def query_knowledge_base(
    kb_id: str, req: QueryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == user.tenant_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return []


@router.post("/{kb_id}/documents", status_code=201)
async def add_document(
    kb_id: str, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER)),
):
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    return {"document_ids": [], "chunks": 0, "status": "uploaded"}
