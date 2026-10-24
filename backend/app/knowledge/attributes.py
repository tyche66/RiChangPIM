"""受治理属性词典（Track A）。

取代原先写死在 ``facets.py`` 里的业务词表。词典来自数据库
（``catalog_attribute_*``），带缓存；解析器不再认识任何硬编码的
"弧形/会议桌"特例。

核心能力：

* 最长词匹配，支持中文无空格与夹杂空格/标点的表达；
* 同义词归一到 ``(attribute_code, option_code)``；
* 不同属性之间 AND，同一属性已确认同义词之间 OR；
* 否定表达（"不要黑色"/"排除圆形"）进入 exclude_values；
* 无法归一的残余词进入 unknown_terms，不静默丢弃。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
# 归一化时统一去掉的分隔符（不影响"弧形 会议桌"→"弧形会议桌"这类无空格表达）
_STRIP_CHARS = " \t\r\n，。！？、；：:,.;!?~～-_—－/|()（）[]【】\"'“”‘’"


def normalize_text(value: str) -> str:
    """NFKC + 去空白 + 去常见标点，用于中文别名匹配。"""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = _WS_RE.sub("", text)
    for ch in _STRIP_CHARS:
        text = text.replace(ch, "")
    return text.casefold()


def normalize_text_with_map(value: str) -> tuple[str, list[int]]:
    """同 :func:`normalize_text`，同时返回"归一化下标 -> 原文下标"映射。

    归一化会删掉空白与标点、还会做 casefold（个别字符会变长），
    两个字符串的下标并不一一对应。别名命中位置落在归一化串上，
    而残余文本要从**原文**里切，因此必须拿到这张映射表，
    否则带空格/标点/中英混排的查询会被错误截断。
    """
    if not value:
        return "", []
    text = unicodedata.normalize("NFKC", value)
    chars: list[str] = []
    mapping: list[int] = []
    for index, char in enumerate(text):
        if _WS_RE.fullmatch(char) or char in _STRIP_CHARS:
            continue
        for piece in char.casefold():
            chars.append(piece)
            mapping.append(index)
    return "".join(chars), mapping


# ---------------------------------------------------------------------------
# 词典结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AliasEntry:
    """一条可匹配的别名。"""

    attribute_code: str
    option_code: str
    alias: str
    normalized: str
    length: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "length", len(self.normalized))


@dataclass
class AttributeDefinitionView:
    code: str
    name: str
    data_type: str
    multi_value: bool
    searchable: bool
    hard_filterable: bool


@dataclass
class AttributeDictionary:
    """内存中的属性词典快照（可缓存）。"""

    definitions: dict[str, AttributeDefinitionView]
    aliases: list[AliasEntry]
    # code -> 定义主键；用于把 ORM 上的 attribute_id 反查回 code
    definition_ids: dict[str, object] = field(default_factory=dict)
    definition_views_by_id: dict[object, AttributeDefinitionView] = field(default_factory=dict)

    @property
    def searchable_codes(self) -> set[str]:
        return {code for code, d in self.definitions.items() if d.searchable}

    def sorted_aliases(self) -> list[AliasEntry]:
        """最长词优先，确保"圆弧型"先于"圆弧"先于"弧"命中。"""
        return sorted(self.aliases, key=lambda a: a.length, reverse=True)

    def option_codes(self, attribute_code: str) -> set[str]:
        return {a.option_code for a in self.aliases if a.attribute_code == attribute_code}

    def view_by_id(self, attribute_id) -> AttributeDefinitionView | None:
        return self.definition_views_by_id.get(attribute_id)


EMPTY_DICTIONARY = AttributeDictionary(definitions={}, aliases=[])


# ---------------------------------------------------------------------------
# 硬条件模型（通用；不再有写死的 category/shape 字段）
# ---------------------------------------------------------------------------


class HardFacet(BaseModel):
    """一个明确的属性硬约束。

    语义：
    * 不同 ``attribute_code`` 的硬条件之间 AND；
    * 同一 ``attribute_code`` 内，``match_mode='any'`` 时已确认同义词 OR；
    * ``match_mode='all'`` 时同一属性多个取值全部满足；
    * 属性缺失（产品没有任何该属性取值）不算命中。
    """

    model_config = ConfigDict(extra="forbid")

    attribute_code: str
    values: list[str] = Field(default_factory=list)
    required: bool = True
    match_mode: str = "any"  # any | all
    source: str = "rule"  # rule | model
    confidence: float = 1.0


class NumericFilter(BaseModel):
    """价格 / 长度 / 宽度 / 高度 / 人数等数值区间。"""

    model_config = ConfigDict(extra="forbid")

    attribute_code: str
    min_value: float | None = None
    max_value: float | None = None
    unit: str | None = None
    source: str = "rule"
    confidence: float = 1.0

    def is_empty(self) -> bool:
        return self.min_value is None and self.max_value is None


class ProductQuery(BaseModel):
    """查询理解契约（替代旧的 QueryEntities/ProductFacets 硬编码结构）。"""

    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(default_factory=list)
    product_nos: list[str] = Field(default_factory=list)
    status_terms: list[str] = Field(default_factory=list)

    hard_facets: list[HardFacet] = Field(default_factory=list)
    numeric_filters: list[NumericFilter] = Field(default_factory=list)
    exclude_values: list[HardFacet] = Field(default_factory=list)

    soft_terms: list[str] = Field(default_factory=list)
    unknown_terms: list[str] = Field(default_factory=list)

    sort: str | None = None
    sort_order: str | None = None
    clarification_needed: str | None = None

    # attribute_code -> option_code -> 该 option 的中文别名（仅内存使用，不参与序列化）
    alias_labels: dict[str, dict[str, list[str]]] = Field(
        default_factory=dict, exclude=True, repr=False
    )

    # ------------------------------------------------------------------
    def has_constraints(self) -> bool:
        return bool(self.hard_facets or self.numeric_filters or self.exclude_values)

    def facet_codes(self) -> list[str]:
        return [f.attribute_code for f in self.hard_facets]

    def required_codes(self) -> list[str]:
        return [f.attribute_code for f in self.hard_facets if f.required]

    def values_for(self, attribute_code: str) -> list[str]:
        out: list[str] = []
        for facet in self.hard_facets:
            if facet.attribute_code == attribute_code:
                out.extend(facet.values)
        return list(dict.fromkeys(out))

    def merge(self, other: ProductQuery) -> None:
        """通用维度合并：规则结果优先，模型只能补充，不能覆盖/删除/放宽。"""
        rule_codes = set(self.facet_codes()) | {f.attribute_code for f in self.exclude_values}
        for facet in other.hard_facets:
            if facet.attribute_code not in rule_codes:
                self.hard_facets.append(facet)
        for facet in other.exclude_values:
            key = facet.attribute_code
            if key not in {f.attribute_code for f in self.exclude_values}:
                self.exclude_values.append(facet)

        rule_numeric = {f.attribute_code for f in self.numeric_filters}
        for nf in other.numeric_filters:
            if nf.attribute_code not in rule_numeric and not nf.is_empty():
                self.numeric_filters.append(nf)

        self.soft_terms = list(
            dict.fromkeys(self.soft_terms + [t for t in other.soft_terms if t])
        )
        self.unknown_terms = list(
            dict.fromkeys(self.unknown_terms + [t for t in other.unknown_terms if t])
        )
        self.product_nos = list(dict.fromkeys(self.product_nos + other.product_nos))
        self.product_ids = list(dict.fromkeys(self.product_ids + other.product_ids))
        self.status_terms = list(dict.fromkeys(self.status_terms + other.status_terms))
        if self.sort is None:
            self.sort = other.sort
        if self.sort_order is None:
            self.sort_order = other.sort_order
        if self.clarification_needed is None:
            self.clarification_needed = other.clarification_needed

    # 兼容旧调用点 ------------------------------------------------------
    @property
    def facets(self) -> dict[str, list[str]]:
        """向后兼容的 dict 视图（category/shape 等）。"""
        return {f.attribute_code: list(f.values) for f in self.hard_facets}

    @property
    def keywords(self) -> list[str]:
        return self.soft_terms


# ---------------------------------------------------------------------------
# 否定词与残渣停用词
# ---------------------------------------------------------------------------

NEGATION_PREFIXES = ("不要", "不想", "排除", "去掉", "除外", "除了", "非", "不", "无", "勿", "别")
NEGATION_WINDOW = 6  # 否定词后多少字符内命中的别名算排除

# 礼貌用语 / 疑问词 / 数量词 / 价格词：这些不应作为软搜索词残留
POLITE_TERMS = (
    "请问", "请", "帮我", "帮忙", "给我", "我想", "我想要", "想要", "需要", "想找",
    "查找", "查询", "查一下", "找一下", "找出", "看看", "看一下", "有吗", "有没有",
    "可以", "能否", "能不能", "谢谢", "麻烦了",
)
QUESTION_TERMS = ("吗", "呢", "吧", "什么", "哪些", "哪个", "哪种", "多少", "怎么", "如何")
COUNT_TERMS = (
    "一张", "一个", "一批", "几", "若干", "多少", "双", "套", "组", "台", "件",
    "人数", "座位", "座位数",
)
PRICE_TERMS = (
    "预算", "价格", "面价", "价钱", "价位", "元", "块", "人民币", "rmb", "RMB",
    "以内", "以上", "不超过", "低于", "高于", "左右", "大约", "约",
)
SIZE_TERMS = (
    "长度", "长", "宽度", "宽", "高度", "高", "尺寸", "规格", "毫米", "厘米", "米",
    "mm", "MM", "cm", "CM", "m",
)
TERM_STOPWORDS = set(POLITE_TERMS) | set(QUESTION_TERMS) | set(COUNT_TERMS) | set(
    PRICE_TERMS
) | set(SIZE_TERMS)

_RESIDUAL_FILLER_TERMS = tuple(
    sorted(
        (set(POLITE_TERMS) - {"请"})
        | set(PRICE_TERMS)
        | {
            "推荐", "最便宜", "最低价", "最实惠", "最优惠", "最贵", "最高价",
            "最长", "最短", "最大尺寸", "最小尺寸",
        },
        key=len,
        reverse=True,
    )
)


# ---------------------------------------------------------------------------
# 数值表达抽取
# ---------------------------------------------------------------------------

_CN_NUM = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
# 万 / 亿：仅作为整数量级后缀（如"一万"）
_CN_MAGNITUDE = {"万": 10000, "亿": 100000000}


def _cn_to_int(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    # "一万" / "两万" / "三万"：汉字 + 量级
    if text and text[-1] in _CN_MAGNITUDE and len(text) <= 2:
        head = _CN_NUM.get(text[:-1], 1) if len(text) == 2 else 1
        return head * _CN_MAGNITUDE[text[-1]]
    if text in _CN_NUM:
        return _CN_NUM[text]
    # 十一 / 二十 / 二十三
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_NUM.get(left, 1) if left else 1
        ones = _CN_NUM.get(right, 0) if right else 0
        return tens * 10 + ones
    # 三千 / 五百
    for unit_char, multiplier in (("千", 1000), ("百", 100)):
        if unit_char in text:
            left, _, right = text.partition(unit_char)
            head = _CN_NUM.get(left, 1) if left else 1
            tail = _CN_NUM.get(right, 0) if right else 0
            return head * multiplier + tail
    return None


_NUM_WITH_UNIT_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?|十[一二]?|[零一二两三四五六七八九]{1,3}|"
    r"[零一二两三四五六七八九]?[千百][零一二两三四五六七八九]?|"
    r"[一二两三四五六七八九]?[万亿])\s*"
    r"(?P<unit>人|座|毫米|厘米|米|mm|MM|cm|CM|m|元|块)",
)
# "长度 3000" / "宽度 1500" / "高度 760"：维度词 + 数字（无单位）
_NUM_AFTER_DIMENSION_RE = re.compile(
    r"(?P<dim>长度|长|宽度|宽|高度|高)\s*(?:为|是|约|大概|在)?\s*(?P<num>\d+(?:\.\d+)?|"
    r"[一二两三四五六七八九]?[万亿]|[零一二两三四五六七八九]{1,3})\s*"
    r"(?P<unit>毫米|mm|MM|厘米|cm|CM|米|m)?\s*(?:左右|以内|以上|以下)?",
    re.IGNORECASE,
)
# "预算 5000" / "价格不超过 8000" 这类：价格词 + (可选界限词) + 数字
_NUM_AFTER_PRICE_WORD_RE = re.compile(
    r"(?:预算|价格|面价|价钱|价位)"
    r"(?:\s*(?:为|是|大概|约|在))?"
    r"(?:\s*(?:不超过|不低于|低于|高于|以内|以上))?"
    r"\s*(?P<num>\d+(?:\.\d+)?|[一二两三四五六七八九]?[万亿]|[零一二两三四五六七八九]{1,3}[千百]?[零一二两三四五六七八九]?)"
    r"\s*(?P<unit>元|块|rmb|RMB)?",
    re.IGNORECASE,
)
_BOUND_RE = re.compile(
    r"(?P<dir>以内|以下|之内|不超过|低于|最多|以上|起|不低于|大于|超过|左右|约为|大约)"
)
# 这些词表示"约等于"，不构成方向，只给容差
_APPROX_DIRS = ("左右", "约为", "大约")


@dataclass
class NumericMention:
    value: float
    unit: str | None
    direction: str | None  # 'max' | 'min' | None


def extract_numeric_mentions(message: str) -> list[NumericMention]:
    """抽取"5000元以内""3米以上""12人"这类数值表达（含中文数字）。

    界限词可能在数值**之前**（"不超过 5000 元"）或**之后**（"5000 元以内"），
    因此两个方向都要看。
    """
    out: list[NumericMention] = []
    for match in _NUM_WITH_UNIT_RE.finditer(message):
        raw_num = match.group("num")
        value = _cn_to_int(raw_num)
        if value is None:
            continue
        unit = match.group("unit")
        direction: str | None = None
        before = message[max(0, match.start() - 4) : match.start()]
        after = message[match.end() : match.end() + 5]
        bound = _BOUND_RE.search(before) or _BOUND_RE.search(after)
        if bound:
            word = bound.group("dir")
            if word in ("以内", "以下", "之内", "不超过", "低于", "最多"):
                direction = "max"
            else:
                direction = "min"
        out.append(NumericMention(value=float(value), unit=unit, direction=direction))
    return out


# 单位 -> 属性（尺寸单位先给一个通用占位，再由上下文细化到具体维度）
_UNIT_TO_ATTRIBUTE = {
    "人": "seat_count",
    "座": "seat_count",
    "毫米": "specification_size_mm",
    "mm": "specification_size_mm",
    "MM": "specification_size_mm",
    "厘米": "specification_size_mm",
    "cm": "specification_size_mm",
    "CM": "specification_size_mm",
    "米": "specification_size_mm",
    "m": "specification_size_mm",
    "元": "face_price",
    "块": "face_price",
    "rmb": "face_price",
    "RMB": "face_price",
}

# 上下文关键词 -> 属性（决定"长/宽/高"分别落到哪个数值条件）
_DIMENSION_CONTEXT = (
    (("长", "长度", "多长"), "specification_length_mm"),
    (("宽", "宽度", "多宽"), "specification_width_mm"),
    (("高", "高度", "多高"), "specification_height_mm"),
)
# 显式维度词 -> 属性
_DIMENSION_BY_WORD = {
    "长": "specification_length_mm",
    "长度": "specification_length_mm",
    "宽": "specification_width_mm",
    "宽度": "specification_width_mm",
    "高": "specification_height_mm",
    "高度": "specification_height_mm",
}


def _dimension_for_index(message: str, index: int) -> str | None:
    """按位置推断长/宽/高：先看前文，再看紧随其后的维度词（"3 米长"）。"""
    window_before = message[max(0, index - 6) : index]
    window_after = message[index : index + 8]
    for keywords, attribute in _DIMENSION_CONTEXT:
        for kw in keywords:
            if kw in window_before or kw in window_after:
                return attribute
    return None


def _collect_mentions(message: str) -> list[tuple[float, str, str | None, int, str | None]]:
    """收集所有数值表达：(value, unit, direction, position, dimension)。"""
    out: list[tuple[float, str, str | None, int, str | None]] = []
    for match in _NUM_WITH_UNIT_RE.finditer(message):
        value = _cn_to_int(match.group("num"))
        if value is None:
            continue
        out.append((float(value), match.group("unit"), None, match.start(), None))
    for match in _NUM_AFTER_PRICE_WORD_RE.finditer(message):
        value = _cn_to_int(match.group("num"))
        if value is None:
            continue
        out.append(
            (float(value), match.group("unit") or "元", None, match.start(), None)
        )
    for match in _NUM_AFTER_DIMENSION_RE.finditer(message):
        value = _cn_to_int(match.group("num"))
        if value is None:
            continue
        unit = (match.group("unit") or "mm")
        if unit in ("mm", "MM", "毫米"):
            unit = "mm"
        elif unit in ("cm", "CM", "厘米"):
            unit = "cm"
        else:
            unit = "米"
        out.append((float(value), unit, None, match.start(), match.group("dim")))
    # 统一按位置探测方向词（向前 6 字、向后 14 字）
    resolved: list[tuple[float, str, str | None, int, str | None]] = []
    for value, unit, _direction, position, dimension in out:
        before = message[max(0, position - 6) : position]
        after = message[position : position + 14]
        bound = _BOUND_RE.search(before) or _BOUND_RE.search(after)
        direction: str | None = None
        if bound:
            word = bound.group("dir")
            if word in _APPROX_DIRS:
                direction = None
            elif word in ("以内", "以下", "之内", "不超过", "低于", "最多"):
                direction = "max"
            else:
                direction = "min"
        resolved.append((value, unit, direction, position, dimension))
    return resolved


def build_numeric_filters(
    message: str, dictionary: AttributeDictionary | None = None
) -> list[NumericFilter]:
    """把数值表达转成通用 NumericFilter。

    ``dictionary`` 里若定义了对应 data_type='number'/'range' 的属性，
    才生成过滤条件；未定义的词不会猜。

    没有方向词（"12 人"、"高度 760"）时按"约等于"处理：同时设
    min/max 容差，由工具层决定是否作为软条件。
    """
    known: set[str] = set()
    if dictionary is not None:
        known = {
            code
            for code, d in dictionary.definitions.items()
            if d.data_type in ("number", "range")
        }

    filters: dict[str, NumericFilter] = {}
    for value, unit, direction, position, dimension_word in _collect_mentions(message):
        attribute = _UNIT_TO_ATTRIBUTE.get(unit)
        if attribute is None:
            continue
        if known and attribute not in known:
            continue

        if attribute.startswith("specification"):
            if unit == "cm":
                value = value * 10.0
            elif unit == "米":
                value = value * 1000.0
            # 长/宽/高：优先用显式维度词，其次用上下文
            resolved_dimension = (
                _DIMENSION_BY_WORD.get(dimension_word)
                if dimension_word
                else None
            ) or _dimension_for_index(message, position)
            if resolved_dimension and (not known or resolved_dimension in known):
                attribute = resolved_dimension

        existing = filters.get(attribute)
        if existing is None:
            if direction is None:
                tolerance = max(value * 0.05, 1.0)
                filters[attribute] = NumericFilter(
                    attribute_code=attribute,
                    min_value=value - tolerance,
                    max_value=value + tolerance,
                    unit="mm" if attribute.startswith("specification") else None,
                )
            else:
                filters[attribute] = NumericFilter(
                    attribute_code=attribute,
                    min_value=value if direction == "min" else None,
                    max_value=value if direction == "max" else None,
                    unit="mm" if attribute.startswith("specification") else None,
                )
        else:
            _merge_numeric(existing, direction, value)
    return [f for f in filters.values() if not f.is_empty()]


def _merge_numeric(existing: NumericFilter, direction: str | None, value: float) -> None:
    if direction == "min":
        existing.min_value = (
            value if existing.min_value is None else min(existing.min_value, value)
        )
    elif direction == "max":
        existing.max_value = (
            value if existing.max_value is None else max(existing.max_value, value)
        )
    else:
        tolerance = max(value * 0.05, 1.0)
        existing.min_value = (
            value - tolerance if existing.min_value is None else existing.min_value
        )
        existing.max_value = (
            value + tolerance if existing.max_value is None else existing.max_value
        )


# ---------------------------------------------------------------------------
# 别名抽取
# ---------------------------------------------------------------------------


@dataclass
class AliasHit:
    entry: AliasEntry
    start: int
    end: int
    negated: bool
    # 被否定时，否定词在**原文**里的起始下标（用于残余文本一并抹掉"不要"）
    negation_start: int = 0


def _negation_span(normalized: str, start: int) -> tuple[bool, int]:
    """返回 ``(是否被否定, 否定词在归一化串上的起始下标)``。"""
    window = normalized[max(0, start - NEGATION_WINDOW) : start]
    for prefix in sorted(NEGATION_PREFIXES, key=len, reverse=True):
        normalized_prefix = normalize_text(prefix)
        if normalized_prefix and window.endswith(normalized_prefix):
            return True, max(0, start - len(normalized_prefix))
    return False, start


def extract_alias_hits(message: str, dictionary: AttributeDictionary) -> list[AliasHit]:
    """最长词匹配抽取属性别名；命中位置落在**原文**坐标上。

    归一化会删掉空白/标点，所以命中位置先在归一化串上找，
    再通过映射表换算回原文下标，保证 ``_residual_text`` 从原文
    切残余词时不会错位（带空格、标点、中英混排的查询同样正确）。
    """
    if not dictionary.aliases:
        return []
    normalized, index_map = normalize_text_with_map(message)
    if not normalized:
        return []

    def to_original(norm_index: int) -> int:
        if not index_map:
            return 0
        return index_map[min(norm_index, len(index_map) - 1)]

    # 用占位符把已消耗的位置标记掉，避免短别名重复命中同一段
    consumed = list(normalized)
    hits: list[AliasHit] = []
    for entry in dictionary.sorted_aliases():
        alias = entry.normalized
        if not alias:
            continue
        search_from = 0
        while True:
            start = "".join(consumed).find(alias, search_from)
            if start < 0:
                break
            end = start + len(alias)
            negated, negation_start_norm = _negation_span(normalized, start)
            start_original = to_original(start)
            end_original = to_original(end - 1) + 1
            hits.append(
                AliasHit(
                    entry=entry,
                    start=start_original,
                    end=end_original,
                    negated=negated,
                    negation_start=(
                        to_original(negation_start_norm) if negated else 0
                    ),
                )
            )
            for i in range(start, end):
                consumed[i] = "\u0000"
            search_from = end
    hits.sort(key=lambda h: h.start)
    return hits


def build_product_query(
    message: str,
    dictionary: AttributeDictionary,
    *,
    product_nos: list[str] | None = None,
    product_ids: list[str] | None = None,
) -> ProductQuery:
    """把自然语言解析成通用 ProductQuery。

    不做任何"弧形会议桌"特例：全部由词典驱动。
    """
    query = ProductQuery(product_nos=list(product_nos or []), product_ids=list(product_ids or []))

    hits = extract_alias_hits(message, dictionary)
    included: dict[str, dict[str, str]] = {}
    excluded: dict[str, dict[str, str]] = {}
    for hit in hits:
        target = excluded if hit.negated else included
        bucket = target.setdefault(hit.entry.attribute_code, {})
        bucket[hit.entry.option_code] = hit.entry.alias

    for attribute_code, options in included.items():
        query.hard_facets.append(
            HardFacet(
                attribute_code=attribute_code,
                values=list(options.keys()),
                required=True,
                match_mode=(
                    "all"
                    if len(options) > 1 and _has_conjunction(message, options)
                    else "any"
                ),
                source="rule",
            )
        )
        query.alias_labels.setdefault(attribute_code, {}).update(
            {code: list(aliases) for code, aliases in options.items()}
        )
    for attribute_code, options in excluded.items():
        query.exclude_values.append(
            HardFacet(
                attribute_code=attribute_code,
                values=list(options.keys()),
                required=False,
                match_mode="any",
                source="rule",
            )
        )

    query.numeric_filters = build_numeric_filters(message, dictionary)

    # 残余文本 -> 软词 / 未知词
    residual = _residual_text(message, hits, product_nos=list(product_nos or []))
    for token in _tokenize_residual(residual):
        if _is_stopword(token):
            continue
        query.soft_terms.append(token)

    # 明显是产品型号的 token 提到 product_nos（由调用方处理）
    query.sort, query.sort_order = _detect_sort(message)
    return query


def _has_conjunction(message: str, options: dict[str, str]) -> bool:
    normalized = normalize_text(message)
    for alias in options.values():
        idx = normalized.find(normalize_text(alias))
        if idx < 0:
            continue
        window = normalized[idx : idx + len(normalize_text(alias)) + 4]
        if any(c in window for c in ("和", "且", "以及", "与", "、")):
            return True
    return False


def _residual_text(
    message: str, hits: list[AliasHit], product_nos: list[str] | None = None
) -> str:
    if not hits and not product_nos:
        return message
    chars = list(message)
    for hit in hits:
        # 被否定的命中要把否定词一起抹掉，否则"不要黑色"会残留出"不要"
        begin = hit.negation_start if hit.negated else hit.start
        for i in range(begin, hit.end):
            if 0 <= i < len(chars):
                chars[i] = " "
    # 产品型号本身不应当成为软词（型号已进 product_nos，检索走精确匹配）
    for product_no in product_nos or []:
        for match in re.finditer(re.escape(str(product_no)), "".join(chars)):
            for i in range(match.start(), match.end()):
                chars[i] = " "
    return "".join(chars)


# 品类词被"会议桌"这类复合词命中后，可能残留"议桌"这类碎片。
# 这些碎片没有任何检索价值，直接丢弃。
_RESIDUAL_FRAGMENTS = (
    "议桌", "议台", "公桌", "班台", "裁桌", "管桌", "客桌", "客台",
    "公椅", "班椅", "裁椅", "管椅", "柜", "桌椅", "桌", "椅", "台",
)


def _tokenize_residual(text: str) -> list[str]:
    # 先去掉价格/尺寸/数量表达，避免"5000""12"这类数字变成软词
    text = _NUM_WITH_UNIT_RE.sub(" ", text)
    text = _BOUND_RE.sub(" ", text)
    parts = re.split(r"[\s，。！？、；：,.;:!?/|()（）\[\]【】]+", text)
    out: list[str] = []
    for part in parts:
        # Remove request/sort filler without discarding the useful word attached
        # to it (for example, "找出最便宜的铭达" -> "铭达").
        for filler in _RESIDUAL_FILLER_TERMS:
            part = part.replace(filler, " ")
        part = re.sub(r"^的+|的+$", " ", part.strip())
        part = re.sub(r"吗+$", " ", part)
        part = re.sub(r"\s*有\s*(?=\d)", " ", part)
        part = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", part)
        for token in part.split():
            token = token.strip()
            if len(token) < 2:
                continue
            if token in _RESIDUAL_FRAGMENTS or _is_stopword(token):
                continue
            if token not in out:
                out.append(token)
    return out


def _is_stopword(token: str) -> bool:
    normalized = normalize_text(token)
    if not normalized:
        return True
    if token in TERM_STOPWORDS or normalized in {normalize_text(t) for t in TERM_STOPWORDS}:
        return True
    return False


_SORT_ASC = ("最便宜", "最低价", "价格最低", "最实惠", "最优惠")
_SORT_DESC = ("最贵", "最高价", "价格最高")
_SIZE_ASC = ("最短", "最小尺寸", "尺寸最小", "最小")
_SIZE_DESC = ("最长", "最大尺寸", "尺寸最大", "最大")


def _detect_sort(message: str) -> tuple[str | None, str | None]:
    if any(x in message for x in _SORT_ASC):
        return "face_price", "asc"
    if any(x in message for x in _SORT_DESC):
        return "face_price", "desc"
    if any(x in message for x in _SIZE_ASC):
        return "specification_length_mm", "asc"
    if any(x in message for x in _SIZE_DESC):
        return "specification_length_mm", "desc"
    return None, None


# ---------------------------------------------------------------------------
# 从数据库加载词典
# ---------------------------------------------------------------------------


async def load_dictionary(db) -> AttributeDictionary:
    """从 ``catalog_attribute_*`` 加载词典快照。

    ``db`` 为同步 Session 或异步 Session 均可（内部统一走 sync API）。
    """
    from app.models.catalog_attribute import (
        CatalogAttributeAlias,
        CatalogAttributeDefinition,
        CatalogAttributeOption,
    )

    definitions: dict[str, AttributeDefinitionView] = {}
    aliases: list[AliasEntry] = []

    rows = _select_all(
        db,
        CatalogAttributeDefinition,
        CatalogAttributeDefinition.is_deleted.is_(False),
        CatalogAttributeDefinition.enabled.is_(True),
    )
    option_rows = _select_all(
        db,
        CatalogAttributeOption,
        CatalogAttributeOption.is_deleted.is_(False),
        CatalogAttributeOption.enabled.is_(True),
    )
    alias_rows = _select_all(
        db,
        CatalogAttributeAlias,
        CatalogAttributeAlias.is_deleted.is_(False),
        CatalogAttributeAlias.enabled.is_(True),
    )
    options_by_id = {row.id: row for row in option_rows}

    for row in rows:
        definitions[row.code] = AttributeDefinitionView(
            code=row.code,
            name=row.name,
            data_type=row.data_type,
            multi_value=bool(row.multi_value),
            searchable=bool(row.searchable),
            hard_filterable=bool(row.hard_filterable),
        )

    for row in alias_rows:
        option = options_by_id.get(row.option_id)
        if option is None:
            continue
        definition = next(
            (d for d in rows if d.id == option.attribute_id), None
        )
        if definition is None:
            continue
        normalized = normalize_text(row.normalized_alias or row.alias)
        if not normalized:
            continue
        aliases.append(
            AliasEntry(
                attribute_code=definition.code,
                option_code=option.code,
                alias=row.alias,
                normalized=normalized,
            )
        )
        # option 自身的 label 也是一条别名
        label_normalized = normalize_text(option.label)
        if label_normalized and label_normalized != normalized:
            aliases.append(
                AliasEntry(
                    attribute_code=definition.code,
                    option_code=option.code,
                    alias=option.label,
                    normalized=label_normalized,
                )
            )

    # 去重：同一 (attribute, option, normalized) 只留一条
    deduped: dict[tuple[str, str, str], AliasEntry] = {}
    for entry in aliases:
        deduped.setdefault((entry.attribute_code, entry.option_code, entry.normalized), entry)
    return AttributeDictionary(
        definitions=definitions,
        aliases=list(deduped.values()),
        definition_ids={row.code: row.id for row in rows},
        definition_views_by_id={row.id: definitions[row.code] for row in rows},
    )


def _select_all(db, model, *conditions):
    """兼容同步/异步 Session 的简单 select。"""
    from sqlalchemy import select

    stmt = select(model).where(*conditions)
    execute = getattr(db, "execute", None)
    if execute is None:
        return []
    result = execute(stmt)
    if hasattr(result, "__await__"):
        raise RuntimeError("use await_load_dictionary for async sessions")
    return list(result.scalars().all())


async def await_load_dictionary(db) -> AttributeDictionary:
    """异步 Session 版本。

    任何异常都向上抛出，由调用方决定 fail-closed 行为（退回空词典）。
    """
    from sqlalchemy import select

    from app.models.catalog_attribute import (
        CatalogAttributeAlias,
        CatalogAttributeDefinition,
        CatalogAttributeOption,
    )

    definitions: dict[str, AttributeDefinitionView] = {}
    rows = (
        await db.execute(
            select(CatalogAttributeDefinition).where(
                CatalogAttributeDefinition.is_deleted.is_(False),
                CatalogAttributeDefinition.enabled.is_(True),
            )
        )
    ).scalars().all()
    option_rows = (
        await db.execute(
            select(CatalogAttributeOption).where(
                CatalogAttributeOption.is_deleted.is_(False),
                CatalogAttributeOption.enabled.is_(True),
            )
        )
    ).scalars().all()
    alias_rows = (
        await db.execute(
            select(CatalogAttributeAlias).where(
                CatalogAttributeAlias.is_deleted.is_(False),
                CatalogAttributeAlias.enabled.is_(True),
            )
        )
    ).scalars().all()

    options_by_id = {row.id: row for row in option_rows}
    definition_by_id = {row.id: row for row in rows}
    for row in rows:
        definitions[row.code] = AttributeDefinitionView(
            code=row.code,
            name=row.name,
            data_type=row.data_type,
            multi_value=bool(row.multi_value),
            searchable=bool(row.searchable),
            hard_filterable=bool(row.hard_filterable),
        )

    aliases: list[AliasEntry] = []
    for row in alias_rows:
        option = options_by_id.get(row.option_id)
        if option is None:
            continue
        definition = definition_by_id.get(option.attribute_id)
        if definition is None:
            continue
        normalized = normalize_text(row.normalized_alias or row.alias)
        if normalized:
            aliases.append(
                AliasEntry(
                    attribute_code=definition.code,
                    option_code=option.code,
                    alias=row.alias,
                    normalized=normalized,
                )
            )
        label_normalized = normalize_text(option.label)
        if label_normalized and label_normalized != normalized:
            aliases.append(
                AliasEntry(
                    attribute_code=definition.code,
                    option_code=option.code,
                    alias=option.label,
                    normalized=label_normalized,
                )
            )
    deduped: dict[tuple[str, str, str], AliasEntry] = {}
    for entry in aliases:
        deduped.setdefault((entry.attribute_code, entry.option_code, entry.normalized), entry)
    return AttributeDictionary(
        definitions=definitions,
        aliases=list(deduped.values()),
        definition_ids={row.code: row.id for row in rows},
        definition_views_by_id={row.id: definitions[row.code] for row in rows},
    )
