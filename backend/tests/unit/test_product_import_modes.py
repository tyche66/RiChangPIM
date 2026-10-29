"""重传产品包的字段合并基础：``RowFields.provided`` 必须准确区分「空着」和「填了值」。

覆盖 / 追加模式靠它决定「这个单元格要不要写回产品」：判断错了就会把已上架产品
打回草稿，或者用 99999 覆盖掉真实面价。
"""

from app.services.product_import import (
    PLACEHOLDER_PRICE,
    ProductRow,
    parse_row,
)


def _row(**values) -> ProductRow:
    return ProductRow(excel_row=2, values=values)


def test_fully_filled_row_marks_every_field_as_provided():
    fields = parse_row(
        _row(
            product_no="SUNON-001",
            product_name="办公椅",
            brand_name="圣奥",
            supplier_name="圣奥",
            category_name="办公椅",
            face_price="1280",
            cost_price="860",
            material="网布",
            specification="W650",
            colors="黑色",
            description="说明",
            data_source="报价表",
            stock_status="有货",
            status="上架",
            tag_names="热销,新品",
        )
    )

    assert fields.errors == []
    assert fields.face_price == 1280
    assert fields.provided >= {
        "product_no",
        "product_name",
        "face_price",
        "cost_price",
        "material",
        "specification",
        "colors",
        "description",
        "data_source",
        "stock_status",
        "status",
        "tag_names",
    }


def test_blank_cells_are_not_provided_so_existing_values_survive():
    """面价留空 → 99999 占位；但「没填」不能算作要覆盖已有面价。"""
    fields = parse_row(
        _row(
            product_no="SUNON-002",
            product_name="会议桌",
            brand_name="圣奥",
            supplier_name="圣奥",
            category_name="会议桌",
        )
    )

    assert fields.face_price == PLACEHOLDER_PRICE
    assert fields.completeness_status == "pending"
    assert "face_price" not in fields.provided
    assert "status" not in fields.provided
    assert "stock_status" not in fields.provided
    # 默认值仍然填着，create 模式照旧用它们建产品
    assert fields.status == "draft"
    assert fields.stock_status == "in_stock"


def test_misspelled_enum_keeps_existing_value_instead_of_writing_the_default():
    """「有货的」这种写法会被降级成默认值 + 提示；此时不能把它当成用户填的值。"""
    fields = parse_row(
        _row(
            product_no="SUNON-003",
            product_name="文件柜",
            face_price="500",
            stock_status="有货的",
            status="已经上架了",
        )
    )

    assert "stock_status" not in fields.provided
    assert "status" not in fields.provided
    assert any("stock_status" in note for note in fields.notes)
    assert any("status" in note for note in fields.notes)


def test_explicit_placeholder_price_is_provided_and_marked_pending():
    fields = parse_row(
        _row(product_no="SUNON-004", product_name="待核价椅子", face_price="待核价")
    )

    assert fields.face_price == PLACEHOLDER_PRICE
    assert fields.completeness_status == "pending"
    assert "face_price" in fields.provided


def test_explicit_completeness_is_provided():
    fields = parse_row(
        _row(
            product_no="SUNON-005",
            product_name="椅子",
            face_price="800",
            completeness_status="待补充",
        )
    )

    assert fields.completeness_status == "pending"
    assert "completeness_status" in fields.provided


def test_tag_specs_support_explicit_type_prefix_and_suffix():
    """标签单元格可以写「系列:摩耳」「摩耳(系列)」，类型会跟着标签走。"""
    fields = parse_row(
        _row(
            product_no="SUNON-006",
            product_name="椅子",
            face_price="800",
            tag_names="系列:摩耳,风格:新中式,摩耳（系列）,热销,series:Moer",
        )
    )

    assert ("摩耳", "series") in fields.tag_specs
    assert ("新中式", "style") in fields.tag_specs
    assert ("热销", None) in fields.tag_specs
    assert ("Moer", "series") in fields.tag_specs
    # 同一个 (名称, 类型) 只保留一次
    assert len([s for s in fields.tag_specs if s == ("摩耳", "series")]) == 1
    # 老字段仍然可用，值就是标签名
    assert "热销" in fields.tag_names
    assert "摩耳" in fields.tag_names


def test_unknown_cjk_prefix_is_not_treated_as_a_type():
    """「型号:ABC」这种正常标签名不能被拆成 类型=型号。"""
    fields = parse_row(
        _row(
            product_no="SUNON-007",
            product_name="椅子",
            face_price="800",
            tag_names="型号:ABC",
        )
    )

    assert fields.tag_specs == [("型号:ABC", None)]
