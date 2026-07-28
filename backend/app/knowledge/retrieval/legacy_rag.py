from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.adapters.base import AIServiceAdapter
from app.adapters.none import NoneAdapter
from app.knowledge.permission_pool import PermissionPool
from app.knowledge.schemas import Source
from app.services.rag_index import RagSearcher

DYNAMIC_TERMS = ("价格", "面价", "成本", "库存", "供应商", "上下架", "报价", "方案状态")


class LegacyRagRetriever:
    def __init__(self, adapter: AIServiceAdapter, db) -> None:
        self.adapter = adapter
        self.db = db

    async def retrieve(
        self,
        query: str,
        *,
        product_id: str | None,
        pool: PermissionPool,
        current_user: dict,
        trace_id: str,
    ) -> tuple[list[dict], list[dict]]:
        if isinstance(self.adapter, NoneAdapter):
            return [], []
        if any(term in query for term in DYNAMIC_TERMS):
            return [], []
        pid = UUID(product_id) if product_id else None
        searcher = RagSearcher(self.adapter, self.db)
        try:
            rows = await searcher.search(query, product_id=pid)
        except Exception:
            return [], []
        sources: list[dict] = []
        for row in rows:
            quote = row.get("chunk_text") or ""
            if "supplier_name" in pool.hidden_fields:
                quote = None
            sources.append(
                Source(
                    source_id=f"doc_chunk_{row.get('chunk_id')}",
                    source_type="document",
                    title=f"产品资料片段 {row.get('chunk_index')}",
                    product_id=row.get("product_id"),
                    section=str(row.get("chunk_index")),
                    quote=quote[:500] if quote else None,
                    observed_at=datetime.now(UTC),
                    access_policy="role_projected",
                ).model_dump(mode="json")
            )
        return sources, []
