"""关键词检索之后的那一次「自然语义筛选」。

背景（2026-10-28 本地验收）：用户输入「现代风格」返回空。

两侧原因都已定位，都是"差一次语义归一"：

* 规则层只认属性词典里的**别名**（``extract_alias_hits`` 最长匹配）。
  说法没在别名表里就没有硬条件，``product.search`` 拿不到约束 → 空。
* 模型规划器本来能做这件事，但 ``_planning_instructions`` 只把
  **option code** 丢给模型（``style: modern,new_chinese,...``），
  没有中文名和中文别名，模型无法把「现代风格」映射到 ``modern``。

本模块补第三层兜底：**召回 + 模型筛选**。当精确层（含语义归一后的
属性条件）仍然拿不到产品时，对宽松/文本召回出的候选池做一次模型筛选，
挑出真正贴合自然语言需求的若干产品；挑不出来就返回空，绝不硬凑
（「巴洛克式会议桌」这类确实没有的查询必须仍然为空）。

约束：

* 全部只读，不写库、不调用写工具、不外泄隐私字段（价格字段由调用方投影裁剪）。
* 模型只能从候选 ``product_no`` 里挑，编造的编号一律丢弃（fail-closed）。
* 适配器不可用/超时/解析失败 → 返回空结果，绝不让整次查询失败。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.knowledge.attributes import AttributeDictionary

logger = logging.getLogger(__name__)

# 候选池上限：一次筛选送的卡片过多既慢又容易让模型敷衍。
MAX_SCREEN_CANDIDATES = 40
# 筛选结果上限：与 product.search 的默认 limit 对齐。
MAX_SCREENED_PRODUCTS = 20
_DESCRIPTION_LIMIT = 80


@dataclass(frozen=True)
class SemanticResolution:
    """语义归一结果：模型从受治理词典里选出的属性条件。"""

    facets: tuple[Any, ...] = ()
    interpretation: str = ""
    # 是否真的问过模型（受众包括"问了但归一不出"的情况，用于把解释透传给前端）
    consulted: bool = False

    @property
    def used(self) -> bool:
        return bool(self.facets)


@dataclass(frozen=True)
class ScreenedProduct:
    """模型筛出的一个产品及其贴合理由。"""

    product_no: str
    reason: str


@dataclass(frozen=True)
class ScreeningResult:
    products: tuple[ScreenedProduct, ...] = ()
    interpretation: str = ""

    @property
    def used(self) -> bool:
        """是否真的筛出了产品（无候选/模型拒绝时恒为 False）。"""
        return bool(self.products)


@dataclass(frozen=True)
class _CandidateRow:
    """喂给模型的候选投影：只留判断贴合度必需的字段，剔除成本/供应商等隐私。"""

    product_no: str
    product_name: str
    category_name: str
    brand_name: str
    series: tuple[str, ...]
    attributes: dict[str, list[str]]
    colors: tuple[str, ...]
    material: str
    description: str


def _candidate_rows(candidates: list[dict[str, Any]]) -> list[_CandidateRow]:
    rows: list[_CandidateRow] = []
    for card in candidates[:MAX_SCREEN_CANDIDATES]:
        product_no = str(card.get("product_no") or "").strip()
        if not product_no:
            continue
        attributes = card.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        clean_attributes: dict[str, list[str]] = {}
        for key, value in attributes.items():
            if isinstance(value, list):
                clean_attributes[str(key)] = [str(v) for v in value]
        rows.append(
            _CandidateRow(
                product_no=product_no,
                product_name=str(card.get("product_name") or ""),
                category_name=str(card.get("category_name") or ""),
                brand_name=str(card.get("brand_name") or ""),
                series=tuple(str(t) for t in (card.get("tags") or []) if isinstance(t, str)),
                attributes=clean_attributes,
                colors=tuple(str(c) for c in (card.get("colors") or [])),
                material=str(card.get("material") or ""),
                description=str(card.get("description") or "")[:_DESCRIPTION_LIMIT],
            )
        )
    return rows


def _rows_payload(rows: list[_CandidateRow]) -> str:
    payload = [
        {
            "product_no": row.product_no,
            "product_name": row.product_name,
            "category_name": row.category_name,
            "brand_name": row.brand_name,
            "series": list(row.series),
            "attributes": row.attributes,
            "colors": list(row.colors),
            "material": row.material,
            "description": row.description,
        }
        for row in rows
    ]
    return json.dumps(payload, ensure_ascii=False)


_SCREEN_INSTRUCTIONS = (
    "你是 RiChangPIM 的只读选品筛选器。用户给出一句自然语言需求，"
    "下面是候选产品的裁剪后事实（已剔除价格/供应商等隐私字段）。\n\n"
    "任务：只挑出**真正贴合**这条自然语言需求的产品，"
    f"按贴合度从高到低排序，最多 {MAX_SCREENED_PRODUCTS} 个。\n\n"
    "规则：\n"
    "1. 逐条对照候选产品的类目/系列/属性/材质/颜色/描述判断，"
    "不要因为编号相邻或名称相似就选。\n"
    "2. **任何一个候选都不贴合时，selected 必须返回空数组**。"
    "宁可空，也不要硬凑；用户要的东西不存在时，空结果才是诚实答案。\n"
    "3. 用户用词与产品属性不一致时按语义判断"
    "（例如「年轻时尚不老气」对应现代/简约风格的产品），"
    "但不得把明显不符的产品选进来。\n"
    "4. reason 用一句中文写清贴合点；"
    "interpretation 用一句中文写清你怎么理解这条需求。\n"
    "5. 只输出合法 JSON，不要任何解释性文字：\n"
    '{"selected":[{"product_no":"候选里的编号","reason":"贴合点"}],'
    '"interpretation":"一句中文"}'
)


def _parse_json_object(answer: str | None) -> dict[str, Any]:
    """容错解析模型输出：兼容 ```json 围栏与前后杂讯。"""
    text = (answer or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


async def screen_products(
    message: str,
    candidates: list[dict[str, Any]],
    *,
    adapter,
    session_id: str,
    timeout: float | None = None,
) -> ScreeningResult:
    """对候选池做一次自然语言语义筛选。

    ``candidates`` 是 product 卡片（``_product_card`` 的输出）。
    返回按贴合度排序的筛选结果；无候选/适配器不可用/解析失败都返回空。
    """
    if not candidates or adapter is None or isinstance(adapter, NoneAdapter):
        return ScreeningResult()
    rows = _candidate_rows(candidates)
    if not rows:
        return ScreeningResult()

    try:
        response = await asyncio.wait_for(
            adapter.chat(
                session_id=session_id,
                message=(
                    "请对下列候选产品做语义筛选。用户需求："
                    f"{message}\n候选产品事实：{_rows_payload(rows)}"
                ),
                history=[],
                system=_SCREEN_INSTRUCTIONS,
                temperature=0,
            ),
            timeout=timeout if timeout is not None else settings.AI_TOOL_PLANNING_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - 语义筛选失败不能让整次查询失败
        logger.warning("semantic_screen_failed error_type=%s", type(exc).__name__)
        return ScreeningResult()

    payload = _parse_json_object(response.get("answer"))
    allowed = {row.product_no for row in rows}
    selected: list[ScreenedProduct] = []
    raw = payload.get("selected")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            product_no = str(item.get("product_no") or "").strip()
            if product_no not in allowed or product_no in {p.product_no for p in selected}:
                continue
            selected.append(
                ScreenedProduct(
                    product_no=product_no,
                    reason=str(item.get("reason") or "")[:200],
                )
            )
            if len(selected) >= MAX_SCREENED_PRODUCTS:
                break
    interpretation = str(payload.get("interpretation") or "")[:200]
    return ScreeningResult(
        products=tuple(selected),
        interpretation=interpretation,
    )


def attribute_context_lines(dictionary: AttributeDictionary) -> list[str]:
    """把词典渲染成模型可读的属性说明：**code + 中文名 + 全部别名**。

    只给 code 模型就无法把「现代风格」映射到 ``modern``（2026-10-28 实测），
    所以这里必须带 label 与别名。
    """
    options: dict[str, dict[str, list[str]]] = {}
    for entry in dictionary.aliases:
        options.setdefault(entry.attribute_code, {}).setdefault(entry.option_code, []).append(
            entry.alias
        )
    lines: list[str] = []
    for code, view in sorted(dictionary.definitions.items()):
        if not view.searchable or view.data_type != "option":
            continue
        by_option = options.get(code)
        if not by_option:
            continue
        parts = [
            f"{option_code}={'|'.join(dict.fromkeys(aliases))}"
            for option_code, aliases in sorted(by_option.items())
        ]
        lines.append(f"{code}({view.name}) 取值: {'; '.join(parts)}")
    return lines


_RESOLVE_INSTRUCTIONS = (
    "你是 RiChangPIM 的只读属性归一器。规则层（词典别名匹配）没能把用户这句"
    "自然语言解析成属性条件，现在由你按语义把它归一到**已定义**的属性取值上。\n\n"
    "规则：\n"
    "1. 只能使用下面列出的属性 code 与取值 code，不得编造；无法归一的词不要硬塞。\n"
    "2. 同一属性的多个取值表示「或」；不同属性之间是「且」。\n"
    "3. 多字少字、口语化、带程度词都不改变取值本身："
    "「现代风格」「偏现代风格」「现代简约风格」都归一到该属性的现代取值；"
    "「年轻时尚不老气」这类描述同样按语义落到最贴近的取值。\n"
    "4. 用户明确否定（不要/排除/除了）的属性不要放入 facets。\n"
    "5. 完全无法归一时返回空 facets，不要编造。\n"
    "6. interpretation 用一句中文写清「用户这句话对应哪些属性取值」。\n"
    "7. 只输出合法 JSON，不要任何解释性文字：\n"
    '{"facets":[{"attribute_code":"属性code","values":["取值code"]}],'
    '"interpretation":"一句中文"}'
)


def _validate_facets(payload: dict[str, Any], dictionary) -> list:
    """按词典校验模型给的 facets：编造的属性/取值一律丢弃（fail-closed）。"""
    from app.knowledge.attributes import HardFacet  # noqa: PLC0415

    raw = payload.get("facets")
    if not isinstance(raw, list):
        return []
    facets: list = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("attribute_code") or "").strip()
        values = item.get("values") if isinstance(item.get("values"), list) else []
        if not code or code in seen or code not in dictionary.definitions:
            continue
        view = dictionary.definitions[code]
        if not view.searchable or view.data_type != "option":
            continue
        allowed = dictionary.option_codes(code)
        kept = list(
            dict.fromkeys(
                str(v).strip()
                for v in values
                if str(v).strip() and str(v).strip() in allowed
            )
        )
        if not kept:
            continue
        seen.add(code)
        facets.append(
            HardFacet(
                attribute_code=code,
                values=kept,
                source="model",
                match_mode="any",
                confidence=1.0,
            )
        )
    return facets


async def resolve_facets(
    message: str,
    dictionary,
    *,
    adapter,
    session_id: str,
    timeout: float | None = None,
) -> SemanticResolution:
    """关键词/规则层无果后，让模型把自然语言归一成受治理属性取值。

    与 :func:`screen_products` 的分工：这一步产出的是**硬条件**，交给既有精确
    SQL，拿到的是该条件下的完整结果集；筛选项只用来兜底。
    """
    if adapter is None or isinstance(adapter, NoneAdapter):
        return SemanticResolution()
    if not message or not message.strip():
        return SemanticResolution()
    if not dictionary.aliases:
        return SemanticResolution()
    lines = attribute_context_lines(dictionary)
    if not lines:
        return SemanticResolution()

    try:
        response = await asyncio.wait_for(
            adapter.chat(
                session_id=session_id,
                message=(
                    "请把下面这句用户需求归一成已定义属性取值：\n"
                    f"{message}\n已定义属性：\n" + "\n".join(lines)
                ),
                history=[],
                system=_RESOLVE_INSTRUCTIONS,
                temperature=0,
            ),
            timeout=timeout if timeout is not None else settings.AI_TOOL_PLANNING_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - 语义归一失败不能让整次查询失败
        logger.warning("semantic_resolve_failed error_type=%s", type(exc).__name__)
        return SemanticResolution()

    payload = _parse_json_object(response.get("answer"))
    facets = _validate_facets(payload, dictionary)
    interpretation = str(payload.get("interpretation") or "")[:200]
    return SemanticResolution(
        facets=tuple(facets),
        interpretation=interpretation,
        consulted=True,
    )
