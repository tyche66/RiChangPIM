import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AIServiceAdapter
from app.adapters.exceptions import (
    AIAdapterAuthenticationError,
    AIAdapterBadRequestError,
    AIAdapterDimensionMismatchError,
    AIAdapterError,
    AIAdapterInvalidResponseError,
    AIAdapterRateLimitError,
    AIAdapterServerError,
    AIAdapterTimeoutError,
    AIAdapterUnavailableError,
)
from app.adapters.factory import get_ai_adapter
from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.core.database import get_db
from app.core.permission import PermissionChecker
from app.core.rate_limiter import get_rate_limiter
from app.middleware.audit import audit_action
from app.schemas.ai import (
    ChatRequest,
    EmbeddingRequest,
    RagIndexRequest,
    RagSearchRequest,
    RecommendRequest,
)
from app.services.polish import PolishService
from app.services.rag_index import RagIndexer, RagSearcher
from app.services.recommend import RecommendService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _envelope(data: Any, code: int = 200, msg: str = "success") -> dict:
    return {"code": code, "data": data, "msg": msg}


def _safe_error_msg(exc: Exception) -> str:
    """Return a sanitized error message suitable for clients."""
    if isinstance(exc, AIAdapterTimeoutError):
        return "AI 服务响应超时，请稍后重试"
    if isinstance(exc, (AIAdapterAuthenticationError, AIAdapterUnavailableError)):
        return "AI 服务暂时不可用"
    if isinstance(exc, AIAdapterRateLimitError):
        return "AI 服务请求过于频繁，请稍后重试"
    if isinstance(exc, (AIAdapterBadRequestError, AIAdapterServerError)):
        return "AI 服务返回异常，请稍后重试"
    if isinstance(exc, (AIAdapterInvalidResponseError, AIAdapterDimensionMismatchError)):
        return "AI 服务返回数据格式异常"
    if isinstance(exc, AIAdapterError):
        return "AI 服务处理失败"
    return "服务器内部错误"


def _http_status_for(exc: Exception) -> int:
    """Map an adapter exception to the HTTP status we return to clients."""
    if isinstance(exc, AIAdapterTimeoutError):
        return 504
    if isinstance(exc, (AIAdapterAuthenticationError, AIAdapterUnavailableError)):
        return 503
    if isinstance(exc, AIAdapterRateLimitError):
        return 502
    if isinstance(exc, AIAdapterBadRequestError):
        return 502
    if isinstance(exc, AIAdapterServerError):
        return 502
    if isinstance(exc, (AIAdapterInvalidResponseError, AIAdapterDimensionMismatchError)):
        return 502
    if isinstance(exc, AIAdapterError):
        return 502
    return 500


def _adapter_code_for(exc: Exception) -> int:
    """Map to our internal envelope error code."""
    status = _http_status_for(exc)
    return {
        502: 50201,
        503: 50301,
        504: 50401,
    }.get(status, 50001)


def _check_ai_enabled(adapter: AIServiceAdapter) -> None:
    """Raise 503 if AI is explicitly not configured.

    When AI_ADAPTER is None / 'none', get_ai_adapter() returns a NoneAdapter.
    Per spec, AI operations must return 503 (no fake success).
    """
    if adapter is None or isinstance(adapter, NoneAdapter):
        raise HTTPException(
            status_code=503,
            detail=_envelope(
                {"code": 50301, "msg": "AI 能力中心未配置"},
                code=50301,
                msg="AI 能力中心未配置",
            ),
        )


