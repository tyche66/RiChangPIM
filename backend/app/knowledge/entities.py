from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.attributes import ProductQuery
from app.knowledge.facets import ProductFacets


class QueryEntities(BaseModel):
    """规则解析器与模型规划器共享的实体载体。

    ``facets`` 保留为 ProductFacets（向后兼容），
    ``query`` 是完整的通用查询理解结果（硬条件/数值/软词/未知词/排序）。
    """

    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(default_factory=list)
    product_nos: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    status_terms: list[str] = Field(default_factory=list)
    facets: ProductFacets = Field(default_factory=ProductFacets)
    query: ProductQuery = Field(default_factory=ProductQuery)
    price_min: float | None = None
    price_max: float | None = None
    price_sort: str | None = None
    specification_sort: str | None = None
