"""Comprehensive tests for the AI adapter contract.

These are pure unit tests — they do NOT import ``app.main`` or touch the database.
See ``tests/conftest.py`` for the integration test layer.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.base import (
    CHAT_RESPONSE_FIELDS,
    STREAM_EVENT_TYPES,
    AIServiceAdapter,
)
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
from app.adapters.factory import build_adapter
from app.adapters.none import NoneAdapter
from app.adapters.openai import (
    EMBEDDING_DIM_DEFAULT,
    OpenAIAdapter,
    OpenAIConfig,
    _coerce_tool_calls,
    _map_http_status_error,
    get_vector_dim,
    register_vector_dim,
)


# ===================================================================
# Base contract
# ===================================================================
class TestBaseContract:
    def test_chat_response_fields_are_complete(self):
        expected = {"answer", "sources", "tool_calls", "session_id", "model", "usage"}
        assert set(CHAT_RESPONSE_FIELDS) == expected

    def test_stream_event_types_are_complete(self):
        expected = {"session", "delta", "source", "done", "error"}
        assert set(STREAM_EVENT_TYPES) == expected

    def test_base_is_abstract(self):
        class Incomplete(AIServiceAdapter):
            pass

        with pytest.raises(TypeError):
            Incomplete()


# ===================================================================
# Exception hierarchy
# ===================================================================
class TestExceptions:
    def test_all_exceptions_subclass_base(self):
        for cls in (
            AIAdapterTimeoutError,
            AIAdapterRateLimitError,
            AIAdapterAuthenticationError,
            AIAdapterBadRequestError,
            AIAdapterServerError,
            AIAdapterInvalidResponseError,
            AIAdapterDimensionMismatchError,
            AIAdapterUnavailableError,
        ):
            assert issubclass(cls, AIAdapterError)

    def test_messages_never_contain_sensitive_patterns(self):
        """Sanity check: our hardcoded messages don't leak secrets."""
        sensitive_keywords = ["http://", "https://", "Bearer", "api_key", "sk-"]
        for cls in (
            AIAdapterTimeoutError,
            AIAdapterRateLimitError,
            AIAdapterAuthenticationError,
            AIAdapterBadRequestError,
            AIAdapterServerError,
            AIAdapterInvalidResponseError,
            AIAdapterDimensionMismatchError,
            AIAdapterUnavailableError,
        ):
            msg = cls.__doc__ or ""
            # Instantiate to check the default message if any
            try:
                exc = cls("test")
                msg = str(exc)
            except Exception:
                pass
            for kw in sensitive_keywords:
                assert kw.lower() not in msg.lower(), f"{cls.__name__} leaks {kw}"


# ===================================================================
# NoneAdapter
# ===================================================================
class TestNoneAdapter:
    @pytest.mark.anyio
    async def test_chat_returns_contract_fields(self):
        adapter = NoneAdapter()
        result = await adapter.chat(session_id="s1", message="hi", history=[])
        for field in CHAT_RESPONSE_FIELDS:
            assert field in result
        assert "未配置" in result["answer"]
        assert result["sources"] == []
        assert result["tool_calls"] == []
        assert result["session_id"] == "s1"
        assert result["model"] is None
        assert result["usage"] is None

    @pytest.mark.anyio
    async def test_chat_stream_yields_error_event(self):
        adapter = NoneAdapter()
        events = []
        async for event in adapter.chat_stream(session_id="s1", message="hi", history=[]):
            events.append(event)
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert events[0]["session_id"] == "s1"
        assert "未配置" in events[0]["error"]

    @pytest.mark.anyio
    async def test_embed_raises_unavailable(self):
        adapter = NoneAdapter()
        with pytest.raises(AIAdapterUnavailableError):
            await adapter.embed(["hello"])

    @pytest.mark.anyio
    async def test_embed_one_raises_unavailable(self):
        adapter = NoneAdapter()
        with pytest.raises(AIAdapterUnavailableError):
            await adapter.embed_one("hello")

    def test_parse_tool_calls_returns_empty(self):
        adapter = NoneAdapter()
        assert adapter.parse_tool_calls({"anything": True}) == []

    @pytest.mark.anyio
    async def test_manage_session_returns_available_false(self):
        adapter = NoneAdapter()
        result = await adapter.manage_session("create", "s1")
        assert result["available"] is False
        assert result["backend"] == "none"

    @pytest.mark.anyio
    async def test_aclose_is_noop(self):
        adapter = NoneAdapter()
        await adapter.aclose()  # should not raise

    def test_available_flag(self):
        assert NoneAdapter().available is False


