from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class GraphRAG:
    """Graph-based Retrieval-Augmented Generation using Apache AGE or pure SQL."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create graph tables for entity-relation storage."""
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS graph_entities (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                properties JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS graph_relations (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                source_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL,
                properties JSONB DEFAULT '{}',
                weight FLOAT DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_graph_entities_kb ON graph_entities(kb_id)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_graph_entities_type ON graph_entities(entity_type)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_graph_entities_name ON graph_entities(name)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_graph_relations_kb ON graph_relations(kb_id)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_graph_relations_source ON graph_relations(source_id)
        """))
        self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_graph_relations_target ON graph_relations(target_id)
        """))
        self.db.commit()

    def add_entity(
        self,
        kb_id: str,
        entity_type: str,
        name: str,
        properties: dict | None = None,
    ) -> str:
        """Add an entity to the knowledge graph."""
        entity_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute(
            text("""
                INSERT INTO graph_entities (id, kb_id, entity_type, name, properties, created_at, updated_at)
                VALUES (:id, :kb_id, :entity_type, :name, :properties, :created_at, :updated_at)
            """),
            {
                "id": entity_id,
                "kb_id": kb_id,
                "entity_type": entity_type,
                "name": name,
                "properties": json.dumps(properties or {}),
                "created_at": now,
                "updated_at": now,
            },
        )
        self.db.commit()
        return entity_id

    def add_relation(
        self,
        kb_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: dict | None = None,
        weight: float = 1.0,
    ) -> str:
        """Add a relation between two entities."""
        relation_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute(
            text("""
                INSERT INTO graph_relations (id, kb_id, source_id, target_id, relation_type, properties, weight, created_at)
                VALUES (:id, :kb_id, :source_id, :target_id, :relation_type, :properties, :weight, :created_at)
            """),
            {
                "id": relation_id,
                "kb_id": kb_id,
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "properties": json.dumps(properties or {}),
                "weight": weight,
                "created_at": now,
            },
        )
        self.db.commit()
        return relation_id

    def query(self, kb_id: str, query: str, top_k: int = 10) -> list[dict]:
        """Query the graph for entities matching the query string and their relations."""
        results: list[dict] = []

        entity_rows = self.db.execute(
            text("""
                SELECT id, entity_type, name, properties, created_at
                FROM graph_entities
                WHERE kb_id = :kb_id AND (
                    name ILIKE :pattern
                    OR properties::text ILIKE :pattern
                    OR entity_type ILIKE :pattern
                )
                ORDER BY created_at DESC
                LIMIT :top_k
            """),
            {"kb_id": kb_id, "pattern": f"%{query}%", "top_k": top_k},
        ).fetchall()

        for row in entity_rows:
            entity = {
                "id": row[0],
                "type": "entity",
                "entity_type": row[1],
                "name": row[2],
                "properties": json.loads(row[3]) if row[3] else {},
                "created_at": row[4],
            }
            results.append(entity)

        if len(results) < top_k:
            remaining = top_k - len(results)
            relation_rows = self.db.execute(
                text("""
                    SELECT r.id, r.relation_type, r.properties, r.weight,
                           s.id, s.entity_type, s.name, s.properties,
                           t.id, t.entity_type, t.name, t.properties
                    FROM graph_relations r
                    JOIN graph_entities s ON r.source_id = s.id
                    JOIN graph_entities t ON r.target_id = t.id
                    WHERE r.kb_id = :kb_id AND (
                        r.relation_type ILIKE :pattern
                        OR s.name ILIKE :pattern
                        OR t.name ILIKE :pattern
                    )
                    ORDER BY r.weight DESC
                    LIMIT :top_k
                """),
                {"kb_id": kb_id, "pattern": f"%{query}%", "top_k": remaining},
            ).fetchall()

            for row in relation_rows:
                results.append({
                    "id": row[0],
                    "type": "relation",
                    "relation_type": row[1],
                    "properties": json.loads(row[2]) if row[2] else {},
                    "weight": float(row[3]),
                    "source": {
                        "id": row[4],
                        "entity_type": row[5],
                        "name": row[6],
                        "properties": json.loads(row[7]) if row[7] else {},
                    },
                    "target": {
                        "id": row[8],
                        "entity_type": row[9],
                        "name": row[10],
                        "properties": json.loads(row[11]) if row[11] else {},
                    },
                })

        return results[:top_k]

    def get_neighbors(
        self, kb_id: str, entity_id: str, hops: int = 1
    ) -> dict[str, Any]:
        """Traverse the graph from an entity with neighbor hop traversal."""
        visited_entities: set[str] = set()
        all_entities: list[dict] = []
        all_relations: list[dict] = []
        frontier = [entity_id]

        for _ in range(hops):
            if not frontier:
                break
            placeholders = ", ".join(f":eid_{i}" for i in range(len(frontier)))
            params = {f"eid_{i}": eid for i, eid in enumerate(frontier)}
            params["kb_id"] = kb_id

            entity_rows = self.db.execute(
                text(f"""
                    SELECT id, entity_type, name, properties, created_at
                    FROM graph_entities
                    WHERE id IN ({placeholders}) AND kb_id = :kb_id
                """),
                params,
            ).fetchall()

            for row in entity_rows:
                if row[0] not in visited_entities:
                    visited_entities.add(row[0])
                    all_entities.append({
                        "id": row[0],
                        "entity_type": row[1],
                        "name": row[2],
                        "properties": json.loads(row[3]) if row[3] else {},
                        "created_at": row[4],
                    })

            relation_rows = self.db.execute(
                text(f"""
                    SELECT r.id, r.source_id, r.target_id, r.relation_type, r.properties, r.weight,
                           s.name AS source_name, t.name AS target_name
                    FROM graph_relations r
                    JOIN graph_entities s ON r.source_id = s.id
                    JOIN graph_entities t ON r.target_id = t.id
                    WHERE (r.source_id IN ({placeholders}) OR r.target_id IN ({placeholders}))
                    AND r.kb_id = :kb_id
                """),
                {**params, **{f"eid_{i + len(frontier)}": eid for i, eid in enumerate(frontier)}},
            ).fetchall()

            next_frontier = []
            for row in relation_rows:
                all_relations.append({
                    "id": row[0],
                    "source_id": row[1],
                    "target_id": row[2],
                    "relation_type": row[3],
                    "properties": json.loads(row[4]) if row[4] else {},
                    "weight": float(row[5]),
                    "source_name": row[6],
                    "target_name": row[7],
                })
                if row[1] not in visited_entities:
                    next_frontier.append(row[1])
                if row[2] not in visited_entities:
                    next_frontier.append(row[2])

            frontier = list(set(next_frontier) - visited_entities)

        return {
            "center_entity": entity_id,
            "hops": hops,
            "entities": all_entities,
            "relations": all_relations,
        }

    def delete_entity(self, kb_id: str, entity_id: str) -> None:
        """Delete an entity and all its relations."""
        self.db.execute(
            text("DELETE FROM graph_relations WHERE source_id = :eid OR target_id = :eid"),
            {"eid": entity_id},
        )
        self.db.execute(
            text("DELETE FROM graph_entities WHERE id = :eid AND kb_id = :kb_id"),
            {"eid": entity_id, "kb_id": kb_id},
        )
        self.db.commit()

    def get_entity(self, entity_id: str) -> dict | None:
        """Get a single entity by ID."""
        row = self.db.execute(
            text("SELECT id, kb_id, entity_type, name, properties, created_at FROM graph_entities WHERE id = :eid"),
            {"eid": entity_id},
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "kb_id": row[1],
            "entity_type": row[2],
            "name": row[3],
            "properties": json.loads(row[4]) if row[4] else {},
            "created_at": row[5],
        }
