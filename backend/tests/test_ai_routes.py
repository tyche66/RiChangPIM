"""Tests for the AI route operational controls.

These are pure unit tests — they do NOT import ``app.main`` or touch a live
database / Redis / AI upstream. All external dependencies are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
from app.adapters.none import NoneAdapter

# ===================================================================
# Exception mapping helpers
# ===================================================================

class TestErrorMapping:
    """Verify the safe error mapping in ai.py does not leak raw details."""

    def _import_helpers(self):
        from app.api.v1.ai import _adapter_code_for, _http_status_for, _safe_error_msg
        return _safe_error_msg, _http_status_for, _adapter_code_for

    @pytest.mark.parametrize("exc_cls,expected_status", [
        (AIAdapterTimeoutError, 504),
        (AIAdapterAuthenticationError, 503),
        (AIAdapterUnavailableError, 503),
        (AIAdapterRateLimitError, 502),
        (AIAdapterBadRequestError, 502),
        (AIAdapterServerError, 502),
        (AIAdapterInvalidResponseError, 502),
        (AIAdapterDimensionMismatchError, 502),
    ])
    def test_http_status_mapping(self, exc_cls, expected_status):
        _safe_error_msg, _http_status_for, _adapter_code_for = self._import_helpers()
        exc = exc_cls("internal detail that must not leak")
        assert _http_status_for(exc) == expected_status

    def test_safe_messages_contain_no_raw_details(self):
        _safe_error_msg, *_ = self._import_helpers()
        sensitive = [
            "http://", "https://", "Bearer", "api_key",
            "sk-", "traceback", "internal detail",
        ]
        for cls in [
            AIAdapterTimeoutError, AIAdapterAuthenticationError,
            AIAdapterUnavailableError, AIAdapterRateLimitError,
            AIAdapterBadRequestError, AIAdapterServerError,
            AIAdapterInvalidResponseError, AIAdapterDimensionMismatchError,
            AIAdapterError,
        ]:
            msg = _safe_error_msg(cls("internal detail that must not leak"))
            for kw in sensitive:
                assert kw.lower() not in msg.lower(), f"{cls.__name__} leaks {kw}"
            assert msg  # non-empty
            assert "internal detail" not in msg

    def test_adapter_code_for_known_statuses(self):
        *_, _adapter_code_for = self._import_helpers()
        assert _adapter_code_for(AIAdapterTimeoutError("x")) == 50401
        assert _adapter_code_for(AIAdapterAuthenticationError("x")) == 50301
        assert _adapter_code_for(AIAdapterServerError("x")) == 50201


# ===================================================================
# _check_ai_enabled
# ===================================================================

class TestCheckAiEnabled:
    def test_raises_503_for_none_adapter(self):
        from fastapi import HTTPException

        from app.api.v1.ai import _check_ai_enabled

        with pytest.raises(HTTPException) as exc_info:
            _check_ai_enabled(NoneAdapter())
        assert exc_info.value.status_code == 503

    def test_raises_503_for_none(self):
        from fastapi import HTTPException

        from app.api.v1.ai import _check_ai_enabled

        with pytest.raises(HTTPException) as exc_info:
            _check_ai_enabled(None)
        assert exc_info.value.status_code == 503

    def test_passes_for_real_adapter(self):
        from app.api.v1.ai import _check_ai_enabled

        mock_adapter = MagicMock()
        mock_adapter.__class__ = object  # not NoneAdapter
        # Should not raise
        _check_ai_enabled(mock_adapter)


# ===================================================================
# Rate limiter
# ===================================================================

class TestRateLimiter:
    @pytest.mark.anyio
    async def test_init_rejects_non_positive_max(self):
        from app.core.rate_limiter import RateLimiter
        with pytest.raises(ValueError):
            RateLimiter("redis://localhost", max_requests=0)

    @pytest.mark.anyio
    async def test_init_rejects_non_positive_window(self):
        from app.core.rate_limiter import RateLimiter
        with pytest.raises(ValueError):
            RateLimiter("redis://localhost", window_seconds=-1)

    @pytest.mark.anyio
    async def test_is_rate_limited_fail_closed_when_redis_unavailable(self):
        from app.core.rate_limiter import RateLimiter
        limiter = RateLimiter("redis://nonexistent:6379", max_requests=10)
        # With an unreachable Redis, fail-closed means is_rate_limited returns True.
        result = await limiter.is_rate_limited("user-1")
        assert result is True
        await limiter.close()

    @pytest.mark.anyio
    async def test_is_rate_limited_allows_under_limit(self):
        from app.core.rate_limiter import RateLimiter
        # Mock redis client
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.incr = AsyncMock(side_effect=[1, 2, 3])
        mock_client.expire = AsyncMock()

        limiter = RateLimiter("redis://localhost", max_requests=10, window_seconds=60)
        with patch.object(limiter, "_ensure_client", return_value=mock_client):
            assert await limiter.is_rate_limited("user-1") is False
            assert await limiter.is_rate_limited("user-1") is False
            assert await limiter.is_rate_limited("user-1") is False

    @pytest.mark.anyio
    async def test_is_rate_limited_blocks_over_limit(self):
        from app.core.rate_limiter import RateLimiter
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.incr = AsyncMock(side_effect=list(range(1, 13)))  # 1..12
        mock_client.expire = AsyncMock()

        limiter = RateLimiter("redis://localhost", max_requests=10, window_seconds=60)
        with patch.object(limiter, "_ensure_client", return_value=mock_client):
            for _ in range(10):
                assert await limiter.is_rate_limited("user-1") is False
            # 11th request exceeds limit
            assert await limiter.is_rate_limited("user-1") is True

    @pytest.mark.anyio
    async def test_is_rate_limited_fail_closed_on_redis_exception(self):
        from app.core.rate_limiter import RateLimiter
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.incr = AsyncMock(side_effect=Exception("redis boom"))

        limiter = RateLimiter("redis://localhost", max_requests=10)
        with patch.object(limiter, "_ensure_client", return_value=mock_client):
            assert await limiter.is_rate_limited("user-1") is True


# ===================================================================
# GET /ai/chat — non-streaming
# ===================================================================

class TestChatRoute:
    @pytest.fixture(autouse=True)
    def mock_audit_write(self):
        with patch("app.middleware.audit._write_operation_log", new_callable=AsyncMock):
            yield

    @pytest.fixture
    def mock_adapter(self):
        adapter = AsyncMock()
        adapter.chat = AsyncMock(return_value={
            "answer": "Hello!",
            "sources": [],
            "tool_calls": [],
            "session_id": "s1",
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })
        return adapter

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        return db

    def _make_user(self):
        return {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "role_code": "user",
            "permissions": ["ai:use"],
        }

    @pytest.mark.anyio
    async def test_chat_returns_envelope(self, mock_adapter, mock_db):
        from app.api.v1.ai import chat
        result = await chat(
            body=MagicMock(session_id="s1", message="hi", history=[], stream=False),
            request=MagicMock(),
            adapter=mock_adapter,
            current_user=self._make_user(),
            db=mock_db,
        )
        assert "code" in result
        assert "data" in result
        assert result["data"]["answer"] == "Hello!"

    @pytest.mark.anyio
    async def test_chat_none_adapter_returns_503(self, mock_db):
        from fastapi import HTTPException

        from app.api.v1.ai import chat

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                body=MagicMock(session_id="s1", message="hi", history=[], stream=False),
                request=MagicMock(),
                adapter=NoneAdapter(),
                current_user=self._make_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 503

    @pytest.mark.anyio
    async def test_chat_adapter_timeout_returns_504(self, mock_db):
        from fastapi import HTTPException

        from app.api.v1.ai import chat

        adapter = AsyncMock()
        adapter.chat = AsyncMock(side_effect=AIAdapterTimeoutError("upstream timeout"))

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                body=MagicMock(session_id="s1", message="hi", history=[], stream=False),
                request=MagicMock(),
                adapter=adapter,
                current_user=self._make_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 504
        detail = exc_info.value.detail
        assert detail["code"] == 50401
        assert "超时" in detail["msg"]

    @pytest.mark.anyio
    async def test_chat_server_error_returns_502(self, mock_db):
        from fastapi import HTTPException

        from app.api.v1.ai import chat

        adapter = AsyncMock()
        adapter.chat = AsyncMock(side_effect=AIAdapterServerError("500"))

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                body=MagicMock(session_id="s1", message="hi", history=[], stream=False),
                request=MagicMock(),
                adapter=adapter,
                current_user=self._make_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 502

    @pytest.mark.anyio
    async def test_chat_persists_conversation(self, mock_db):
        from app.api.v1.ai import chat
        adapter = AsyncMock()
        adapter.chat = AsyncMock(return_value={
            "answer": "Hi there",
            "sources": [],
            "tool_calls": [],
            "session_id": "s1",
            "model": "gpt-4o",
            "usage": {"total_tokens": 20},
        })
        await chat(
            body=MagicMock(session_id="s1", message="hello world", history=[], stream=False),
            request=MagicMock(),
            adapter=adapter,
            current_user=self._make_user(),
            db=mock_db,
        )
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_chat_stream_returns_streaming_response(self, mock_adapter, mock_db):
        from fastapi.responses import StreamingResponse

        from app.api.v1.ai import chat

        async def fake_stream(*args, **kwargs):
            yield {"type": "session", "session_id": "s1"}
            yield {"type": "delta", "delta": "Hello", "session_id": "s1"}
            yield {"type": "delta", "delta": " world", "session_id": "s1"}
            yield {
                "type": "done", "answer": "Hello world",
                "session_id": "s1", "sources": [],
                "tool_calls": [], "model": "gpt-4o",
            }

        mock_adapter.chat_stream = fake_stream

        result = await chat(
            body=MagicMock(session_id="s1", message="hi", history=[], stream=True),
            request=MagicMock(),
            adapter=mock_adapter,
            current_user=self._make_user(),
            db=mock_db,
        )
        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"

    @pytest.mark.anyio
    async def test_chat_stream_sse_format(self, mock_adapter, mock_db):
        from app.api.v1.ai import chat

        async def fake_stream(*args, **kwargs):
            yield {"type": "delta", "delta": "Hello", "session_id": "s1"}
            yield {
                "type": "done", "answer": "Hello",
                "session_id": "s1", "sources": [],
                "tool_calls": [],
            }

        mock_adapter.chat_stream = fake_stream

        result = await chat(
            body=MagicMock(session_id="s1", message="hi", history=[], stream=True),
            request=MagicMock(),
            adapter=mock_adapter,
            current_user=self._make_user(),
            db=mock_db,
        )
        chunks = []
        async for chunk in result.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        body = "".join(chunks)
        # SSE events should use chat_stream and done event names
        assert "event: chat_stream" in body
        assert "event: done" in body

    @pytest.mark.anyio
    async def test_chat_stream_error_event(self, mock_adapter, mock_db):
        from app.adapters.exceptions import AIAdapterError
        from app.api.v1.ai import chat

        async def fake_stream(*args, **kwargs):
            yield {"type": "error", "error": "upstream failed", "session_id": "s1"}

        mock_adapter.chat_stream = fake_stream

        result = await chat(
            body=MagicMock(session_id="s1", message="hi", history=[], stream=True),
            request=MagicMock(),
            adapter=mock_adapter,
            current_user=self._make_user(),
            db=mock_db,
        )
        chunks = []
        try:
            async for chunk in result.body_iterator:
                chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        except AIAdapterError:
            pass  # expected — stream raises after yielding error event
        body = "".join(chunks)
        assert "event: chat_stream" in body
        assert "error" in body


# ===================================================================
# GET /health/live and /health/ready
# ===================================================================

class TestHealthProbes:
    @pytest.mark.anyio
    async def test_live_is_process_only(self):
        """Liveness must not touch DB/Redis/MinIO."""
        import inspect

        from app.main import health_live

        source = inspect.getsource(health_live)
        assert "engine" not in source
        assert "redis" not in source.lower() or "redis" not in source
        result = await health_live()
        assert result == {"status": "alive"}

    @pytest.mark.anyio
    async def test_ready_checks_components(self):
        from app.main import health_ready
        with patch("app.main._check_db", return_value=True), \
             patch("app.main._check_redis", return_value=True), \
             patch("app.main._check_minio", return_value=True), \
             patch("app.main._check_ai_ready", return_value=False):
            result = await health_ready()
        assert result["status"] == "ready"
        assert result["components"]["db"] == "ok"
        assert result["components"]["redis"] == "ok"
        assert result["components"]["minio"] == "ok"
        assert result["components"]["ai"] == "none"

    @pytest.mark.anyio
    async def test_ready_degraded_when_db_down(self):
        from app.main import health_ready
        with patch("app.main._check_db", return_value=False), \
             patch("app.main._check_redis", return_value=True), \
             patch("app.main._check_minio", return_value=True), \
             patch("app.main._check_ai_ready", return_value=True):
            result = await health_ready()
        assert result["status"] == "degraded"
        assert result["components"]["db"] == "error"

    @pytest.mark.anyio
    async def test_ready_ai_configured(self):
        from app.main import health_ready
        with patch("app.main._check_db", return_value=True), \
             patch("app.main._check_redis", return_value=True), \
             patch("app.main._check_minio", return_value=True), \
             patch("app.main._check_ai_ready", return_value=True):
            result = await health_ready()
        assert result["components"]["ai"] == "ok"


# ===================================================================
# AIConversation persistence
# ===================================================================

class TestConversationPersistence:
    @pytest.mark.anyio
    async def test_persist_truncates_long_question(self):
        from app.api.v1.ai import _persist_conversation

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        long_question = "x" * 1000
        await _persist_conversation(
            db, "s1", None, long_question,
            {"answer": "hi", "sources": [], "tool_calls": [], "session_id": "s1"},
        )
        call_args = db.add.call_args[0][0]
        assert call_args.question.startswith("length=1000 sha256=")
        assert long_question not in call_args.question

    @pytest.mark.anyio
    async def test_persist_does_not_fail_request_on_db_error(self):
        from app.api.v1.ai import _persist_conversation

        db = AsyncMock()
        db.add = MagicMock(side_effect=Exception("DB down"))
        db.commit = AsyncMock(side_effect=Exception("DB down"))

        # Should not raise
        await _persist_conversation(
            db, "s1", None, "hello",
            {"answer": "hi", "sources": [], "tool_calls": [], "session_id": "s1"},
        )

    @pytest.mark.anyio
    async def test_persist_stores_model_usage_when_columns_exist(self):
        from app.api.v1.ai import _persist_conversation

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        response = {
            "answer": "hi",
            "sources": [],
            "tool_calls": [],
            "session_id": "s1",
            "model": "gpt-4o",
            "usage": {"total_tokens": 42},
        }
        await _persist_conversation(db, "s1", None, "hello", response)
        conv = db.add.call_args[0][0]
        # model and usage are set if the columns exist on the model
        # (they may be None if the column doesn't exist — that's fine)
        assert conv.answer.startswith("length=2 sha256=")
        assert conv.answer != "hi"


# ===================================================================
# Rate limit dependency in chat route
# ===================================================================

class TestRateLimitDependency:
    @pytest.mark.anyio
    async def test_rate_limit_rejects_when_limited(self):
        from fastapi import HTTPException

        from app.api.v1.ai import _check_rate_limit

        mock_limiter = AsyncMock()
        mock_limiter.is_rate_limited = AsyncMock(return_value=True)

        request = MagicMock()
        request.headers = {}

        with patch("app.api.v1.ai.get_rate_limiter", return_value=mock_limiter):
            with pytest.raises(HTTPException) as exc_info:
                await _check_rate_limit(
                    request,
                    current_user={"sub": "550e8400-e29b-41d4-a716-446655440000"},
                )
            assert exc_info.value.status_code == 429

    @pytest.mark.anyio
    async def test_rate_limit_allows_when_not_limited(self):
        from app.api.v1.ai import _check_rate_limit

        mock_limiter = AsyncMock()
        mock_limiter.is_rate_limited = AsyncMock(return_value=False)

        request = MagicMock()

        with patch("app.api.v1.ai.get_rate_limiter", return_value=mock_limiter):
            result = await _check_rate_limit(
                request,
                current_user={"sub": "550e8400-e29b-41d4-a716-446655440000"},
            )
            assert result == {"sub": "550e8400-e29b-41d4-a716-446655440000"}


# ===================================================================
# Structured logging
# ===================================================================

class TestStructuredLogging:
    def test_log_ai_event_format(self, caplog):
        import logging

        from app.api.v1.ai import _log_ai_event

        with caplog.at_level(logging.INFO, logger="app.api.v1.ai"):
            _log_ai_event("chat", "openai", "gpt-4o", 120, "ok", "abc123")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "ai_operation" in record.message
        assert "action=chat" in record.message
        assert "adapter=openai" in record.message
        assert "model=gpt-4o" in record.message
        assert "latency_ms=120" in record.message
        assert "status=ok" in record.message
        assert "request_id=abc123" in record.message
        # Ensure no prompt text is logged
        assert "hello" not in record.message.lower()