# ===================================================================
# OpenAIConfig
# ===================================================================
class TestOpenAIConfig:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            OpenAIConfig(api_key="")

    def test_defaults(self):
        cfg = OpenAIConfig(api_key="sk-test")
        assert cfg.api_url == "https://api.openai.com/v1"
        assert cfg.chat_model == "gpt-4o-mini"
        assert cfg.embedding_model == "text-embedding-3-small"
        assert cfg.timeout == 30.0
        assert cfg.max_retries == 2

    def test_paths(self):
        cfg = OpenAIConfig(api_key="sk-test")
        assert cfg.chat_path() == "/chat/completions"
        assert cfg.embedding_path() == "/embeddings"


# ===================================================================
# OpenAIAdapter — tool call coercion
# ===================================================================
class TestCoerceToolCalls:
    def test_empty(self):
        assert _coerce_tool_calls(None) == []
        assert _coerce_tool_calls([]) == []

    def test_standard_openai_format(self):
        raw = [
            {
                "id": "tc_1",
                "function": {
                    "name": "search",
                    "arguments": '{"q": "hello"}',
                },
            }
        ]
        result = _coerce_tool_calls(raw)
        assert result == [{"id": "tc_1", "name": "search", "arguments": {"q": "hello"}}]

    def test_already_dict_arguments(self):
        raw = [
            {
                "id": "tc_1",
                "function": {
                    "name": "search",
                    "arguments": {"q": "hello"},
                },
            }
        ]
        result = _coerce_tool_calls(raw)
        assert result == [{"id": "tc_1", "name": "search", "arguments": {"q": "hello"}}]

    def test_malformed_json_arguments_falls_back_to_raw(self):
        raw = [
            {
                "id": "tc_1",
                "function": {
                    "name": "search",
                    "arguments": "{not json",
                },
            }
        ]
        result = _coerce_tool_calls(raw)
        assert result == [{"id": "tc_1", "name": "search", "arguments": {"_raw": "{not json"}}]


# ===================================================================
# OpenAIAdapter — error mapping
# ===================================================================
class TestMapHttpStatusError:
    def _make_exc(self, code: int) -> httpx.HTTPStatusError:
        return httpx.HTTPStatusError(
            str(code),
            request=MagicMock(),
            response=MagicMock(status_code=code),
        )

    def test_401_raises_authentication(self):
        with pytest.raises(AIAdapterAuthenticationError):
            _map_http_status_error(self._make_exc(401))

    def test_403_raises_authentication(self):
        with pytest.raises(AIAdapterAuthenticationError):
            _map_http_status_error(self._make_exc(403))

    def test_429_raises_rate_limit(self):
        with pytest.raises(AIAdapterRateLimitError):
            _map_http_status_error(self._make_exc(429))

    def test_400_raises_bad_request(self):
        with pytest.raises(AIAdapterBadRequestError):
            _map_http_status_error(self._make_exc(400))

    def test_500_raises_server_error(self):
        with pytest.raises(AIAdapterServerError):
            _map_http_status_error(self._make_exc(500))

    def test_503_raises_server_error(self):
        with pytest.raises(AIAdapterServerError):
            _map_http_status_error(self._make_exc(503))