async def _persist_conversation(
    db: AsyncSession,
    session_id: str,
    user_id: UUID | None,
    question: str,
    response: dict[str, Any],
) -> None:
    """Persist a minimal AIConversation record.

    - question is truncated (summary, not full sensitive prompt).
    - usage / model / status are stored when the model defines those columns.
    - Sources / tool_calls are JSON-serialised for audit traceability.
    """
    from app.models.audit import AIConversation

    try:
        question_summary = (
            f"length={len(question)} sha256="
            f"{hashlib.sha256(question.encode('utf-8')).hexdigest()}"
        )
        answer = response.get("answer") or ""
        answer_summary = (
            f"length={len(answer)} sha256="
            f"{hashlib.sha256(answer.encode('utf-8')).hexdigest()}"
        )

        sources_raw = response.get("sources") or []
        tool_calls_raw = response.get("tool_calls") or []

        conv = AIConversation(
            session_id=session_id,
            user_id=user_id,
            question=question_summary,
            answer=answer_summary,
            sources=json.dumps(sources_raw, ensure_ascii=False) if sources_raw else None,
            tool_calls=json.dumps(tool_calls_raw, ensure_ascii=False) if tool_calls_raw else None,
        )

        # Conditionally store newer model fields if present.
        mapper = sa_inspect(AIConversation)
        col_names = {c.key for c in mapper.columns}
        if "model" in col_names:
            conv.model = response.get("model")
        if "token_usage" in col_names:
            usage = response.get("usage")
            conv.token_usage = json.dumps(usage, ensure_ascii=False) if usage else None
        if "status" in col_names:
            conv.status = "completed"
        if "request_summary" in col_names:
            conv.request_summary = question_summary
        if "response_summary" in col_names:
            conv.response_summary = answer_summary

        db.add(conv)
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — persistence must not fail the request
        logger.error("failed to persist AI conversation: %r", exc, exc_info=True)


def _log_ai_event(
    action: str,
    adapter_type: str | None,
    model: str | None,
    latency_ms: int,
    status: str,
    request_id: str,
) -> None:
    """Structured AI operation log — never includes the prompt text."""
    logger.info(
        "ai_operation action=%s adapter=%s model=%s latency_ms=%s status=%s request_id=%s",
        action,
        adapter_type,
        model,
        latency_ms,
        status,
        request_id,
    )


# ---------------------------------------------------------------------------
# Rate-limit dependency
# ---------------------------------------------------------------------------

async def _enforce_rate_limit(current_user: dict) -> dict:
    """Enforce the shared per-user AI limit after authorization succeeds."""
    user_id_raw = current_user.get("sub") or current_user.get("user_id")
    if not user_id_raw:
        # Should not happen — PermissionChecker already validated the token.
        raise HTTPException(status_code=401, detail={"code": 40102, "msg": "无法识别用户"})

    try:
        user_id = UUID(user_id_raw)
    except (ValueError, TypeError):
        user_id = uuid.uuid4()  # fallback — rate limit by a synthetic id

    limiter = get_rate_limiter()
    limited = await limiter.is_rate_limited(user_id)
    if not limiter.available:
        raise HTTPException(
            status_code=503,
            detail={"code": 50303, "msg": "AI 限流服务暂时不可用"},
        )
    if limited:
        raise HTTPException(
            status_code=429,
            detail=_envelope({"code": 42901, "msg": "请求过于频繁，请稍后重试"}, code=42901),
        )
    return current_user


async def _check_rate_limit(
    request: Request,
    current_user: dict = Depends(PermissionChecker("ai:use")),
) -> dict:
    """Authorize AI use, then enforce the shared per-user rate limit."""
    return await _enforce_rate_limit(current_user)


async def _check_admin_rate_limit(
    request: Request,
    current_user: dict = Depends(PermissionChecker("ai:use")),
) -> dict:
    """Reject non-admin callers before consulting the rate-limit service."""
    if current_user.get("role_code") != "admin":
        raise HTTPException(status_code=403, detail={"code": 40301, "msg": "仅管理员可用"})
    return await _enforce_rate_limit(current_user)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/chat", dependencies=[Depends(_check_rate_limit)])
