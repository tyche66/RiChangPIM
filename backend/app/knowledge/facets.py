"""通用产品 Facet（Track A）。

原先这里写死了 ``category`` / ``shape`` 两个维度与一整张业务词表，
导致每加一种桌形就要改 Python。现在维度完全由数据库里的
``catalog_attribute_definition`` 驱动，本模块只提供：

* ``ProductFacets``：attribute_code -> option codes 的通用容器，
  保留 ``.category`` / ``.shape`` 属性以兼容既有调用点；
* ``extract_product_facets``：基于属性词典的最长词匹配解析；
* 语义保证：不同属性 AND、同属性已确认同义词 OR、属性缺失不算命中。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.attributes import (
    AttributeDictionary,
    ProductQuery,
    build_product_query,
)

# 兼容旧导入点的空词典
FACET_ALIASES: dict[str, dict[str, str]] = {}
FACET_QUERY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {}
SHAPE_TAG_TYPES: tuple[str, ...] = ()


class ProductFacets(BaseModel):
    """通用 facet 容器。

    ``values`` 的 key 是 ``catalog_attribute_definition.code``，
    value 是归一后的 ``catalog_attribute_option.code`` 列表。
    """

    model_config = ConfigDict(extra="forbid")

    values: dict[str, list[str]] = Field(default_factory=dict)

    # -- 兼容旧调用点 ----------------------------------------------------
    @property
    def category(self) -> list[str]:
        return self.values.get("category", [])

    @property
    def shape(self) -> list[str]:
        return self.values.get("shape", [])

    def has_constraints(self) -> bool:
        return any(self.values.values())

    @classmethod
    def from_query(cls, query: ProductQuery) -> ProductFacets:
        values: dict[str, list[str]] = {}
        for facet in query.hard_facets:
            if facet.values:
                values[facet.attribute_code] = list(facet.values)
        return cls(values=values)

    @classmethod
    def coerce(cls, payload) -> ProductFacets:
        """接受 dict（模型/前端传来）或 ProductFacets。"""
        if isinstance(payload, ProductFacets):
            return payload
        if isinstance(payload, dict):
            values = payload.get("values", payload)
            if isinstance(values, dict):
                return cls(
                    values={
                        str(k): [str(v) for v in vs]
                        for k, vs in values.items()
                        if vs
                    }
                )
        return cls()


def extract_product_facets(
    message: str, dictionary: AttributeDictionary | None = None
) -> tuple[ProductFacets, str]:
    """解析消息中的显式属性条件，返回 (facets, 残余文本)。

    ``dictionary`` 为空时退化为无约束——绝不回退到硬编码词表，
    避免"没有字典也能猜"这种静默放宽。
    """
    if dictionary is None or not dictionary.aliases:
        return ProductFacets(), message
    query = build_product_query(message, dictionary)
    return ProductFacets.from_query(query), message
