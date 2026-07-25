from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.permission_pool import PermissionPool


@dataclass(frozen=True)
class ToolAuthzResult:
    allowed: bool
    reason: str | None = None


@runtime_checkable
class ToolAuthorizationPolicy(Protocol):
    def authorize(self, tool_name: str, pool: PermissionPool, current_user: dict, required_permissions: set[str]) -> ToolAuthzResult: ...


class DefaultToolAuthorizationPolicy:
    def authorize(self, tool_name: str, pool: PermissionPool, current_user: dict, required_permissions: set[str]) -> ToolAuthzResult:
        if tool_name not in pool.allowed_tools:
            return ToolAuthzResult(False, "tool not allowed for permission pool")
        if current_user.get("role_code") == "admin":
            return ToolAuthzResult(True)
        perms = set(current_user.get("perms") or []) | pool.ai_permissions
        missing = required_permissions - perms
        if missing:
            return ToolAuthzResult(False, f"missing permissions: {', '.join(sorted(missing))}")
        return ToolAuthzResult(True)


def require_ai_access(pool: PermissionPool, current_user: dict) -> None:
    if current_user.get("role_code") == "admin":
        return
    perms = set(current_user.get("perms") or []) | pool.ai_permissions
    if not ({"ai:access", "ai:use", "ai:knowledge", "ai:product"} & perms):
        raise KnowledgeGatewayError(
            KnowledgeErrorCode.AUTH_DENIED,
            "无权限访问 Knowledge Gateway",
            status_code=403,
        )


def get_tool_authorization_policy() -> ToolAuthorizationPolicy:
    return DefaultToolAuthorizationPolicy()