@audit_action("ai_chat", module="ai")
async def chat(
    body: ChatRequest,
    request: Request,
    adapter: AIServiceAdapter = Depends(get_ai_adapter),
    current_user: dict = Depends(PermissionChecker("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    _check_ai_enabled(adapter)
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    session_id = body.session_id or str(uuid.uuid4())
    user_id_raw = current_user.get("sub") or current_user.get("user_id")
    user_id: UUID | None = None
    if user_id_raw:
        try:
            user_id = UUID(user_id_raw)
        except (ValueError, TypeError):
            pass

    adapter_type = getattr(settings, "AI_ADAPTER", None)

    try:
        if body.stream:
            async def _stream_gen() -> AsyncGenerator[str, None]:
                accumulated = ""
                sources_acc: list = []
                tool_calls_acc: list = []
                model_acc: str | None = None
                usage_acc: dict | None = None

                def _sse(event_name: str, payload: dict) -> str:
                    data = json.dumps(payload, ensure_ascii=False)
                    return f"event: {event_name}\ndata: {data}\n\n"

                try:
                    async for event in adapter.chat_stream(
                        session_id=session_id,
                        message=body.message,
                        history=body.history,
                    ):
                        etype = event.get("type", "delta")
                        if etype == "error":
                            err_payload = {
                                "type": "error",
                                "data": event.get("error", "unknown error"),
                            }
                            yield _sse("chat_stream", err_payload)
                            raise AIAdapterError(
                                event.get("error", "unknown stream error")
                            )
                        if etype == "session":
                            yield _sse("chat_stream", event)
                        elif etype == "delta":
                            accumulated += event.get("delta", "")
                            yield _sse("chat_stream", event)
                        elif etype == "source":
                            sources_acc.append(event)
                            yield _sse("chat_stream", event)
                        elif etype == "done":
                            accumulated = event.get("answer", accumulated)
                            sources_acc.extend(event.get("sources") or [])
                            tool_calls_acc.extend(event.get("tool_calls") or [])
                            model_acc = event.get("model")
                            usage_acc = event.get("usage")
                            yield _sse("done", event)

                    # Persist after stream completes.
                    resp_for_persist = {
                        "answer": accumulated,
                        "sources": sources_acc,
                        "tool_calls": tool_calls_acc,
                        "session_id": session_id,
                        "model": model_acc,
                        "usage": usage_acc,
                    }
                    await _persist_conversation(
                        db, session_id, user_id, body.message, resp_for_persist
                    )
                except Exception:
                    # Do not persist on stream error — let the error handler deal with it.
                    raise

            latency_ms = int((time.perf_counter() - start) * 1000)
            _log_ai_event("chat", adapter_type, None, latency_ms, "streaming", request_id)
            return StreamingResponse(
                _stream_gen(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Request-ID": request_id,
                },
            )
        else:
            resp = await adapter.chat(
                session_id=session_id,
                message=body.message,
                history=body.history,
                stream=False,
            )
            await _persist_conversation(db, session_id, user_id, body.message, resp)
            latency_ms = int((time.perf_counter() - start) * 1000)
            _log_ai_event(
                "chat", adapter_type, resp.get("model"), latency_ms, "ok", request_id
            )
            return _envelope(resp)
    except AIAdapterError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event(
            "chat", adapter_type, None, latency_ms, "adapter_error", request_id
        )
        status = _http_status_for(exc)
        raise HTTPException(
            status_code=status,
            detail=_envelope(
                {"code": _adapter_code_for(exc), "msg": _safe_error_msg(exc)},
                code=_adapter_code_for(exc),
                msg=_safe_error_msg(exc),
            ),
        ) from exc


@router.post("/embeddings", dependencies=[Depends(_check_admin_rate_limit)])
@audit_action("ai_embeddings", module="ai")
async def embeddings(
    request: Request,
    body: EmbeddingRequest,
    adapter: AIServiceAdapter = Depends(get_ai_adapter),
    current_user: dict = Depends(PermissionChecker("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    if current_user.get("role_code") != "admin":
        raise HTTPException(status_code=403, detail={"code": 40301, "msg": "仅管理员可用"})
    _check_ai_enabled(adapter)
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    adapter_type = getattr(settings, "AI_ADAPTER", None)
    try:
        texts = body.texts
        embeddings_list = await adapter.embed(texts)
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("embeddings", adapter_type, None, latency_ms, "ok", request_id)
        return _envelope(
            {
                "embeddings": embeddings_list,
                "model": settings.AI_EMBEDDING_MODEL or "text-embedding-3-small",
                "dim": settings.AI_EMBEDDING_DIM,
            }
        )
    except AIAdapterError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("embeddings", adapter_type, None, latency_ms, "adapter_error", request_id)
        status = _http_status_for(exc)
        raise HTTPException(
            status_code=status,
            detail=_envelope(
                {"code": _adapter_code_for(exc), "msg": _safe_error_msg(exc)},
                code=_adapter_code_for(exc),
                msg=_safe_error_msg(exc),
            ),
        ) from exc


@router.post("/rag/search", dependencies=[Depends(_check_rate_limit)])
@audit_action("ai_rag_search", module="ai")
async def rag_search(
    request: Request,
    body: RagSearchRequest,
    adapter: AIServiceAdapter = Depends(get_ai_adapter),
    db: AsyncSession = Depends(get_db),
):
    _check_ai_enabled(adapter)
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    adapter_type = getattr(settings, "AI_ADAPTER", None)
    try:
        searcher = RagSearcher(
            adapter,
            db,
            top_k=body.top_k,
            min_score=body.min_score,
        )
        results = await searcher.search(body.query, product_id=body.product_id)
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("rag_search", adapter_type, None, latency_ms, "ok", request_id)
        return _envelope({"results": results, "query": body.query, "total": len(results)})
    except AIAdapterError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("rag_search", adapter_type, None, latency_ms, "adapter_error", request_id)
        status = _http_status_for(exc)
        raise HTTPException(
            status_code=status,
            detail=_envelope(
                {"code": _adapter_code_for(exc), "msg": _safe_error_msg(exc)},
                code=_adapter_code_for(exc),
                msg=_safe_error_msg(exc),
            ),
        ) from exc


@router.post("/rag/index", dependencies=[Depends(_check_admin_rate_limit)])
@audit_action("ai_rag_index", module="ai")
async def rag_index(
    request: Request,
    body: RagIndexRequest,
    adapter: AIServiceAdapter = Depends(get_ai_adapter),
    current_user: dict = Depends(PermissionChecker("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    if current_user.get("role_code") != "admin":
        raise HTTPException(status_code=403, detail={"code": 40301, "msg": "仅管理员可用"})
    _check_ai_enabled(adapter)
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    adapter_type = getattr(settings, "AI_ADAPTER", None)
    try:
        indexer = RagIndexer(
            db,
            chunk_size=settings.AI_RAG_CHUNK_SIZE,
            chunk_overlap=settings.AI_RAG_CHUNK_OVERLAP,
        )
        count = await indexer.index_manual(body.product_manual_id, adapter=adapter)
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("rag_index", adapter_type, None, latency_ms, "ok", request_id)
        return _envelope({"indexed": count, "manual_id": body.product_manual_id})
    except AIAdapterError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("rag_index", adapter_type, None, latency_ms, "adapter_error", request_id)
        status = _http_status_for(exc)
        raise HTTPException(
            status_code=status,
            detail=_envelope(
                {"code": _adapter_code_for(exc), "msg": _safe_error_msg(exc)},
                code=_adapter_code_for(exc),
                msg=_safe_error_msg(exc),
            ),
        ) from exc


@router.post("/proposal/{proposal_id}/polish", dependencies=[Depends(_check_rate_limit)])
@audit_action("ai_polish", module="ai")
async def polish_proposal(
    request: Request,
    proposal_id: UUID,
    adapter: AIServiceAdapter = Depends(get_ai_adapter),
    current_user: dict = Depends(PermissionChecker("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    _check_ai_enabled(adapter)
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    adapter_type = getattr(settings, "AI_ADAPTER", None)
    try:
        service = PolishService(adapter, db, model=settings.AI_CHAT_MODEL)
        result = await service.polish_proposal(proposal_id, current_user)
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("polish", adapter_type, settings.AI_CHAT_MODEL, latency_ms, "ok", request_id)
        return _envelope(result)
    except AIAdapterError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("polish", adapter_type, None, latency_ms, "adapter_error", request_id)
        status = _http_status_for(exc)
        raise HTTPException(
            status_code=status,
            detail=_envelope(
                {"code": _adapter_code_for(exc), "msg": _safe_error_msg(exc)},
                code=_adapter_code_for(exc),
                msg=_safe_error_msg(exc),
            ),
        ) from exc


@router.post("/recommend", dependencies=[Depends(_check_rate_limit)])
@audit_action("ai_recommend", module="ai")
async def recommend(
    request: Request,
    body: RecommendRequest,
    adapter: AIServiceAdapter = Depends(get_ai_adapter),
    current_user: dict = Depends(PermissionChecker("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    _check_ai_enabled(adapter)
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    adapter_type = getattr(settings, "AI_ADAPTER", None)
    try:
        service = RecommendService(adapter, db, model=settings.AI_CHAT_MODEL)
        result = await service.recommend(
            body.requirement,
            current_user,
            limit=body.limit,
            role_code=current_user.get("role_code"),
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event(
            "recommend", adapter_type, settings.AI_CHAT_MODEL, latency_ms, "ok", request_id
        )
        return _envelope(result)
    except AIAdapterError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _log_ai_event("recommend", adapter_type, None, latency_ms, "adapter_error", request_id)
        status = _http_status_for(exc)
        raise HTTPException(
            status_code=status,
            detail=_envelope(
                {"code": _adapter_code_for(exc), "msg": _safe_error_msg(exc)},
                code=_adapter_code_for(exc),
                msg=_safe_error_msg(exc),
            ),
        ) from exc
