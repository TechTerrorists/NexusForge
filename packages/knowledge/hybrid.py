from __future__ import annotations

from typing import Any

from .graph_rag import GraphRAG
from .vector_store import VectorStore


class HybridRetriever:
    """Combines vector similarity search with graph-based retrieval using weighted scoring."""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_rag: GraphRAG,
        alpha: float = 0.5,
    ):
        self.vector_store = vector_store
        self.graph_rag = graph_rag
        self.alpha = max(0.0, min(1.0, alpha))

    def _normalize_scores(self, results: list[dict], score_key: str) -> list[dict]:
        """Normalize scores to [0, 1] range using min-max normalization."""
        if not results:
            return results
        scores = [r.get(score_key, 0) for r in results]
        min_score = min(scores)
        max_score = max(scores)
        range_score = max_score - min_score
        if range_score == 0:
            for r in results:
                r[f"normalized_{score_key}"] = 1.0
        else:
            for r in results:
                raw = r.get(score_key, 0)
                r[f"normalized_{score_key}"] = (raw - min_score) / range_score
        return results

    def query(
        self,
        kb_id: str,
        query_text: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        """Execute a hybrid query combining vector and graph results."""
        vector_results = self.vector_store.query(
            kb_id=kb_id,
            query_text=query_text,
            top_k=top_k * 2,
            filters=filters,
        )
        vector_results = self._normalize_scores(vector_results, "similarity")

        graph_results = self.graph_rag.query(
            kb_id=kb_id,
            query=query_text,
            top_k=top_k * 2,
        )

        combined: dict[str, dict] = {}

        for vr in vector_results:
            doc_id = vr.get("doc_id", vr.get("chunk_id", ""))
            content = vr.get("content", "")
            score = vr.get("normalized_similarity", vr.get("similarity", 0)) * self.alpha
            key = f"vector:{doc_id}:{content[:50]}"
            combined[key] = {
                "source": "vector",
                "doc_id": doc_id,
                "content": content,
                "metadata": vr.get("metadata", {}),
                "score": score,
                "chunk_index": vr.get("chunk_index"),
                "original_similarity": vr.get("similarity"),
            }

        graph_weight = 1.0 - self.alpha
        for gr in graph_results:
            gr_id = gr.get("id", "")
            gr_type = gr.get("type", "entity")
            if gr_type == "entity":
                name = gr.get("name", "")
                score = graph_weight * 0.8
                key = f"graph:entity:{gr_id}"
                combined[key] = {
                    "source": "graph",
                    "type": "entity",
                    "id": gr_id,
                    "entity_type": gr.get("entity_type", ""),
                    "name": name,
                    "properties": gr.get("properties", {}),
                    "score": score,
                    "content": f"{gr.get('entity_type', '')}: {name}",
                }
            elif gr_type == "relation":
                source_name = gr.get("source", {}).get("name", "")
                target_name = gr.get("target", {}).get("name", "")
                rel_type = gr.get("relation_type", "")
                weight = gr.get("weight", 1.0)
                score = graph_weight * min(weight, 1.0)
                key = f"graph:relation:{gr_id}"
                combined[key] = {
                    "source": "graph",
                    "type": "relation",
                    "id": gr_id,
                    "relation_type": rel_type,
                    "source_entity": gr.get("source", {}),
                    "target_entity": gr.get("target", {}),
                    "properties": gr.get("properties", {}),
                    "score": score,
                    "content": f"{source_name} --[{rel_type}]--> {target_name}",
                }

        sorted_results = sorted(combined.values(), key=lambda x: x.get("score", 0), reverse=True)
        return sorted_results[:top_k]

    def set_alpha(self, alpha: float) -> None:
        """Adjust the vector vs. graph weighting."""
        self.alpha = max(0.0, min(1.0, alpha))
