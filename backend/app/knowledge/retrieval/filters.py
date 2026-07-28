from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


def apply_document_filters(stmt: Select, current_user: dict) -> Select:
    now = datetime.now(UTC)
    stmt = stmt.where(
        KnowledgeDocument.is_deleted.is_(False),
        KnowledgeDocument.is_active.is_(True),
        KnowledgeChunk.is_deleted.is_(False),
    )
    stmt = stmt.where(
        (KnowledgeDocument.effective_at.is_(None)) | (KnowledgeDocument.effective_at <= now)
    )
    stmt = stmt.where(
        (KnowledgeDocument.expired_at.is_(None)) | (KnowledgeDocument.expired_at >= now)
    )
    if current_user.get("role_code") == "admin":
        return stmt
    perms = set(current_user.get("perms") or [])
    stmt = stmt.where(KnowledgeDocument.visibility.in_(("internal", "restricted")))
    if perms:
        stmt = stmt.where(
            (KnowledgeDocument.required_permission.is_(None))
            | (KnowledgeDocument.required_permission.in_(perms))
        )
    else:
        stmt = stmt.where(KnowledgeDocument.required_permission.is_(None))
    return stmt
