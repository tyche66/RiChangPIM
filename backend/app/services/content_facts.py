"""内容生成与选题共用的产品事实装配（Track B / B 期事实注入）。

只暴露可以直接对外表述的字段：价格、库存、供应商、数据来源等
一律不进入外部模型提示词。属性值只保留可信来源（人工/业务确认/
导入/迁移），ai_inferred 且未确认的值视为不可用事实。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import selectinload

from app.models.catalog_attribute import ProductAttributeValue
from app.models.product import Product

# 产品说明类文本注入提示词前的截断长度：给模型足够的细节锚点，
# 又不至于把长手册挤爆上下文。
FACT_TEXT_LIMIT = 600

# 仅把来源可信的属性值注入外部提示词；ai_inferred 且未人工确认的值不进提示词，
# 避免把模型自己的推断当成公司事实再喂给生成模型。
TRUSTED_ATTRIBUTE_SOURCES = ("manual", "business_confirmed", "import", "migrated")

# 富化事实需要的关系预加载选项（异步会话禁止隐式懒加载）。
PRODUCT_FACT_OPTIONS = (
    selectinload(Product.category),
    selectinload(Product.brand),
    selectinload(Product.attribute_values).selectinload(ProductAttributeValue.definition),
    selectinload(Product.attribute_values).selectinload(ProductAttributeValue.option),
)


def _truncate_fact_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:FACT_TEXT_LIMIT]


def attribute_facts(product: Product) -> dict[str, Any]:
    """把受治理属性值压成 {属性名: 取值文本}，只保留可信来源。"""
    facts: dict[str, Any] = {}
    for value in getattr(product, "attribute_values", None) or []:
        if value.source not in TRUSTED_ATTRIBUTE_SOURCES and not value.verified:
            continue
        definition = getattr(value, "definition", None)
        name = getattr(definition, "name", None) or getattr(definition, "code", None)
        if not name:
            continue
        if value.option is not None:
            rendered = value.option.label or value.option.code
        elif value.value_text:
            rendered = value.value_text
        elif value.value_num is not None:
            rendered = f"{value.value_num:g}{value.unit or ''}"
        else:
            continue
        existing = facts.get(name)
        facts[name] = f"{existing}、{rendered}" if existing else rendered
    return facts


def product_fact_payload(product: Product) -> dict[str, Any]:
    """生成/选题提示词用的产品事实包。"""
    category = getattr(product, "category", None)
    brand = getattr(product, "brand", None)
    return {
        "id": str(product.id),
        "product_name": product.product_name,
        "product_no": getattr(product, "product_no", None),
        "specs": getattr(product, "specification", None) or getattr(product, "specs", None),
        "series": getattr(product, "series", None),
        "category": getattr(category, "category_name", None),
        "brand": getattr(brand, "brand_name", None),
        "material": _truncate_fact_text(getattr(product, "material", None)),
        "material_description": _truncate_fact_text(getattr(product, "material_description", None)),
        "colors": _truncate_fact_text(getattr(product, "colors", None)),
        "description": _truncate_fact_text(getattr(product, "description", None)),
        "attributes": attribute_facts(product),
    }
