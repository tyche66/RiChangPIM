from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class ConversationStore(Protocol):
    async def create_session(self, metadata: dict[str, Any]) -> str: ...
    async def append_turn(self, session_id: str, request_digest: dict[str, Any], response_digest: dict[str, Any], trace: dict[str, Any]) -> str: ...
    async def load_context(self, session_id: str, policy: Any) -> list[dict[str, str]]: ...
    async def list_sessions(self, user_id: UUID, cursor: str | None = None) -> list[dict[str, Any]]: ...
    async def delete_session(self, user_id: UUID, session_id: str) -> None: ...


def digest_text(text: str) -> dict[str, Any]:
    return {"length": len(text or ""), "sha256": hashlib.sha256((text or "").encode("utf-8")).hexdigest()}


class DigestConversationStore:
    def __init__(self, db: AsyncSession, user_id: UUID | None) -> None:
        self.db = db
        self.user_id = user_id

    async def create_session(self, metadata: dict[str, Any]) -> str:
        return str(uuid4())

    async def append_turn(self, session_id: str, request_digest: dict[str, Any], response_digest: dict[str, Any], trace: dict[str, Any]) -> str:
        from app.models.audit import AIConversation

        turn_id = str(uuid4())
        conv = AIConversation(
            session_id=session_id,
            user_id=self.user_id,
            question=f"length={request_digest.get('length', 0)} sha256={request_digest.get('sha256', '')}",
            answer=f"length={response_digest.get('length', 0)} sha256={response_digest.get('sha256', '')}",
            sources=json.dumps(trace.get("source_ids") or [], ensure_ascii=False),
            tool_calls=json.dumps(trace.get("tool_names") or [], ensure_ascii=False),
        )
        mapper = sa_inspect(AIConversation)
        col_names = {c.key for c in mapper.columns}
        if "model" in col_names:
            conv.model = trace.get("model")
        if "token_usage" in col_names:
            conv.token_usage = json.dumps(trace.get("usage") or {}, ensure_ascii=False)
        if "status" in col_names:
            conv.status = trace.get("status") or "completed"
        if "request_summary" in col_names:
            conv.request_summary = conv.question
        if "response_summary" in col_names:
            conv.response_summary = conv.answer
        self.db.add(conv)
        await self.db.commit()
        return turn_id

    async def load_context(self, session_id: str, policy: Any) -> list[dict[str, str]]:
        return []

    async def list_sessions(self, user_id: UUID, cursor: str | None = None) -> list[dict[str, Any]]:
        from app.models.audit import AIConversation

        if self.user_id != user_id:
            return []
        result = await self.db.execute(
            select(AIConversation.session_id, AIConversation.create_time)
            .where(AIConversation.user_id == user_id)
            .order_by(AIConversation.create_time.desc())
            .limit(50)
        )
        return [{"session_id": sid, "create_time": created} for sid, created in result.all()]

    async def delete_session(self, user_id: UUID, session_id: str) -> None:
        return None
