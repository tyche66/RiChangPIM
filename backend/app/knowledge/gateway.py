from __future__ import annotations

import hashlib
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.adapters.base import AIServiceAdapter
from app.core.config import settings
from app.knowledge.citations import CitationValidator
from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.events import sse_event
from app.knowledge.metrics import record_query
from app.knowledge.model_gateway import AdapterModelGateway
from app.knowledge.model_planner import ModelToolPlanner
from app.knowledge.permission_pool import PermissionPoolResolver, get_permission_pool_resolver
from app.knowledge.planner import Planner, QueryPlan, get_planner
from app.knowledge.policy import require_ai_access
from app.knowledge.quota import QuotaCheckRequest, QuotaUsageRecord, get_quota_checker
from app.knowledge.retrieval.hybrid import HybridRetriever
from app.knowledge.schemas import KnowledgeQueryRequest, KnowledgeQueryResponse, KnowledgeUsage
from app.knowledge.sessions import DigestConversationStore, digest_text
from app.knowledge.tools.base import ToolContext
from app.knowledge.tools.registry import ToolRegistry, default_tool_registry
from app.knowledge.tracing import new_trace_id
from app.observability import metrics as obs_metrics
from app.schemas.pending_action import PendingActionCreate
from app.services.pending_actions import action_to_dict, create_pending_action

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
        citation_validator: CitationValidator | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.planner = planner or get_planner()
        self.registry = registry or default_tool_registry()
        self.pool_resolver = pool_resolver or get_permission_pool_resolver()
        self.citation_validator = citation_validator or CitationValidator()

    async def handle(
        self, request: KnowledgeQueryRequest, current_user: dict, *, trace_id: str | None = None
    ) -> KnowledgeQueryResponse:
        trace_id = trace_id or new_trace_id()
        start = time.perf_counter()
        session_id = request.session_id or str(uuid4())
        intent = "unknown"
        status = "ok"
        usage = KnowledgeUsage()
        tool_names: list[str] = []
        retrieval_events: list[dict[str, Any]] = []
        try:
            pool = self.pool_resolver.resolve(current_user)
            require_ai_access(pool, current_user)
            user_id = _user_uuid(current_user)
            quota = get_quota_checker()
            quota_result = await quota.check(
                QuotaCheckRequest(
                    user_id=user_id,
                    role_code=current_user.get("role_code"),
                    trace_id=trace_id,
                    estimated_input_tokens=len(request.message),
                )
            )
            if not quota_result.allowed:
                raise KnowledgeGatewayError(
                    KnowledgeErrorCode(quota_result.reason_code or "QUOTA_EXCEEDED"),
                    quota_result.reason_message or "AI 限额不足",
                    status_code=429,
                )

            plan = await self._plan(
                request,
                current_user=current_user,
                pool=pool,
                session_id=session_id,
            )
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

            tool_context = ToolContext(
                db=self.db, current_user=current_user, permission_pool=pool, trace_id=trace_id
            )
            tool_results = await self._run_tools(plan, request, tool_context)
            tool_names = list(tool_results.get("tool_names", []))
            facts = tool_results.get("facts", [])
            products = tool_results.get("products", [])
            sources = tool_results.get("sources", [])
            issues = tool_results.get("issues", [])
            suppliers = tool_results.get("suppliers", [])

            if plan.retrieval.get("enabled"):
                retriever = HybridRetriever(self.adapter, self.db)
                product_id = products[0].get("id") if products else None
                retrieval_start = time.perf_counter()
                retrieved, retrieval_events = await retriever.retrieve(
                    request.message,
                    product_id=product_id,
                    pool=pool,
                    current_user=current_user,
                    trace_id=trace_id,
                )
                sources.extend(retrieved)
                obs_metrics.observe_retrieval(
                    "hybrid",
                    time.perf_counter() - retrieval_start,
                    len(retrieved),
                )

            pending_actions = await self._build_pending_actions(
                plan, request, current_user, user_id, products, sources, usage
            )
            answer = _deterministic_answer(
                plan, facts, products, sources, issues, suppliers, pending_actions
            )
            self.citation_validator.validate_sources(sources)
            model_gateway = AdapterModelGateway(self.adapter)
            if (
                model_gateway.available()
                and (facts or products or sources)
                and plan.entities.price_sort not in {"asc", "desc"}
                and plan.entities.specification_sort not in {"asc", "desc"}
            ):
                try:
                    model = await model_gateway.generate_answer(
                        session_id=session_id,
                        message=request.message,
                        context={
                            "intent": plan.intent.value,
                            "facts": _model_safe(facts),
                            "products": _model_safe(products),
                            "sources": sources,
                            "issues": _model_safe(issues),
                        },
                        trace_id=trace_id,
                    )
                    if model.answer:
                        answer = model.answer
                    self.citation_validator.validate_answer(answer, sources)
                    usage.provider = model.provider
                    usage.model = model.model
                    if model.usage:
                        usage.input_tokens = int(
                            model.usage.get("input_tokens") or model.usage.get("prompt_tokens") or 0
                        )
                        usage.output_tokens = int(
                            model.usage.get("output_tokens")
                            or model.usage.get("completion_tokens")
                            or 0
                        )
                except KnowledgeGatewayError as exc:
                    usage.degraded_reason = exc.code.value
            elif not model_gateway.available():
                usage.degraded_reason = KnowledgeErrorCode.CAPABILITY_DISABLED.value

            response = KnowledgeQueryResponse(
                trace_id=trace_id,
                session_id=session_id,
                answer=answer,
                facts=facts,
                sources=sources,
                products=products,
                pending_actions=pending_actions,
                confidence=_confidence(facts, products, sources),
                insufficient_sources=not (facts or products or sources),
                usage=usage,
            )
            store = DigestConversationStore(self.db, user_id)
            obs_metrics.observe_ai_query(
                intent,
                status,
                time.perf_counter() - start,
            )
            obs_metrics.set_citation_count("ok", len(sources))
            try:
                await store.append_turn(
                    session_id,
                    digest_text(request.message),
                    digest_text(response.answer),
                    {
                        "trace_id": trace_id,
                        "source_ids": [s.get("source_id") for s in sources],
                        "tool_names": tool_names,
                        "pending_action_ids": [a.get("id") for a in pending_actions],
                        "model": usage.model,
                        "usage": usage.model_dump(),
                        "status": "completed",
                        "retrieval_events": retrieval_events,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "knowledge_audit_failed trace_id=%s error_type=%s", trace_id, type(exc).__name__
                )
            try:
                await quota.record(
                    QuotaUsageRecord(
                        trace_id=trace_id,
                        user_id=user_id,
                        role_code=current_user.get("role_code"),
                        provider=usage.provider,
                        model=usage.model,
                        tokens=usage.input_tokens + usage.output_tokens,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        status="ok",
                        timestamp=datetime.now(UTC),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "knowledge_quota_record_failed trace_id=%s error_type=%s",
                    trace_id,
                    type(exc).__name__,
                )
            return response
        except KnowledgeGatewayError:
            status = "error"
            raise
        finally:
            record_query(
                trace_id=trace_id,
                intent=intent,
                status=status,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )

    async def stream(
        self, request: KnowledgeQueryRequest, current_user: dict, *, trace_id: str | None = None
    ):
        trace_id = trace_id or new_trace_id()
        session_id = request.session_id or str(uuid4())
        yield sse_event(
            "meta", {"schema_version": "1.0", "trace_id": trace_id, "session_id": session_id}
        )
        try:
            body = request.model_copy(
                update={
                    "session_id": session_id,
                    "capabilities": request.capabilities.model_copy(update={"stream": False}),
                }
            )
            yield sse_event("phase", {"name": "planning", "label": "正在识别意图"})
            response = await self.handle(body, current_user, trace_id=trace_id)
            yield sse_event("phase", {"name": "answering", "label": "正在生成只读结果"})
            if response.answer:
                yield sse_event("answer_delta", {"text": response.answer})
            for source in response.sources:
                yield sse_event(
                    "source",
                    source.model_dump(mode="json") if hasattr(source, "model_dump") else source,
                )
            if response.products:
                yield sse_event(
                    "products",
                    {
                        "items": response.products,
                        "reason_source_ids": [s.source_id for s in response.sources],
                    },
                )
            for action in response.pending_actions:
                yield sse_event("pending_action", action)
            yield sse_event(
                "done",
                {
                    "status": "completed",
                    "confidence": response.confidence,
                    "usage": response.usage.model_dump(mode="json"),
                },
            )
        except KnowledgeGatewayError as exc:
            yield sse_event(
                "error",
                {"code": exc.code.value, "retryable": exc.retryable, "message": exc.message},
            )
            yield sse_event("done", {"status": "failed", "confidence": "insufficient", "usage": {}})

    async def _run_tools(
        self, plan: QueryPlan, request: KnowledgeQueryRequest, context: ToolContext
    ) -> dict[str, Any]:
        acc: dict[str, Any] = {
            "facts": [],
            "products": [],
            "sources": [],
            "issues": [],
            "suppliers": [],
            "tool_names": [],
        }
        for tool_name in plan.required_tools:
            params = plan.tool_params.get(tool_name) or _params_for_tool(tool_name, plan, request)
            result = await self.registry.execute(tool_name, params, context)
            acc["tool_names"].append(tool_name)
            for key in ("facts", "products", "sources", "issues", "suppliers"):
                acc[key].extend(result.get(key) or [])
        acc["products"] = _dedupe_by(acc["products"], "id")
        acc["sources"] = _dedupe_by(acc["sources"], "source_id")
        return acc

    async def _plan(self, request, *, current_user: dict, pool, session_id: str) -> QueryPlan:
        planner = ModelToolPlanner(self.planner, self.registry)
        return await planner.plan(
            request,
            db=self.db,
            adapter=self.adapter,
            current_user=current_user,
            permission_pool=pool,
            session_id=session_id,
        )

    async def _build_pending_actions(
        self,
        plan: QueryPlan,
        request: KnowledgeQueryRequest,
        current_user: dict,
        user_id: UUID | None,
        products: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        usage: KnowledgeUsage,
    ) -> list[dict[str, Any]]:
        if not settings.AI_PENDING_ACTIONS_ENABLED:
            return []
        if (
            plan.intent.value != "proposal_draft"
            or not request.capabilities.supports_actions
            or not user_id
        ):
            return []
        perms = set(current_user.get("perms") or [])
        if current_user.get("role_code") != "admin" and "ai:pending_action" not in perms:
            return []
        active_products = [p for p in products if p.get("status") == "active"]
        if not active_products:
            return []
        source_ids = [s.get("source_id") for s in sources if s.get("source_id")]
        items = [
            {"product_id": p["id"], "quantity": 1, "remark": "AI 建议加入方案草稿"}
            for p in active_products[:10]
        ]
        payload = {
            "proposal_name": _proposal_name(request.message),
            "customer_name": None,
            "summary": "AI 根据当前产品事实生成方案草稿，确认后才会写入方案。",
            "items": items,
        }
        idem = _action_idempotency_key(
            user_id, request.session_id, request.message, [p["id"] for p in active_products]
        )
        action = await create_pending_action(
            self.db,
            PendingActionCreate(
                action_type="proposal.create_draft",
                idempotency_key=idem,
                target_type="proposal",
                payload=payload,
                source_ids=source_ids,
                model_provider=usage.provider,
                model_name=usage.model,
                reason="proposal_draft_request",
            ),
            user_id,
        )
        return [action_to_dict(action)]


def _params_for_tool(
    tool_name: str, plan: QueryPlan, request: KnowledgeQueryRequest
) -> dict[str, Any]:
    entities = plan.entities
    if tool_name == "product.search":
        return {
            "keyword": None if entities.keywords else request.message[:80],
            "keywords": entities.keywords,
            "product_nos": entities.product_nos,
            "product_ids": entities.product_ids,
            "filters": request.scope.filters,
            "sort_by": (
                "face_price"
                if entities.price_sort
                else "specification_length"
                if entities.specification_sort
                else None
            ),
            "sort_order": entities.price_sort or entities.specification_sort,
            "limit": 20,
        }
    if tool_name in {"product.get_many", "product.compare"}:
        product_nos = (
            entities.product_nos[:5] if tool_name == "product.compare" else entities.product_nos
        )
        product_ids = (
            entities.product_ids[:5] if tool_name == "product.compare" else entities.product_ids
        )
        return {"product_ids": product_ids, "product_nos": product_nos}
    if tool_name == "quality.list_issues":
        return {"issue_types": entities.status_terms, "limit": 50}
    if tool_name == "supplier.compare":
        return {"product_ids": entities.product_ids, "product_nos": entities.product_nos}
    return {}


def _deterministic_answer(
    plan: QueryPlan,
    facts: list[dict],
    products: list[dict],
    sources: list[dict],
    issues: list[dict],
    suppliers: list[dict],
    pending_actions: list[dict],
) -> str:
    if plan.intent.value == "proposal_draft":
        if pending_actions:
            return "已生成方案草稿待确认动作。确认前不会写入方案或创建分享。"
        return "未找到可加入方案草稿的已激活产品，未创建待确认动作。"
    if plan.intent.value == "procurement_compare":
        if suppliers:
            return "已返回供应商当前结构化事实；缺失的交期、质量和实时库存均标记为 unknown。"
        return "未找到可比较的供应商结构化事实。"
    if plan.intent.value.startswith("quality"):
        if issues:
            return f"查询到 {len(issues)} 个待治理问题，已按权限返回产品和问题列表。"
        return "已完成质量统计，具体结果见 facts。"
    if products:
        if plan.entities.specification_sort:
            selected = products[0]
            length = selected.get("specification_length_mm")
            length_label = "最长" if plan.entities.specification_sort == "desc" else "最短"
            if length is not None:
                product_name = selected.get("product_name") or selected.get("product_no")
                return f"当前{length_label}的产品为 {product_name}，长度 {length:g} mm。"
            return f"找到 {len(products)} 个相关产品，但规格未提供可比较的长度。"
        all_prices_pending = all(
            product.get("face_price_display") == "待核价" for product in products
        )
        if plan.entities.price_sort and all_prices_pending:
            price_label = "最便宜" if plan.entities.price_sort == "asc" else "最贵"
            return (
                f"找到 {len(products)} 个相关产品，但面价均为待核价，"
                f"无法可靠判断{price_label}的一款。"
            )
        if plan.entities.price_sort:
            price_label = "最低" if plan.entities.price_sort == "asc" else "最高"
            selected = products[0]
            product_name = selected.get("product_name") or selected.get("product_no")
            return (
                f"当前{price_label}面价为 {product_name}，"
                f"面价 {selected.get('face_price_display')}。"
            )
        return f"找到 {len(products)} 个相关产品，价格与库存均来自当前 PIM 结构化事实。"
    if sources:
        return "已找到可引用资料来源，请核对来源后使用。"
    return "资料不足，无法形成可靠答案。"


def _proposal_name(message: str) -> str:
    cleaned = " ".join(message.strip().split())[:40]
    return f"AI 方案草稿 - {cleaned or '未命名'}"


def _action_idempotency_key(
    user_id: UUID, session_id: str | None, message: str, product_ids: list[str]
) -> str:
    raw = "|".join([str(user_id), session_id or "", message, ",".join(sorted(product_ids))])
    return "proposal-draft-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


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


MODEL_FORBIDDEN_FIELDS = {
    "cost_price",
    "supplier_id",
    "supplier_name",
    "margin",
    "profit",
    "quotation_item_cost",
    "proposal_cost_details",
    "cover_image_url",
}


def _model_safe(value):
    if isinstance(value, list):
        return [_model_safe(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _model_safe(item)
            for key, item in value.items()
            if key not in MODEL_FORBIDDEN_FIELDS
        }
    return value


def _user_uuid(current_user: dict) -> UUID | None:
    raw = current_user.get("sub") or current_user.get("user_id")
    try:
        return UUID(str(raw)) if raw else None
    except (TypeError, ValueError):
        return None
