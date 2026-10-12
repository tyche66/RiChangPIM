"""客户状态机纯函数（HLD §5.1）。

TRANSITIONS 定义了允许的阶段迁移路径。
- won 是终态，不可迁出。
- lost → contacted 是 reopen，必须带 reason。
- 回退（backward）迁移必须带 reason。
"""

from __future__ import annotations

TRANSITIONS: dict[str, list[str]] = {
    "lead": ["contacted", "needs", "quoted", "lost"],
    "contacted": ["needs", "quoted", "lost", "lead"],
    "needs": ["quoted", "won", "lost", "contacted", "lead"],
    "quoted": ["won", "lost", "needs", "contacted", "lead"],
    "won": [],
    "lost": ["contacted"],
}

# 回退迁移集合（from_stage, to_stage）对，这些迁移必须带 reason
BACKWARD_TRANSITIONS: set[tuple[str, str]] = {
    ("contacted", "lead"),
    ("needs", "contacted"),
    ("needs", "lead"),
    ("quoted", "needs"),
    ("quoted", "contacted"),
    ("quoted", "lead"),
    ("lost", "contacted"),
}


def can_transition(from_stage: str, to_stage: str) -> bool:
    """检查是否允许从 from_stage 迁移到 to_stage。"""
    return to_stage in TRANSITIONS.get(from_stage, [])


def is_backward(from_stage: str, to_stage: str) -> bool:
    """检查迁移是否为回退（需要 reason）。"""
    return (from_stage, to_stage) in BACKWARD_TRANSITIONS


def validate_transition(from_stage: str, to_stage: str, reason: str | None = None) -> dict:
    """验证阶段迁移是否合法。

    Returns:
        {"ok": True} 或 {"ok": False, "code": int, "msg": str}
    """
    if not can_transition(from_stage, to_stage):
        return {"ok": False, "code": 40010, "msg": f"非法状态迁移: {from_stage} -> {to_stage}"}
    if is_backward(from_stage, to_stage) and not reason:
        return {"ok": False, "code": 40011, "msg": "回退/reopen 操作必须提供 reason"}
    return {"ok": True}
