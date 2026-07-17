"""OpenAI-compatible chat/embeddings adapter.

Conforms to the AIServiceAdapter contract. Works with any endpoint that exposes
the OpenAI Chat Completions + Embeddings API surface (official OpenAI, Azure
OpenAI, local vLLM/Ollama OpenAI-compatible servers, etc.).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx

from app.adapters.base import AIServiceAdapter
from app.adapters.exceptions import (
    AIAdapterAuthenticationError,
    AIAdapterBadRequestError,
    AIAdapterDimensionMismatchError,
    AIAdapterInvalidResponseError,
    AIAdapterRateLimitError,
    AIAdapterServerError,
    AIAdapterTimeoutError,
)

logger = logging.getLogger(__name__)

EMBEDDING_DIM_DEFAULT = 1536

# ---------------------------------------------------------------------------
# Embedding dim registry — process-global so RAG and adapter agree on the dim.
# ---------------------------------------------------------------------------
_VECTOR_DIM = EMBEDDING_DIM_DEFAULT


def register_vector_dim(dim: int) -> None:
    """Set the embedding vector dimension used by RAG.

    Called once at app startup based on AI_EMBEDDING_DIM env.
    """
    global _VECTOR_DIM
    if dim <= 0 or dim > 8192:
        raise ValueError(f"invalid AI_EMBEDDING_DIM: {dim}")
    _VECTOR_DIM = dim


def get_vector_dim() -> int:
    return _VECTOR_DIM


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class OpenAIConfig:
    api_key: str
    api_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    timeout: float = 30.0
    max_retries: int = 2

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("OpenAIConfig.api_key is required")

    def chat_path(self) -> str:
        return "/chat/completions"

    def embedding_path(self) -> str:
        return "/embeddings"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TOOL_CALL_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_codefence(text: str) -> str:
    return text.replace("```json", "```").replace("```", "").strip()


def _coerce_tool_calls(raw_tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert OpenAI function/tool format to our normalized dict list.

    Output shape:
        [{"name": str, "arguments": dict, "id": Optional[str]}]
    """
    if not raw_tool_calls:
        return []
    out: list[dict[str, Any]] = []
    for tc in raw_tool_calls:
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        out.append(
            {
                "id": tc.get("id"),
                "name": fn.get("name"),
                "arguments": args or {},
            }
        )
    return out


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
class OpenAIAdapter(AIServiceAdapter):
    """OpenAI-compatible adapter.

    Concurrency:
        A single AsyncClient is reused. httpx is connection-pooled and async-safe.
        For high scale, swap with a per-request client via httpx.AsyncClient(...) locally.

    Lifecycle:
        Use as an async context manager (``async with adapter:``) or call
        ``await adapter.aclose()`` on shutdown to release the HTTP client.
    """

    def __init__(self, cfg: OpenAIConfig):
        self.cfg = cfg
        self._client = httpx.AsyncClient(
            base_url=cfg.api_url.rstrip("/"),
            timeout=httpx.Timeout(cfg.timeout),
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            },
        )

    # ---------- context manager ----------
    async def __aenter__(self) -> OpenAIAdapter:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------- chat ----------
    async def chat(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, str]],
        stream: bool = False,
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.4,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = self._build_messages(system, history, message)
        payload: dict[str, Any] = {
            "model": self.cfg.chat_model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        resp = await self._post(self.cfg.chat_path(), payload)
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        answer = (msg.get("content") or "").strip()
        return {
            "session_id": session_id,
            "answer": answer,
            "sources": [],
            "tool_calls": _coerce_tool_calls(msg.get("tool_calls")),
            "model": resp.get("model"),
            "usage": resp.get("usage"),
        }

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        messages = self._build_messages(None, history, message)
        payload: dict[str, Any] = {
            "model": self.cfg.chat_model,
            "messages": messages,
            "stream": True,
            "temperature": kwargs.pop("temperature", 0.4),
        }
        if kwargs.get("tools"):
            payload["tools"] = kwargs["tools"]

        try:
            full_text = ""
            emitted_id = False
            model = None
            yield {"type": "session", "session_id": session_id}
            async with self._client.stream(
                "POST", self.cfg.chat_path(), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    yield {
                        "type": "error",
                        "session_id": session_id,
                        "error": "upstream streaming request failed",
                    }
                    return
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        yield {
                            "type": "error",
                            "session_id": session_id,
                            "error": "upstream returned malformed streaming data",
                        }
                        return
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    fragment = delta.get("content") or ""
                    if not fragment:
                        continue
                    full_text += fragment
                    if model is None:
                        model = chunk.get("model")
                    yield {
                        "type": "delta",
                        "session_id": session_id,
                        "delta": fragment,
                        "id": chunk.get("id") if not emitted_id else None,
                    }
                    if not emitted_id:
                        emitted_id = True
            yield {
                "type": "done",
                "session_id": session_id,
                "answer": full_text,
                "sources": [],
                "tool_calls": [],
                "model": model,
            }
        except httpx.TimeoutException:
            yield {
                "type": "error",
                "session_id": session_id,
                "error": "upstream request timed out",
            }
        except httpx.HTTPStatusError as exc:
            yield {
                "type": "error",
                "session_id": session_id,
                "error": _map_http_status_error(exc),
            }
        except json.JSONDecodeError:
            yield {
                "type": "error",
                "session_id": session_id,
                "error": "upstream returned malformed streaming data",
            }

    # ---------- embeddings ----------
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding for RAG ingestion.

        OpenAI accepts up to ~2048 inputs per request; we chunk defensively.
        """
        if not texts:
            return []
        expected_dim = get_vector_dim()
        out: list[list[float]] = []
        BATCH = 96
        for i in range(0, len(texts), BATCH):
            chunk = texts[i : i + BATCH]
            resp = await self._post(
                self.cfg.embedding_path(),
                {"model": self.cfg.embedding_model, "input": chunk},
            )
            for item in sorted(resp.get("data") or [], key=lambda d: d.get("index", 0)):
                vec = item.get("embedding")
                if vec is None:
                    continue
                actual_dim = len(vec)
                if actual_dim != expected_dim:
                    raise AIAdapterDimensionMismatchError(
                        f"embedding dimension mismatch: expected {expected_dim}, got {actual_dim}"
                    )
                out.append(vec)
        return out

    async def embed_one(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result[0] if result else []

    # ---------- tool calls ----------
    def parse_tool_calls(self, raw_response: dict[str, Any]) -> list[dict[str, Any]]:
        # OpenAI is already in normalized shape; but tolerate our normalized payload too.
        if "tool_calls" in raw_response and isinstance(raw_response["tool_calls"], list):
            return raw_response["tool_calls"]
        # Fallback: scan the answer for ```json{...}``` code fences.
        answer = raw_response.get("answer") or raw_response.get("content") or ""
        parsed: list[dict[str, Any]] = []
        for match in _TOOL_CALL_RE.findall(answer):
            try:
                obj = json.loads(match)
                if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                    parsed.append(obj)
            except json.JSONDecodeError:
                continue
        return parsed

    # ---------- session management ----------
    async def manage_session(
        self, action: str, session_id: str | None = None
    ) -> dict[str, Any]:
        # OpenAI Chat Completions is stateless; we synthesize session metadata here
        # and let the Business API persist it via AIConversation.
        if action == "create":
            return {
                "session_id": session_id or str(uuid.uuid4()),
                "created": True,
                "backend": "openai",
            }
        if action == "get":
            return {"session_id": session_id, "backend": "openai", "messages": []}
        if action == "delete":
            return {"session_id": session_id, "deleted": True}
        return {"error": f"unknown action: {action}"}

    # ---------- internal helpers ----------
    def _build_messages(
        self,
        system: str | None,
        history: list[dict[str, str]],
        message: str,
    ) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        for h in history or []:
            role = h.get("role")
            content = h.get("content")
            if role in ("user", "assistant", "system") and content:
                msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": message})
        return msgs

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = 0
        last_msg: str | None = None
        while attempts <= self.cfg.max_retries:
            try:
                r = await self._client.post(path, json=payload)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"{r.status_code}", request=r.request, response=r
                    )
                r.raise_for_status()
                try:
                    return r.json()
                except json.JSONDecodeError as exc:
                    raise AIAdapterInvalidResponseError(
                        "upstream returned invalid JSON"
                    ) from exc
            except httpx.TimeoutException as exc:
                last_msg = "upstream request timed out"
                logger.warning(
                    "openai call timed out (attempt %s/%s)",
                    attempts + 1,
                    self.cfg.max_retries + 1,
                )
                # Don't retry timeouts — they're unlikely to succeed on retry
                # within the same overall deadline.
                raise AIAdapterTimeoutError(last_msg) from exc
            except AIAdapterInvalidResponseError:
                raise
            except (AIAdapterAuthenticationError, AIAdapterRateLimitError,
                    AIAdapterBadRequestError, AIAdapterServerError):
                raise
            except httpx.HTTPStatusError as exc:
                last_msg = _map_http_status_error(exc)
                attempts += 1
                logger.warning(
                    "openai call failed (attempt %s/%s): %s",
                    attempts,
                    self.cfg.max_retries + 1,
                    last_msg,
                )
                if attempts > self.cfg.max_retries:
                    raise
            except httpx.TransportError as exc:
                last_msg = "upstream connection failed"
                attempts += 1
                logger.warning(
                    "openai transport error (attempt %s/%s): %s",
                    attempts,
                    self.cfg.max_retries + 1,
                    exc,
                )
                if attempts > self.cfg.max_retries:
                    raise AIAdapterServerError(last_msg) from exc
        raise AIAdapterServerError("upstream request failed")


# ---------------------------------------------------------------------------
# Error mapping — turns httpx / HTTP errors into sanitized adapter errors.
# ---------------------------------------------------------------------------
def _map_http_status_error(exc: httpx.HTTPStatusError) -> str:
    """Return a sanitized, caller-safe error message for an HTTP status error.

    Never includes the request URL, headers, raw response body, or stack trace.
    """
    code = exc.response.status_code
    if code == 401 or code == 403:
        raise AIAdapterAuthenticationError("authentication failed or insufficient permissions")
    if code == 429:
        raise AIAdapterRateLimitError("rate limit exceeded")
    if 400 <= code < 500:
        raise AIAdapterBadRequestError(f"invalid request ({code})")
    if code >= 500:
        raise AIAdapterServerError(f"upstream server error ({code})")
    return f"unexpected HTTP status {code}"
