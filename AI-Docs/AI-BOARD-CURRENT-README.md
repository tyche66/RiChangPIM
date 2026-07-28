# AI Board Current README

Last updated: 2026-07-26

This note describes the current AI Portal / Knowledge Gateway implementation and the gaps that should be handed to the next agent. It intentionally avoids secrets and does not include API keys.

## Entry Points

- AI Portal frontend: `http://localhost:888/`
- AI chat/debug page: `http://localhost:888/chat`
- Admin frontend: `http://localhost:888/admin/`
- Knowledge query API: `POST /api/v1/knowledge/query`
- Backend docs: `http://localhost:888/docs`

Nginx serves Portal from `portal/dist` at `/`, and Admin from `frontend/dist` at `/admin/`. The AI Portal has not displaced the admin UI.

## Current Chat Flow

Frontend file: `portal/src/views/Conversation.vue`

The chat page currently sends only the current user message to the unified read-only knowledge endpoint:

```json
{
  "message": "...",
  "capabilities": {
    "stream": true,
    "supports_actions": true
  }
}
```

The page first calls the SSE mode of `POST /api/v1/knowledge/query`. If no `answer_delta` is received, it falls back to the same endpoint with `stream: false`.

The UI renders:

- answer text
- product cards
- comparison table
- source cards
- pending action cards
- event stream metadata
- trace id

It does not maintain or resend a full conversation transcript. The backend stores a digest audit trail through `DigestConversationStore`, not the raw full conversation text.

## Backend Flow

API file: `backend/app/api/v1/knowledge.py`

Gateway file: `backend/app/knowledge/gateway.py`

Flow:

1. FastAPI validates `KnowledgeQueryRequest`.
2. `KnowledgeGateway.handle()` resolves the current user's permission pool.
3. Quota is checked.
4. `RuleBasedPlanner` creates a plan from the single message.
5. Gateway executes allowed read-only tools.
6. Optional hybrid retrieval runs for plans that enable retrieval.
7. A deterministic answer is generated from structured facts/products/sources.
8. If an AI model adapter is available and context exists, model answer generation may refine the answer.
9. Response includes facts, sources, products, pending actions, confidence, usage, and insufficient-source state.

Important modules:

- `backend/app/knowledge/planner.py`: rule-based intent and entity extraction
- `backend/app/knowledge/tools/product.py`: structured product search/get/compare tools
- `backend/app/knowledge/tools/supplier.py`: read-only supplier comparison
- `backend/app/knowledge/retrieval/hybrid.py`: hybrid retrieval
- `backend/app/knowledge/indexing/*`: document indexing and embedding cache
- `backend/app/adapters/openai.py`: OpenAI-compatible adapter, also used for OpenRouter
- `backend/app/knowledge/permission_pool.py`: role-based tool and field projection

## Current Capabilities

- Read-only product lookup through `product.search` and `product.get_many`.
- Product compare for explicitly identified products.
- Supplier compare for procurement-style read-only facts.
- Quality summary/list for missing price, unknown stock, draft data, missing images, and missing manuals.
- Knowledge retrieval over indexed product/knowledge chunks.
- Pending action creation for proposal draft requests, gated by confirmation before any write.
- Field projection by role; sensitive fields such as cost price are hidden from sales/viewer roles.
- OpenAI-compatible chat and embedding adapters.
- OpenRouter embedding smoke tested with `nvidia/nemotron-3-embed-1b:free` at 2048 dimensions.
- pgvector uses `halfvec(2048)` for HNSW compatibility.

## Known Weaknesses

The current chat experience is too brittle for natural user language.

Observed issue:

- Input: `找出最便宜的铭达办公桌`
- Previous behavior: `资料不足，无法形成可靠答案。`

Root causes:

- The planner was mostly keyword/rule based and originally split only on whitespace. Chinese natural sentences could become one long keyword, causing `product.search` to miss structured data.
- The pilot data contains `铭达` office desk products, but their `face_price` values are `99999`, which means `待核价`. Even when products are found, the system cannot honestly determine the cheapest item from placeholder prices.

Recent local fix:

