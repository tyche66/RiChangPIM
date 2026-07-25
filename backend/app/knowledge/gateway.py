from __future__ import annotations

import time
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.adapters.base import AIServiceAdapter
from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.events import sse_event
from app.knowledge.metrics import record_query
from app.knowledge.model_gateway import AdapterModelGateway
from app.knowledge.permission_pool import PermissionPoolResolver, get_permission_pool_resolver
from app.knowledge.planner import Planner, QueryPlan, get_planner
from app.knowledge.policy import require_ai_access
from app.knowledge.quota import QuotaCheckRequest, QuotaUsageRecord, get_quota_checker
from app.knowledge.retrieval.legacy_rag import LegacyRagRetriever
from app.knowledge.schemas import KnowledgeQueryRequest, KnowledgeQueryResponse, KnowledgeUsage
from app.knowledge.sessions import DigestConversationStore, digest_text
from app.knowledge.tools.base import ToolContext
from app.knowledge.tools.registry import ToolRegistry, default_tool_registry
from app.knowledge.tracing import new_trace_id

logger = logging.getLogger(__name__)


class KnowledgeGateway:
    def __init__(
        self,
        *,
        db,
        adapter: AIServiceAdapter,
        planner: Planner | None = None,
        registry: ToolRegistry | None = None,
        pool_resolver: PermissionPoolResolver | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.planner = planner or get_planner()
        self.registry = registry or default_tool_registry()
        self.pool_resolver = pool_resolver or get_permission_pool_resolver()

    async def handle(self, request: KnowledgeQueryRequest, current_user: dict, *, trace_id: str | None = None) -> KnowledgeQueryResponse:
        trace_id = trace_id or new_trace_id()
        start = time.perf_counter()
        session_id = request.session_id or str(uuid4())
        intent = "unknown"
        status = "ok"
        usage = KnowledgeUsage()
        tool_names: list[str] = []
        try:
            pool = self.pool_resolver.resolve(current_user)
            require_ai_access(pool, current_user)
            user_id = _user_uuid(current_user)
            quota = get_quota_checker()
            quota_result = await quota.check(QuotaCheckRequest(user_id=user_id, role_code=current_user.get("role_code"), trace_id=trace_id, estimated_input_tokens=len(request.message)))
            if not quota_result.allowed:
                raise KnowledgeGatewayError(KnowledgeErrorCode(quota_result.reason_code or "QUOTA_EXCEEDED"), quota_result.reason_message or "AI 限额不足", status_code=429)

            plan = self.planner.plan(request)
            intent = plan.intent.value
            if plan.intent.value == "unsupported":
                return KnowledgeQueryResponse(
                    trace_id=trace_id,
                    session_id=session_id,
                    answer="该请求涉及不支持或高风险能力，P1 只允许只读产品、知识和质量查询。",
                    confidence="insufficient",
                    insufficient_sources=True,
                    usage=KnowledgeUsage(degraded_reason=KnowledgeErrorCode.PLAN_INVALID.value),
                )

            tool_context = ToolContext(db=self.db, current_user=current_user, permission_pool=pool, trace_id=trace_id)
            tool_results = await self._run_tools(plan, request, tool_context)
            tool_names = list(tool_results.get("tool_names", []))
            facts = tool_results.get("facts", [])
            products = tool_results.get("products", [])
            sources = tool_results.get("sources", [])
            issues = tool_results.get("issues", [])

            if plan.retrieval.get("enabled"):
                retriever = LegacyRagRetriever(self.adapter, self.db)
                product_id = products[0].get("id") if products else None
                sources.extend(await retriever.retrieve(request.message, product_id=product_id, pool=pool, trace_id=trace_id))

            answer = _deterministic_answer(plan, facts, products, sources, issues)
            model_gateway = AdapterModelGateway(self.adapter)
            if model_gateway.available() and (facts or products or sources):
                try:
                    model = await model_gateway.generate_answer(
                        session_id=session_id,
                        message=request.message,
                        context={"intent": plan.intent.value, "facts": _model_safe(facts), "products": _model_safe(products), "sources": sources, "issues": _model_safe(issues)},
                        trace_id=trace_id,
                    )
                    if model.answer:
                        answer = model.answer
                    usage.provider = model.provider
                    usage.model = model.model
                    if model.usage:
                        usage.input_tokens = int(model.usage.get("input_tokens") or model.usage.get("prompt_tokens") or 0)
                        usage.output_tokens = int(model.usage.get("output_tokens") or model.usage.get("completion_tokens") or 0)
                except KnowledgeGatewayError as exc:
                    usage.degraded_reason = exc.code.value
            else:
                usage.degraded_reason = KnowledgeErrorCode.CAPABILITY_DISABLED.value

            response = KnowledgeQueryResponse(
                trace_id=trace_id,
                session_id=session_id,
                answer=answer,
                facts=facts,
                sources=sources,
                products=products,
                pending_actions=[],
                confidence=_confidence(facts, products, sources),
                insufficient_sources=not (facts or products or sources),
                usage=usage,
            )
            store = DigestConversationStore(self.db, user_id)
            try:
                await store.append_turn(
                    session_id,
                    digest_text(request.message),
                    digest_text(response.answer),
                    {"trace_id": trace_id, "source_ids": [s.get("source_id") for s in sources], "tool_names": tool_names, "model": usage.model, "usage": usage.model_dump(), "status": "completed"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("knowledge_audit_failed trace_id=%s error_type=%s", trace_id, type(exc).__name__)
            try:
                await quota.record(QuotaUsageRecord(trace_id=trace_id, user_id=user_id, role_code=current_user.get("role_code"), provider=usage.provider, model=usage.model, tokens=usage.input_tokens + usage.output_tokens, latency_ms=int((time.perf_counter() - start) * 1000), status="ok", timestamp=datetime.now(UTC)))
            except Exception as exc:  # noqa: BLE001
                logger.error("knowledge_quota_record_failed trace_id=%s error_type=%s", trace_id, type(exc).__name__)
            return response
        except KnowledgeGatewayError:
            status = "error"
            raise
        finally:
            record_query(trace_id=trace_id, intent=intent, status=status, latency_ms=int((time.perf_counter() - start) * 1000))

    async def stream(self, request: KnowledgeQueryRequest, current_user: dict, *, trace_id: str | None = None):
        trace_id = trace_id or new_trace_id()
        session_id = request.session_id or str(uuid4())
        yield sse_event("meta", {"schema_version": "1.0", "trace_id": trace_id, "session_id": session_id})
        try:
            body = request.model_copy(update={"session_id": session_id, "capabilities": request.capabilities.model_copy(update={"stream": False})})
            yield sse_event("phase", {"name": "planning", "label": "正在识别意图"})
            response = await self.handle(body, current_user, trace_id=trace_id)
            yield sse_event("phase", {"name": "answering", "label": "正在生成只读结果"})
            if response.answer:
                yield sse_event("answer_delta", {"text": response.answer})
            for source in response.sources:
                yield sse_event("source", source.model_dump(mode="json") if hasattr(source, "model_dump") else source)
            if response.products:
                yield sse_event("products", {"items": response.products, "reason_source_ids": [s.source_id for s in response.sources]})
            yield sse_event("done", {"status": "completed", "confidence": response.confidence, "usage": response.usage.model_dump(mode="json")})
        except KnowledgeGatewayError as exc:
            yield sse_event("error", {"code": exc.code.value, "retryable": exc.retryable, "message": exc.message})
            yield sse_event("done", {"status": "failed", "confidence": "insufficient", "usage": {}})

    async def _run_tools(self, plan: QueryPlan, request: KnowledgeQueryRequest, context: ToolContext) -> dict[str, Any]:
        acc: dict[str, Any] = {"facts": [], "products": [], "sources": [], "issues": [], "tool_names": []}
        for tool_name in plan.required_tools:
            params = _params_for_tool(tool_name, plan, request)
            result = await self.registry.execute(tool_name, params, context)
            acc["tool_names"].append(tool_name)
            for key in ("facts", "products", "sources", "issues"):
                acc[key].extend(result.get(key) or [])
        acc["products"] = _dedupe_by(acc["products"], "id")
        acc["sources"] = _dedupe_by(acc["sources"], "source_id")
        return acc


def _params_for_tool(tool_name: str, plan: QueryPlan, request: KnowledgeQueryRequest) -> dict[str, Any]:
    entities = plan.entities
    if tool_name == "product.search":
        return {"keyword": " ".join(entities.keywords) or request.message[:80], "product_nos": entities.product_nos, "product_ids": entities.product_ids, "filters": request.scope.filters, "limit": 20}
    if tool_name in {"product.get_many", "product.compare"}:
        product_nos = entities.product_nos[:5] if tool_name == "product.compare" else entities.product_nos
        product_ids = entities.product_ids[:5] if tool_name == "product.compare" else entities.product_ids
        return {"product_ids": product_ids, "product_nos": product_nos}
    if tool_name == "quality.list_issues":
        return {"issue_types": entities.status_terms, "limit": 50}
    return {}


def _deterministic_answer(plan: QueryPlan, facts: list[dict], products: list[dict], sources: list[dict], issues: list[dict]) -> str:
    if plan.intent.value.startswith("quality"):
        if issues:
            return f"查询到 {len(issues)} 个待治理问题，已按权限返回产品和问题列表。"
        return "已完成质量统计，具体结果见 facts。"
    if products:
        return f"找到 {len(products)} 个相关产品，价格与库存均来自当前 PIM 结构化事实。"
    if sources:
        return "已找到可引用资料来源，请核对来源后使用。"
    return "资料不足，无法形成可靠答案。"


def _confidence(facts: list, products: list, sources: list) -> str:
    if facts or products:
        return "high"
    if sources:
        return "medium"
    return "insufficient"


def _dedupe_by(items: list[dict], key: str) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        marker = item.get(key)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


MODEL_FORBIDDEN_FIELDS = {"cost_price", "supplier_id", "supplier_name", "margin", "profit", "quotation_item_cost", "proposal_cost_details"}


def _model_safe(value):
    if isinstance(value, list):
        return [_model_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_safe(item) for key, item in value.items() if key not in MODEL_FORBIDDEN_FIELDS}
    return value


def _user_uuid(current_user: dict) -> UUID | None:
    raw = current_user.get("sub") or current_user.get("user_id")
    try:
        return UUID(str(raw)) if raw else None
    except (TypeError, ValueError):
        return None
