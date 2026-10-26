"""产品事实装配单测：隐私字段、属性来源过滤、截断与提示词注入。"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.content_facts import FACT_TEXT_LIMIT, product_fact_payload


def _product(**overrides):
    base = dict(
        id="p-1",
        product_name="铭达总裁桌 EMD89R.320190",
        product_no="EMD89R.320190",
        specification="W3200*D1900*H750 mm",
        series="EMD89R",
        category=SimpleNamespace(category_name="总裁桌"),
        brand=SimpleNamespace(brand_name="铭达"),
        material="岩板",
        material_description="台面为岩板，边框为铝合金。",
        colors="黑色、灰色",
        description="面向总裁办公区的成套桌台。",
        face_price=99999.0,
        stock_status="in_stock",
        data_source="内部导入",
        attribute_values=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _attr_value(name, *, option=None, text=None, num=None, source="manual", verified=False):
    return SimpleNamespace(
        definition=SimpleNamespace(name=name, code=name),
        option=SimpleNamespace(label=option, code=option) if option else None,
        value_text=text,
        value_num=num,
        unit="mm" if num is not None else None,
        source=source,
        verified=verified,
    )


def test_payload_excludes_price_stock_and_internal_fields():
    payload = product_fact_payload(_product())
    assert payload["product_name"] == "铭达总裁桌 EMD89R.320190"
    assert payload["specs"] == "W3200*D1900*H750 mm"
    assert payload["category"] == "总裁桌"
    assert payload["brand"] == "铭达"
    assert payload["material"] == "岩板"
    assert payload["attributes"] == {}
    # 价格、库存、供应商、数据来源等一律不进提示词
    for forbidden in ("face_price", "stock_status", "data_source", "cost_price", "supplier"):
        assert forbidden not in payload
    assert "99999" not in str(payload)


def test_attributes_only_keep_trusted_or_verified_values():
    product = _product(
        attribute_values=[
            _attr_value("桌形", option="一字型"),
            _attr_value("风格", option="现代简约", source="ai_inferred"),
            _attr_value("尺寸类别", text="大尺寸", source="ai_inferred", verified=True),
            _attr_value("台面宽度", num=3200),
        ]
    )
    attributes = product_fact_payload(product)["attributes"]
    assert attributes == {
        "桌形": "一字型",
        "尺寸类别": "大尺寸",
        "台面宽度": "3200mm",
    }


def test_multi_option_values_are_joined():
    product = _product(
        attribute_values=[
            _attr_value("颜色", option="黑色"),
            _attr_value("颜色", option="灰色"),
        ]
    )
    assert product_fact_payload(product)["attributes"]["颜色"] == "黑色、灰色"


def test_long_text_is_truncated():
    product = _product(description="长" * (FACT_TEXT_LIMIT + 200))
    payload = product_fact_payload(product)
    assert len(payload["description"]) == FACT_TEXT_LIMIT


def test_content_prompt_injects_enriched_facts():
    from app.models.content_skill import ContentSkill
    from app.services.content_dna import CONTENT_OUTPUT_SCHEMA, YANYE_CONTENT_PROMPT
    from app.services.content_service import build_content_prompt

    skill = ContentSkill(
        code="yanye-content",
        name="言也 DNA · 内容工坊",
        skill_type="content",
        source_dna="yanye",
        prompt_template=YANYE_CONTENT_PROMPT,
        output_schema=CONTENT_OUTPUT_SCHEMA,
    )
    prompt = build_content_prompt(
        skill,
        topic="总裁桌选购",
        platform="xhs",
        tone="warm",
        products=[product_fact_payload(_product(attribute_values=[_attr_value("桌形", option="一字型")]))],
        project_facts=[],
    )
    assert "铭达总裁桌 EMD89R.320190" in prompt
    assert "岩板" in prompt
    assert "一字型" in prompt
    assert "99999" not in prompt
