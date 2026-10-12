"""项目阶段状态机（HLD §5.2）。

纯函数 + 字典表，tests/unit 可直接导入。

规则：
- lead → measuring → design → quoted → producing → delivered → closed
- 允许跳跃前进（如 lead → design）
- 允许回退一格（必须带 reason）
- closed/cancelled 不可迁出（admin 可强制，记日志）
- 任意非终态 → cancelled（带 reason，同时 status=cancelled）
- delivered/closed 自动 status=done
"""

from __future__ import annotations

__all__ = [
    "STAGES",
    "TERMINAL_STAGES",
    "can_transition",
    "validate_transition",
    "auto_update_status",
]

STAGES = ["lead", "measuring", "design", "quoted", "producing", "delivered", "closed"]

TERMINAL_STAGES = frozenset({"closed", "cancelled"})

# 回退映射：每个阶段可以回退到哪个阶段（1-step backward）
_BACKWARD_MAP: dict[str, str] = {
    "measuring": "lead",
    "design": "measuring",
    "quoted": "design",
    "producing": "quoted",
    "delivered": "producing",
    "closed": "delivered",
}


def can_transition(from_stage: str, to_stage: str) -> bool:
    """判断阶段迁移是否结构上可行。

    规则：
    - 同阶段：True（no-op）
    - 前进（含跳跃）：True
    - 回退一格：True（需 reason，由 validate_transition 检查）
    - 回退多格：False
    - 从终态（closed/cancelled）迁出：False
    - 任意非终态 → cancelled：True（需 reason）
    """
    if from_stage == to_stage:
        return True
    if from_stage in TERMINAL_STAGES:
        return False
    if to_stage == "cancelled":
        return True
    if to_stage not in STAGES:
        return False
    from_idx = STAGES.index(from_stage)
    to_idx = STAGES.index(to_stage)
    if to_idx > from_idx:
        return True  # 前进/跳跃
    if to_idx == from_idx - 1:
        return True  # 回退一格
    return False  # 回退多格


def validate_transition(from_stage: str, to_stage: str, reason: str | None = None) -> dict | None:
    """校验阶段迁移，返回错误 dict 或 None（合法）。

    错误码：
    - 40010: 非法状态迁移
    - 40011: 回退缺 reason
    """
    if from_stage == to_stage:
        return None
    if from_stage in TERMINAL_STAGES:
        return {"code": 40010, "msg": f"终态 {from_stage} 不可迁出"}
    if to_stage == "cancelled":
        if not reason:
            return {"code": 40011, "msg": "取消项目必须提供原因"}
        return None
    if to_stage not in STAGES:
        return {"code": 40010, "msg": f"未知阶段: {to_stage}"}
    from_idx = STAGES.index(from_stage)
    to_idx = STAGES.index(to_stage)
    if to_idx > from_idx:
        return None  # 前进/跳跃
    if to_idx == from_idx - 1:
        if not reason:
            return {"code": 40011, "msg": "回退阶段必须提供原因"}
        return None
    return {"code": 40010, "msg": "不允许回退多个阶段"}


def auto_update_status(stage: str) -> str:
    """根据阶段自动更新项目状态。

    delivered/closed → done
    其余 → active
    """
    if stage in ("delivered", "closed"):
        return "done"
    return "active"
