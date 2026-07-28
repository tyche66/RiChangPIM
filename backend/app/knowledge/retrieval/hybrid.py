from __future__ import annotations

from datetime import UTC, datetime

from app.knowledge.errors import KnowledgeGatewayError
from app.knowledge.retrieval.dedup import keep_top_chunks_per_document
from app.knowledge.retrieval.exact import exact_search
from app.knowledge.retrieval.keyword import keyword_search
from app.knowledge.retrieval.rrf import reciprocal_rank_fusion
from app.knowledge.retrieval.vector import vector_search
from app.knowledge.schemas import Source


class HybridRetriever:
    def __init__(self, adapter, db) -> None:
        self.adapter = adapter
        self.db = db

    async def retrieve(
        self,
        query: str,
        *,
        product_id: str | None,
        pool,
        current_user: dict,
        trace_id: str,
    ) -> tuple[list[dict], list[dict]]:
        exact_rows = await exact_search(
            self.db,
            query=query,
            product_id=product_id,
            current_user=current_user,
            limit=8,
        )
        keyword_rows = await keyword_search(
            self.db,
            query=query,
            product_id=product_id,
            current_user=current_user,
            limit=12,
        )
        events = [
            {"event": "retrieval", "channel": "exact", "candidates": len(exact_rows)},
            {"event": "retrieval", "channel": "keyword", "candidates": len(keyword_rows)},
        ]
        vector_rows: list[dict] = []
        try:
            vector_rows = await vector_search(
                self.db,
                adapter=self.adapter,
                query=query,
                product_id=product_id,
                current_user=current_user,
                limit=12,
            )
        except KnowledgeGatewayError as exc:
            events.append(
                {
                    "event": "retrieval",
                    "channel": "vector",
                    "status": "degraded",
                    "reason": exc.code.value,
                }
            )
        else:
            events.append(
                {"event": "retrieval", "channel": "vector", "candidates": len(vector_rows)}
            )

        for row in exact_rows:
            row["priority_boost"] = 10.0
        fused = reciprocal_rank_fusion(
            {
                "exact": exact_rows,
                "keyword": keyword_rows,
                "vector": vector_rows,
            }
        )
        fused.sort(
            key=lambda item: (item.get("priority_boost", 0.0), item.get("rrf_score", 0.0)),
            reverse=True,
        )
        fused = keep_top_chunks_per_document(fused, limit_per_document=3)
        return [self._to_source(row, pool) for row in fused[:10]], events

    def _to_source(self, row: dict, pool) -> dict:
        quote = row.get("quote") or ""
        if "supplier_name" in pool.hidden_fields:
            quote = None
        chunk_id = str(row.get("chunk_id"))
        document_id = str(row.get("document_id"))
        score = row.get("score") or row.get("rrf_score")
        source = Source(
            source_id=f"chunk:{chunk_id}",
            source_type="document",
            title=str(row.get("title") or "知识文档"),
            product_id=str(row.get("product_id")) if row.get("product_id") else None,
            document_id=document_id,
            chunk_id=chunk_id,
            page=row.get("page"),
            section=row.get("section"),
            quote=quote[:500] if quote else None,
            observed_at=datetime.now(UTC),
            access_policy="role_projected",
            score=round(float(score), 4) if score is not None else None,
            channel=",".join(row.get("channels") or []),
            open_url=f"/api/v1/knowledge/sources/chunk:{chunk_id}",
        )
        return source.model_dump(mode="json")
