from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session


class DocumentChunk:
    """Represents a chunk of a document with embedding."""
    def __init__(self, chunk_id: str, doc_id: str, content: str, embedding: list[float], metadata: dict):
        self.chunk_id = chunk_id
        self.doc_id = doc_id
        self.content = content
        self.embedding = embedding
        self.metadata = metadata


class VectorStore:
    """Vector store using pgvector for similarity search with chunking support."""

    def __init__(self, db_session: Session, embedding_model: str = "text-embedding-3-small"):
        self.db = db_session
        self.embedding_model = embedding_model
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create vector tables if they don't exist."""
        from sqlalchemy import text
        self.db.execute(text("""
            CREATE EXTENSION IF NOT EXISTS vector
        """))
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS vector_documents (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS vector_chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL REFERENCES vector_documents(id) ON DELETE CASCADE,
                kb_id TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector(1536),
                metadata JSONB DEFAULT '{}',
                chunk_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_vector_chunks_kb ON vector_chunks(kb_id)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_vector_chunks_embedding ON vector_chunks 
            USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
        """))
        self.db.commit()

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks."""
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        return chunks

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        try:
            import openai
            client = openai.AsyncOpenAI()
            response = await client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception:
            return [[0.0] * 1536 for _ in texts]

    def add_document(self, kb_id: str, content: str, metadata: dict | None = None) -> str:
        """Add a document to the vector store, chunking and embedding it."""
        import asyncio
        from sqlalchemy import text

        doc_id = str(uuid.uuid4())
        metadata = metadata or {}
        now = time.time()

        self.db.execute(
            text("""
                INSERT INTO vector_documents (id, kb_id, content, metadata, created_at)
                VALUES (:id, :kb_id, :content, :metadata, :created_at)
            """),
            {
                "id": doc_id,
                "kb_id": kb_id,
                "content": content,
                "metadata": json.dumps(metadata),
                "created_at": now,
            },
        )

        chunks = self._chunk_text(content)
        if not chunks:
            self.db.commit()
            return doc_id

        embeddings = asyncio.get_event_loop().run_until_complete(self._embed(chunks))

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = hashlib.sha256(f"{doc_id}:{i}:{chunk[:100]}".encode()).hexdigest()[:32]
            chunk_meta = {**metadata, "chunk_index": i, "doc_id": doc_id}
            self.db.execute(
                text("""
                    INSERT INTO vector_chunks (id, doc_id, kb_id, content, embedding, metadata, chunk_index, created_at)
                    VALUES (:id, :doc_id, :kb_id, :content, :embedding, :metadata, :chunk_index, :created_at)
                """),
                {
                    "id": chunk_id,
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "content": chunk,
                    "embedding": str(embedding),
                    "metadata": json.dumps(chunk_meta),
                    "chunk_index": i,
                    "created_at": now,
                },
            )

        self.db.commit()
        return doc_id

    def query(
        self,
        kb_id: str,
        query_text: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        """Query the vector store using cosine similarity."""
        import asyncio
        from sqlalchemy import text

        query_embedding = asyncio.get_event_loop().run_until_complete(
            self._embed([query_text])
        )[0]

        filter_clause = ""
        params: dict[str, Any] = {
            "kb_id": kb_id,
            "embedding": str(query_embedding),
            "top_k": top_k,
        }

        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(f"metadata->>'{key}' = :filter_{key}")
                params[f"filter_{key}"] = value
            if conditions:
                filter_clause = "AND " + " AND ".join(conditions)

        query_sql = text(f"""
            SELECT id, doc_id, content, metadata, chunk_index,
                   1 - (embedding <=> :embedding::vector) AS similarity
            FROM vector_chunks
            WHERE kb_id = :kb_id {filter_clause}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        results = self.db.execute(query_sql, params).fetchall()
        return [
            {
                "chunk_id": row[0],
                "doc_id": row[1],
                "content": row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
                "chunk_index": row[4],
                "similarity": float(row[5]),
            }
            for row in results
        ]

    def delete_document(self, kb_id: str, doc_id: str) -> None:
        """Delete a document and all its chunks."""
        from sqlalchemy import text
        self.db.execute(
            text("DELETE FROM vector_chunks WHERE kb_id = :kb_id AND doc_id = :doc_id"),
            {"kb_id": kb_id, "doc_id": doc_id},
        )
        self.db.execute(
            text("DELETE FROM vector_documents WHERE id = :doc_id AND kb_id = :kb_id"),
            {"doc_id": doc_id, "kb_id": kb_id},
        )
        self.db.commit()

    def list_documents(self, kb_id: str) -> list[dict]:
        """List all documents in a knowledge base."""
        from sqlalchemy import text
        results = self.db.execute(
            text("SELECT id, kb_id, content, metadata, created_at FROM vector_documents WHERE kb_id = :kb_id"),
            {"kb_id": kb_id},
        ).fetchall()
        return [
            {
                "id": row[0],
                "kb_id": row[1],
                "content": row[2][:200] + "..." if len(row[2]) > 200 else row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
                "created_at": row[4],
            }
            for row in results
        ]
