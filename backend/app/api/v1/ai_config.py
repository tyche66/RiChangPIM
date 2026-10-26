"""AI 配置中心 API（v1.9.5）。

* ``GET  /api/v1/ai/config``          —— 两个 scope 的生效配置（密钥只出掩码）；
* ``PUT  /api/v1/ai/config/{scope}``  —— 局部更新并刷新进程缓存；
* ``POST /api/v1/ai/config/{scope}/test`` —— 用当前配置做一次最小连通性探测。

安全边界：
* 仅 ``role_code=admin``（显式校验；PermissionChecker 对 admin 会整体跳过权限码）；
* 响应与审计绝不回显密钥明文；
* 探测只发一次极短 chat 调用（超时 10s、不重试），不回传上游响应体。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.middleware.audit import audit_action
from app.models.ai_config import AiProviderConfig
from app.schemas.ai_config import AiConfigRead, AiConfigTestResult, AiConfigUpdate
from app.services.ai_config import (
    SCOPES,
    config_to_dict,
    load_config,
    mask_key,
    refresh_cache,
)

router = APIRouter(prefix="/api/v1/ai/config", tags=["ai-config"])

_SCOPE_LABELS = dict(SCOPES)


def _envelope(data: Any, code: int = 200) -> dict:
    return {"code": code, "data": data}


def _require_admin(request: Request) -> None:
    """AI 配置中心的显式 admin 校验。

    PermissionChecker 对 ``role_code == "admin"`` 会整体跳过权限码检查，
    因此这里必须单独断言 role_code：非管理员一律 403。
    """
    if getattr(request.state, "role_code", None) != "admin":
        raise HTTPException(
            status_code=403, detail={"code": 40301, "msg": "无权限访问该资源"}
        )


def _require_scope(scope: str) -> None:
    if scope not in _SCOPE_LABELS:
        raise HTTPException(
            status_code=404, detail={"code": 40401, "msg": "未知的 AI 配置域"}
        )


async def _load_row(db: AsyncSession, scope: str) -> AiProviderConfig | None:
    result = await db.execute(
        select(AiProviderConfig).where(
            AiProviderConfig.scope == scope,
            AiProviderConfig.is_deleted.is_(False),
        )
    )
    return result.scalars().first()


@router.get(
    "",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("ai:config"))],
)
async def read_ai_config(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """读取两个 scope 的生效配置（密钥只出掩码）。"""
    _require_admin(request)
    items = []
    for scope, _label in SCOPES:
        config = await load_config(scope, db)
        payload = config_to_dict(config)
        payload["label"] = _SCOPE_LABELS[scope]
        items.append(AiConfigRead(**payload))
    return _envelope({"items": items})


@router.put(
    "/{scope}",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("ai:config"))],
)
@audit_action("ai_config_update", module="ai")
async def update_ai_config(
    scope: str,
    payload: AiConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """局部更新：未出现的字段保持原值，密钥留空即"不改"。"""
    _require_admin(request)
    _require_scope(scope)

    row = await _load_row(db, scope)
    if row is None:
        row = AiProviderConfig(scope=scope, label=_SCOPE_LABELS[scope])
        db.add(row)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "chat_models":
            # 列表 -> 逗号分隔存储；空列表表示不限制。
            row.chat_models = ",".join(value) if value else None
        elif field == "enabled":
            row.enabled = bool(value)
        elif value is None:
            # None = 不改动；空串 = 清除该字段（回落环境变量）。
            continue
        elif field in ("api_key", "embedding_api_key"):
            text = str(value).strip()
            setattr(row, field, text or None)
        elif field == "timeout_seconds":
            row.timeout_seconds = str(value)
        else:
            setattr(row, field, str(value).strip() or None)

    await db.commit()
    await refresh_cache()
    config = await load_config(scope, db)
    payload_out = config_to_dict(config)
    payload_out["label"] = _SCOPE_LABELS[scope]
    return _envelope(AiConfigRead(**payload_out))


@router.post(
    "/{scope}/test",
    response_model=dict,
    dependencies=[Depends(PermissionChecker("ai:config"))],
)
async def test_ai_config(
    scope: str, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """最小连通性探测：只回类型与延迟，不回上游响应体与密钥。"""
    _require_admin(request)
    _require_scope(scope)

    config = await load_config(scope, db)
    if not config.api_key:
        return _envelope(
            AiConfigTestResult(
                scope=scope, ok=False, detail="尚未配置 API Key，无法测试"
            ).model_dump()
        )

    started = time.perf_counter()
    try:
        from app.adapters.none import NoneAdapter

        adapter = _build_probe_adapter(config)
        if isinstance(adapter, NoneAdapter):
            raise RuntimeError("adapter-not-available")
        await adapter.chat(
            session_id=f"ai_config_test:{scope}",
            message="ping",
            history=[{"role": "system", "content": "只回复 pong"}],
            stream=False,
            model=config.chat_model,
        )
    except Exception as exc:  # noqa: BLE001 —— 探测结果只回异常类型
        return _envelope(
            AiConfigTestResult(
                scope=scope,
                ok=False,
                model=config.chat_model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail=f"连接失败（{type(exc).__name__}）",
            ).model_dump()
        )

    return _envelope(
        AiConfigTestResult(
            scope=scope,
            ok=True,
            model=config.chat_model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=f"连接成功，密钥 {mask_key(config.api_key)}",
        ).model_dump()
    )


def _build_probe_adapter(config):
    """用待测配置构造一次性适配器；失败时返回 NoneAdapter。"""
    from app.adapters.factory import build_adapter

    return build_adapter(
        adapter_type="openai",
        api_url=config.api_url,
        api_key=config.api_key,
        chat_model=config.chat_model,
        embedding_model=config.embedding_model,
        timeout=min(config.timeout_seconds or 10.0, 10.0),
        max_retries=0,
        allowed_chat_models=frozenset(config.chat_models or ()),
    )