- `QueryEntities` now has `price_sort`.
- `RuleBasedPlanner` extracts known Chinese business terms such as `铭达` and `办公桌`.
- `RuleBasedPlanner` recognizes `最便宜` / `最低价` / `价格最低` as ascending price intent.
- `product.search` accepts `keywords` and applies each keyword as an AND filter across product number, name, description, material, specification, category, brand, and supplier.
- `product.search` supports `sort_by=face_price` and `sort_order=asc`, pushing `99999` placeholder prices after real prices.
- Deterministic answer now says products were found but all prices are pending if every matched product has `face_price_display == 待核价`.

Validation for this fix:

```bash
cd /workspaces/RiChangPIM/backend
PYTHONPATH=. pytest tests/test_knowledge_gateway.py tests/test_ai_adapter.py::TestBuildAdapter
PYTHONPATH=. python -m compileall app/knowledge
```

Result: `17 passed`; compileall passed.

## Why The Chat Still Feels Weak

The current implementation is not a real multi-turn assistant. It is a single-turn read-only query console with a rule-based planner.

Main limitations:

- No full conversational memory is sent with each request.
- Follow-up questions like `那有没有小一点的` lack context unless the user repeats the entity.
- Chinese entity extraction is manually curated and incomplete.
- Ranking is basic and mostly structured-field based.
- Model generation only runs after tools/retrieval produce context; it does not currently rescue bad planning well.
- The deterministic fallback is generic when no facts/products/sources are found.
- Product data quality is a real blocker: many pilot products have price, cost, stock, and completeness values marked unknown or pending.

## Suggested Next Agent Work

Prioritize these in order:

1. Add a real query understanding layer before tool execution.
   Use the model adapter to extract intent, entities, filters, sort, and clarification needs into a strict schema, then validate against allowlisted tools and fields. Keep the rule-based planner as fallback.

2. Add bounded conversation context.
   Continue avoiding full raw transcript persistence if that is a requirement, but send short-lived in-memory or client-provided recent turns, or store sanitized summaries/digests that preserve entities and user constraints.

3. Improve no-result and partial-result answers.
   Distinguish: no product match, matched products with missing price, permission-filtered fields, retrieval unavailable, adapter unavailable, and data not indexed.

4. Add clarification behavior.
   For ambiguous requests, return a question and suggested filters instead of immediately saying sources are insufficient.

5. Improve product search semantics.
   Support category hierarchy filters, synonym dictionaries, brand/series extraction, dimensional constraints, price ranges, and availability filters.

6. Add evaluation cases for natural Chinese queries.
   Include examples like cheapest item, budget search, brand/category combinations, follow-up queries, missing-price explanations, and permission-specific output.

7. Improve Portal UX.
   The current page is a debug surface. It needs a real chat transcript, message history, loading states per phase, clearer source/product grouping, and explicit partial-data notices.

## Environment Notes

Embedding-related defaults currently target OpenRouter-compatible embeddings:

```env
AI_ADAPTER=openai
AI_API_URL=https://openrouter.ai/api/v1
AI_EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b:free
AI_EMBEDDING_DIM=2048
```

Do not commit local credential files. The local files `AI.env` and `embedding.env` are gitignored and excluded from the repo secret scan.

## Useful Checks

Backend quick checks:

```bash
cd /workspaces/RiChangPIM/backend
PYTHONPATH=. pytest tests/test_knowledge_gateway.py tests/test_ai_adapter.py tests/unit/test_embedding_cache.py
PYTHONPATH=. python -m compileall app
```

Portal check:

```bash
cd /workspaces/RiChangPIM/portal
npm run build
```

Release gate helpers:

```bash
cd /workspaces/RiChangPIM
bash scripts/secret_scan.sh
docker compose -f docker-compose.yml config --quiet
```

## Handoff Summary

The AI board is functional as a read-only product/knowledge query gateway, but it is still closer to a deterministic tool router than a natural chat assistant. The most valuable next step is not more UI polish; it is replacing or augmenting the rule-based planner with a schema-constrained model planner, plus bounded context handling and better partial-data responses.