# ===================================================================
# OpenAIAdapter — chat (non-streaming)
# ===================================================================
class TestOpenAIAdapterChat:
    @pytest.fixture
    def cfg(self):
        return OpenAIConfig(api_key="sk-test", api_url="http://test", timeout=5.0)

    @pytest.fixture
    def adapter(self, cfg):
        return OpenAIAdapter(cfg)

    @pytest.mark.anyio
    async def test_chat_returns_contract_fields(self, adapter):
        fake_resp = {
            "id": "chatcmpl-1",
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello!",
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        with patch.object(
            adapter, "_post", new=AsyncMock(return_value=fake_resp)
        ):
            result = await adapter.chat(session_id="s1", message="hi", history=[])

        for field in CHAT_RESPONSE_FIELDS:
            assert field in result
        assert result["answer"] == "Hello!"
        assert result["sources"] == []
        assert result["tool_calls"] == []
        assert result["session_id"] == "s1"
        assert result["model"] == "gpt-4o-mini"
        assert result["usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    @pytest.mark.anyio
    async def test_chat_with_tool_calls(self, adapter):
        fake_resp = {
            "choices": [
                {
                    "message": {
                        "content": "Let me search.",
                        "tool_calls": [
                            {
                                "id": "tc_1",
                                "function": {"name": "search", "arguments": '{"q": "x"}'},
                            }
                        ],
                    }
                }
            ],
            "model": "gpt-4o-mini",
            "usage": None,
        }
        with patch.object(
            adapter, "_post", new=AsyncMock(return_value=fake_resp)
        ):
            result = await adapter.chat(session_id="s1", message="hi", history=[])
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search"

    @pytest.mark.anyio
    async def test_chat_propagates_timeout(self, adapter):
        adapter._client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with pytest.raises(AIAdapterTimeoutError):
            await adapter.chat(session_id="s1", message="hi", history=[])

    @pytest.mark.anyio
    async def test_chat_propagates_auth_error(self, adapter):
        adapter._client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "401",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )
        )
        with pytest.raises(AIAdapterAuthenticationError):
            await adapter.chat(session_id="s1", message="hi", history=[])

    @pytest.mark.anyio
    async def test_chat_propagates_server_error(self, adapter):
        adapter._client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        with pytest.raises(AIAdapterServerError):
            await adapter.chat(session_id="s1", message="hi", history=[])

    @pytest.mark.anyio
    async def test_chat_propagates_invalid_json(self, adapter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(side_effect=json.JSONDecodeError("bad", "doc", 0))
        adapter._client.post = AsyncMock(return_value=mock_response)
        with pytest.raises(AIAdapterInvalidResponseError):
            await adapter.chat(session_id="s1", message="hi", history=[])


# ===================================================================
# OpenAIAdapter — chat_stream
# ===================================================================
class TestOpenAIAdapterChatStream:
    @pytest.fixture
    def cfg(self):
        return OpenAIConfig(api_key="sk-test", api_url="http://test", timeout=5.0)

    @pytest.fixture
    def adapter(self, cfg):
        return OpenAIAdapter(cfg)

    def _make_streaming_response(self, chunks: list[str]):
        """Build a mock that simulates httpx.AsyncClient.stream context manager."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async def aiter_lines():
            for line in chunks:
                yield line

        mock_resp.aiter_lines = aiter_lines
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        return mock_cm

    @pytest.mark.anyio
    async def test_stream_yields_delta_then_done(self, adapter):
        chunks = [
            "data: " + json.dumps(
                {"id": "c1", "model": "gpt-4o-mini", "choices": [{"delta": {"content": "Hello"}}]}
            ),
            "data: " + json.dumps(
                {"id": "c1", "choices": [{"delta": {"content": " world"}}]}
            ),
            "data: [DONE]",
        ]
        mock_cm = self._make_streaming_response(chunks)
        with patch.object(adapter._client, "stream", return_value=mock_cm):
            events = []
            async for event in adapter.chat_stream(session_id="s1", message="hi", history=[]):
                events.append(event)

        assert events[0]["type"] == "session"
        assert events[0]["session_id"] == "s1"
        assert events[1]["type"] == "delta"
        assert events[1]["delta"] == "Hello"
        assert events[2]["type"] == "delta"
        assert events[2]["delta"] == " world"
        assert events[-1]["type"] == "done"
        assert events[-1]["answer"] == "Hello world"
        assert events[-1]["sources"] == []
        assert events[-1]["tool_calls"] == []

    @pytest.mark.anyio
    async def test_stream_yields_error_on_bad_status(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.aiter_lines = AsyncMock(return_value=iter([]))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        with patch.object(adapter._client, "stream", return_value=mock_cm):
            events = []
            async for event in adapter.chat_stream(session_id="s1", message="hi", history=[]):
                events.append(event)
        assert [event["type"] for event in events] == ["session", "error"]

    @pytest.mark.anyio
    async def test_stream_event_types_conform(self, adapter):
        chunks = [
            "data: " + json.dumps(
                {"id": "c1", "choices": [{"delta": {"content": "x"}}]}
            ),
            "data: [DONE]",
        ]
        mock_cm = self._make_streaming_response(chunks)
        with patch.object(adapter._client, "stream", return_value=mock_cm):
            async for event in adapter.chat_stream(session_id="s1", message="hi", history=[]):
                assert event["type"] in STREAM_EVENT_TYPES
                assert "session_id" in event


# ===================================================================
# OpenAIAdapter — embeddings
# ===================================================================
class TestOpenAIAdapterEmbeddings:
    @pytest.fixture
    def cfg(self):
        return OpenAIConfig(api_key="sk-test", api_url="http://test", timeout=5.0)

    @pytest.fixture
    def adapter(self, cfg):
        return OpenAIAdapter(cfg)

    @pytest.mark.anyio
    async def test_embed_empty_list(self, adapter):
        assert await adapter.embed([]) == []

    @pytest.mark.anyio
    async def test_embed_one_delegates(self, adapter):
        with patch.object(adapter, "embed", new=AsyncMock(return_value=[[0.1, 0.2]])):
            result = await adapter.embed_one("hello")
            assert result == [0.1, 0.2]

    @pytest.mark.anyio
    async def test_embed_one_returns_empty_for_empty(self, adapter):
        with patch.object(adapter, "embed", new=AsyncMock(return_value=[])):
            result = await adapter.embed_one("hello")
            assert result == []

    @pytest.mark.anyio
    async def test_embed_validates_dimension(self, adapter):
        register_vector_dim(128)
        fake_resp = {
            "data": [{"index": 0, "embedding": [0.1] * 64}],  # wrong dim
        }
        with patch.object(
            adapter, "_post", new=AsyncMock(return_value=fake_resp)
        ):
            with pytest.raises(AIAdapterDimensionMismatchError, match="expected 128"):
                await adapter.embed(["hello"])
        register_vector_dim(EMBEDDING_DIM_DEFAULT)

    @pytest.mark.anyio
    async def test_embed_accepts_correct_dimension(self, adapter):
        register_vector_dim(3)
        fake_resp = {
            "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}],
        }
        with patch.object(
            adapter, "_post", new=AsyncMock(return_value=fake_resp)
        ):
            result = await adapter.embed(["hello"])
            assert result == [[0.1, 0.2, 0.3]]
        register_vector_dim(EMBEDDING_DIM_DEFAULT)

    @pytest.mark.anyio
    async def test_embed_sorts_by_index(self, adapter):
        register_vector_dim(3)
        fake_resp = {
            "data": [
                {"index": 2, "embedding": [0.6, 0.7, 0.8]},
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                {"index": 1, "embedding": [0.4, 0.5, 0.6]},
            ],
        }
        with patch.object(
            adapter, "_post", new=AsyncMock(return_value=fake_resp)
        ):
            result = await adapter.embed(["a", "b", "c"])
            assert result == [
                [0.1, 0.2, 0.3],
                [0.4, 0.5, 0.6],
                [0.6, 0.7, 0.8],
            ]
        register_vector_dim(EMBEDDING_DIM_DEFAULT)


# ===================================================================
# OpenAIAdapter — lifecycle
# ===================================================================
class TestOpenAIAdapterLifecycle:
    @pytest.mark.anyio
    async def test_aclose_closes_client(self):
        cfg = OpenAIConfig(api_key="sk-test")
        adapter = OpenAIAdapter(cfg)
        with patch.object(adapter._client, "aclose", new=AsyncMock()) as mock_close:
            await adapter.aclose()
            mock_close.assert_awaited_once()

    @pytest.mark.anyio
    async def test_context_manager(self):
        cfg = OpenAIConfig(api_key="sk-test")
        async with OpenAIAdapter(cfg) as adapter:
            assert isinstance(adapter, OpenAIAdapter)
        # After exit, client should be closed (we can't easily assert without
        # mocking, but the __aexit__ calls aclose).


# ===================================================================
# OpenAIAdapter — session management
# ===================================================================
class TestOpenAIAdapterSession:
    @pytest.fixture
    def adapter(self):
        return OpenAIAdapter(OpenAIConfig(api_key="sk-test"))

    @pytest.mark.anyio
    async def test_create_session(self, adapter):
        result = await adapter.manage_session("create", "s1")
        assert result["session_id"] == "s1"
        assert result["created"] is True
        assert result["backend"] == "openai"

    @pytest.mark.anyio
    async def test_create_generates_uuid(self, adapter):
        result = await adapter.manage_session("create")
        assert result["session_id"]
        assert result["created"] is True

    @pytest.mark.anyio
    async def test_get_session(self, adapter):
        result = await adapter.manage_session("get", "s1")
        assert result["session_id"] == "s1"
        assert result["messages"] == []

    @pytest.mark.anyio
    async def test_delete_session(self, adapter):
        result = await adapter.manage_session("delete", "s1")
        assert result["deleted"] is True

    @pytest.mark.anyio
    async def test_unknown_action(self, adapter):
        result = await adapter.manage_session("bogus")
        assert "error" in result


# ===================================================================
# OpenAIAdapter — parse_tool_calls (code-fence fallback)
# ===================================================================
class TestOpenAIAdapterParseToolCalls:
    @pytest.fixture
    def adapter(self):
        return OpenAIAdapter(OpenAIConfig(api_key="sk-test"))

    def test_normalized_input_passthrough(self, adapter):
        raw = {"tool_calls": [{"name": "search", "arguments": {"q": "x"}}]}
        result = adapter.parse_tool_calls(raw)
        assert result == [{"name": "search", "arguments": {"q": "x"}}]

    def test_code_fence_json(self, adapter):
        raw = {"answer": '```json\n{"name": "search", "arguments": {}}\n```'}
        result = adapter.parse_tool_calls(raw)
        assert len(result) == 1
        assert result[0]["name"] == "search"

    def test_code_fence_plain(self, adapter):
        raw = {"answer": '```{"name": "search", "arguments": {}}```'}
        result = adapter.parse_tool_calls(raw)
        assert len(result) == 1

    def test_no_tool_calls_returns_empty(self, adapter):
        assert adapter.parse_tool_calls({"answer": "just text"}) == []


# ===================================================================
# Factory — build_adapter
# ===================================================================
class TestBuildAdapter:
    def test_none_when_adapter_type_is_none(self):
        assert isinstance(build_adapter(None), NoneAdapter)

    def test_none_when_adapter_type_is_none_string(self):
        assert isinstance(build_adapter("none"), NoneAdapter)

    def test_none_when_adapter_type_is_unknown(self):
        assert isinstance(build_adapter("unknown_xyz"), NoneAdapter)

    def test_openai_without_api_key_returns_none_adapter(self):
        """Fail-closed: missing api_key -> NoneAdapter."""
        adapter = build_adapter("openai", api_key=None)
        assert isinstance(adapter, NoneAdapter)

    def test_openai_without_api_key_empty_string_returns_none_adapter(self):
        adapter = build_adapter("openai", api_key="")
        assert isinstance(adapter, NoneAdapter)

    def test_openai_with_api_key_returns_openai_adapter(self):
        adapter = build_adapter(
            "openai",
            api_key="sk-test",
            api_url="http://localhost:1234",
            chat_model="gpt-4o",
            embedding_model="text-embedding-3-large",
            timeout=10.0,
        )
        assert isinstance(adapter, OpenAIAdapter)
        assert adapter.cfg.api_key == "sk-test"
        assert adapter.cfg.api_url == "http://localhost:1234"
        assert adapter.cfg.chat_model == "gpt-4o"
        assert adapter.cfg.embedding_model == "text-embedding-3-large"
        assert adapter.cfg.timeout == 10.0

    def test_future_engines_return_none_adapter(self):
        for engine in ("fastgpt", "dify", "ragflow"):
            assert isinstance(build_adapter(engine), NoneAdapter)


# ===================================================================
# Vector dim registry
# ===================================================================
class TestVectorDimRegistry:
    def test_get_default(self):
        assert get_vector_dim() == EMBEDDING_DIM_DEFAULT

    def test_register_and_get(self):
        register_vector_dim(768)
        assert get_vector_dim() == 768
        register_vector_dim(EMBEDDING_DIM_DEFAULT)

    def test_register_rejects_zero(self):
        with pytest.raises(ValueError):
            register_vector_dim(0)

    def test_register_rejects_negative(self):
        with pytest.raises(ValueError):
            register_vector_dim(-1)

    def test_register_rejects_too_large(self):
        with pytest.raises(ValueError):
            register_vector_dim(9999)
