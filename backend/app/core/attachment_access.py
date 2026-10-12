"""附件访问闸（HLD §4.8 / V2-01 附件越权修复）。

叶子模块：不 import app.main / database，纯数据判断（可单测）。

调用方（files.py 的 download/preview/content/缩略图路径与媒体库列表）在拿到
attachment 后先过本闸。``user`` 为 request.state 风格对象（role_code /
permissions / user_id），并应携带 ``visible_customer_ids`` /
``visible_project_ids``（由请求期依赖经 core.data_scope 预计算）；
集合未携带时非 admin/manager 一律拒绝（fail-closed，不暴露存在性）。

规则：
- ``biz_domain`` IS NULL 或 ``'product'`` → True（现行文件中心/媒体库行为零变化）。
- ``'content'`` → 有 ``content:view`` 即可。
- ``'customer'`` → ``customer:view`` 且客户在该用户数据范围内。
- ``'project'`` → ``project:view`` 且项目在该用户数据范围内。
- 其余 → False。
"""

from __future__ import annotations

from typing import Any

__all__ = ["can_access_attachment"]

# 数据范围全量角色（与 core.data_scope 一致）
_FULL_SCOPE_ROLES = frozenset({"admin", "manager"})


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """兼容 dict（JWT payload）与对象（request.state / ORM）两种形态。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _has_permission(user: Any, code: str) -> bool:
    """与 core.permission.PermissionChecker 同构：admin 直通，否则查 permissions。

    兼容 request.state.permissions（列表）与 JWT payload 的 perms 键。
    """
    if _get(user, "role_code") == "admin":
        return True
    perms = _get(user, "permissions")
    if perms is None:
        perms = _get(user, "perms")
    if not perms:
        return False
    return code in perms


def _in_scope(user: Any, attr_name: str, obj_id: Any) -> bool:
    """obj_id 是否落在 user 的可见集合（attr_name）内。

    admin/manager 全量放行；集合未加载（None）→ fail-closed 拒绝。
    兼容 UUID / str 混容比较。
    """
    if obj_id is None:
        return False
    if _get(user, "role_code") in _FULL_SCOPE_ROLES:
        return True
    visible = _get(user, attr_name)
    if visible is None:
        return False
    try:
        if obj_id in visible:
            return True
    except TypeError:
        pass
    return str(obj_id) in {str(v) for v in visible}


def can_access_attachment(user: Any, att: Any) -> bool:
    """附件访问判定（HLD §4.8）。

    Args:
        user: request.state 风格对象；admin/manager 数据范围全量。
        att: Attachment ORM 对象或 dict（读 biz_domain / biz_scope_id）。

    Returns:
        是否允许访问该附件。
    """
    domain = _get(att, "biz_domain")
    if domain is None or domain == "product":
        return True
    if domain == "content":
        return _has_permission(user, "content:view")
    if domain == "customer":
        if not _has_permission(user, "customer:view"):
            return False
        return _in_scope(user, "visible_customer_ids", _get(att, "biz_scope_id"))
    if domain == "project":
        if not _has_permission(user, "project:view"):
            return False
        return _in_scope(user, "visible_project_ids", _get(att, "biz_scope_id"))
    return False
