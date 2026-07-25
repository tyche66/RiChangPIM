from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.knowledge.permission_pool import PermissionPool


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(self, query: str, *, product_id: str | None, pool: PermissionPool, trace_id: str) -> list[dict]: ...
