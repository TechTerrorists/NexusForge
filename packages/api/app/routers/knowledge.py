from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime

from ..database import get_db
from ..models import KnowledgeBase, User
from ..auth.dependencies import get_current_active_user, require_role

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class KBCreate(BaseModel):
    name: str
    embedding_model: str = "text-embedding-3-small"
    chunk_config: dict = {"chunk_size": 512, "overlap": 50}


class KBResponse(BaseModel):
    id: str
    name: str
    embedding_model: str
    chunk_config: dict
    created_at: str


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
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    kb = KnowledgeBase(
        id=uuid4(), name=req.name, embedding_model=req.embedding_model,
        chunk_config=req.chunk_config, tenant_id=user.tenant_id,
        created_at=datetime.utcnow(),
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return KBResponse(
        id=str(kb.id), name=kb.name, embedding_model=kb.embedding_model,
        chunk_config=kb.chunk_config, created_at=kb.created_at.isoformat(),
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
            id=str(k.id), name=k.name, embedding_model=k.embedding_model,
            chunk_config=k.chunk_config, created_at=k.created_at.isoformat(),
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
        id=str(kb.id), name=kb.name, embedding_model=kb.embedding_model,
        chunk_config=kb.chunk_config, created_at=kb.created_at.isoformat(),
    )


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager")),
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
    from packages.knowledge.vector_store import VectorStore
    vs = VectorStore(db)
    results = await vs.query(kb_id, req.query, top_k=req.top_k, filters=req.filters)
    return [QueryResult(content=r["content"], score=r["score"], metadata=r.get("metadata", {})) for r in results]


@router.post("/{kb_id}/documents", status_code=201)
async def add_document(
    kb_id: str, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "manager", "developer")),
):
    content = await file.read()
    from packages.knowledge.file_understanding import FileUnderstanding
    fu = FileUnderstanding()
    text = content.decode("utf-8", errors="replace")
    chunks = fu.chunk_text(text)
    from packages.knowledge.vector_store import VectorStore
    vs = VectorStore(db)
    doc_ids = []
    for i, chunk in enumerate(chunks):
        doc_id = await vs.add_document(kb_id, chunk, metadata={"source": file.filename, "chunk": i})
        doc_ids.append(doc_id)
    return {"document_ids": doc_ids, "chunks": len(chunks)}
