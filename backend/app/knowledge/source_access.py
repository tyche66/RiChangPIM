from __future__ import annotations

from app.models.knowledge import KnowledgeDocument


def can_access_document(document: KnowledgeDocument, current_user: dict) -> bool:
    if current_user.get("role_code") == "admin":
        return True
    if not document.is_active or document.is_deleted:
        return False
    perms = set(current_user.get("perms") or [])
    if document.visibility == "private":
        return False
    if document.required_permission and document.required_permission not in perms:
        return False
    return True
