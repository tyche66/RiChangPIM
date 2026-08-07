"""批量导入表格解析层的单元用例（app/services/product_import.py）。

三条主线：表头认列（中文/英文/供应商叫法/带序号的图片列）、行解析的「整行失败 vs
降级入库」分界、以及导入模板能被这套解析器自己读回来。

夹具用 pandas 现写真 xlsx（纯文字、不含图片，所以不牵连 Pillow）：表头行检测和
excel_row 口径都依赖 pandas 的空值与类型行为，手搓 dict 会把这些全绕过去，而正是
这些地方出错会让内嵌图片挂到相邻产品身上。

内嵌图片本身的解析在 tests/unit/test_excel_images.py，这里只管文字列。
"""

import io
from datetime import date, datetime

import pandas as pd
import pytest

from app.services.product_import import (
    COMPLETENESS_ALIASES,
    HEADER_ALIASES,
    PLACEHOLDER_PRICE,
    STATUS_ALIASES,
    STOCK_STATUS_ALIASES,
    ProductRow,
    SheetError,
    build_import_template,
    cell_text,
    detect_header_row,
    normalize_enum,
    parse_price,
    parse_row,
    read_product_sheet,
    resolve_header,
    split_multi,
)

# products_export.HEADER_MAP 的全部取值。这里是抄的而不是 import 的：那个模块为了
# 查库牵连 app.core.database，进不了单元层（tests/unit/conftest.py 的约定）。
# 导出列名改了这条会红 —— 那正是要提醒的事：「导出→改几行→导回」是最常用的路径。
EXPORT_HEADERS: tuple[str, ...] = (
    "产品ID",
    "产品编号",
    "产品名称",
    "品牌",
    "供应商",
    "分类",
    "面价",
    "成本价",
    "材质",
    "库存状态",
    "状态",
    "描述",
    "规格",
    "颜色",
    "数据来源",
    "完整度状态",
    "创建时间",
    "更新时间",
    "标签",
)


def _xlsx(rows: list[list[object]]) -> bytes:
    """把二维表写成 xlsx。首行刻意不留空 —— openpyxl 不写纯空的前导行，
    pandas 读回来会少几行，行号断言就会假绿。"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, header=False, sheet_name="报价单")
    return buffer.getvalue()


def test_exported_chinese_headers_are_all_recognised():
    """导出的每一列都要认得出，否则「导出→改→导回」第一步就报缺列。

    老代码只认 product_no / product_name / face_price 这三个英文键，而导出写的是
    中文表头 —— 这条用例钉住的就是那个断裂点。
    """
    assert [h for h in EXPORT_HEADERS if resolve_header(h) is None] == []
    assert resolve_header("产品编号") == "product_no"
    assert resolve_header("面价") == "face_price"
    assert resolve_header("完整度状态") == "completeness_status"
    # 产品ID/时间列是导出才有的，认出来但要忽略（空串），不然每次导回都提示一堆
    # 「无法识别的列」，用户会以为是自己表错了。
    assert resolve_header("产品ID") == ""
    assert resolve_header("创建时间") == ""
    assert resolve_header("更新时间") == ""


def test_header_aliases_cover_english_keys_supplier_wording_and_decorations():
    """供应商发来的表用的是「货号/品名/单价」，模板列名带星号，手写表带空格括号。"""
    assert resolve_header("product_no") == "product_no"
    assert resolve_header("facePrice") == "face_price"
    assert resolve_header("Product Name") == "product_name"
    assert resolve_header("货号") == "product_no"
    assert resolve_header("品名") == "product_name"
    assert resolve_header("单价") == "face_price"
    assert resolve_header("厂商") == "supplier_name"
    assert resolve_header("产品编号*") == "product_no"
    assert resolve_header(" 产品 编号 ") == "product_no"
    # 末尾括号里是给人看的说明，不该影响认列。
    assert resolve_header("产品名称（必填）") == "product_name"
    assert resolve_header("面价(含税)") == "face_price"
    assert resolve_header("单价（元/把）") == "face_price"
    assert resolve_header("图片1（可选）") == "images"


def test_numbered_columns_are_only_forgiven_for_image_columns():
    """「图片1/图片2」是供应商表里多图的标准排法（一列一张），必须认。

    但只对图片列做这个退让：把「价格2」当成面价会静默用错一列数据，宁可报
    「无法识别」让用户看见。
    """
    assert resolve_header("图片1") == "images"
    assert resolve_header("主图2") == "main_image"
    assert resolve_header("scene_image_3") == "scene_images"
    assert resolve_header("图片２") == "images"  # 全角数字
    assert resolve_header("价格2") is None
    assert resolve_header("备注3") is None
    assert resolve_header("未知列") is None
    assert resolve_header("") is None
    assert resolve_header(None) is None


def test_every_declared_alias_resolves_back_to_its_own_key():
    """别名表里出现重复词（比如「图片」同时写进 images 和 scene_images）时，
    后写的那组会静默抢走它 —— 这条用例让重复在改表当场就红。"""
    for key, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            assert resolve_header(alias) == key, f"表头「{alias}」落到了 {resolve_header(alias)}"
        # 每组第一个别名同时用作模板列名，必须是中文那一版。
        assert not aliases[0].isascii(), f"{key} 的模板列名应该是中文"


def test_cell_text_keeps_integer_product_numbers_intact():
    """一列编号里只要混进一个空格，pandas 就把整列推成 float64。

    ``str(100234.0)`` == "100234.0"，编号凭空多个小数点 —— 「编号已存在」和批内
    去重会同时失灵，还会在库里造出一个查不到的产品。
    """
    assert cell_text(100234.0) == "100234"
    assert cell_text(1280.5) == "1280.5"
    assert cell_text(float("nan")) == ""
    assert cell_text(None) == ""
    assert cell_text(pd.NA) == ""
    assert cell_text("  SUNON-001  ") == "SUNON-001"
    assert cell_text(datetime(2026, 8, 3, 10, 30, 5)) == "2026-08-03 10:30:05"
    assert cell_text(date(2026, 8, 3)) == "2026-08-03"


def test_parse_price_degrades_instead_of_blowing_up_the_whole_import():
    """原实现是 ``float(row.get("face_price", 0))``，没有 try。

    导出的「待核价」再导回去直接 ValueError，一行脏数据让整份导入 500，前面几百行
    也一起没了 —— 所以「解不动」必须降级成行级原因。
    """
    assert parse_price("1,280.00").value == 1280.0
    assert parse_price("¥1280 元/把").value == 1280.0
    assert parse_price(1280).value == 1280.0
    assert parse_price("") == parse_price(None)
    assert (parse_price("").value, parse_price("").error) == (None, None)
    for word in ("待核价", "面议", "TBD", "-"):
        price = parse_price(word)
        assert (price.value, price.placeholder) == (PLACEHOLDER_PRICE, True), word
    # 有人手填 99999：也按占位价处理，否则会撞 check_product_placeholder_price。
    assert parse_price(99999).placeholder is True
    assert "无法识别" in (parse_price("看图议价").error or "")
    assert "负数" in (parse_price("-50").error or "")
    assert "成本价" in (parse_price("abc", field_label="成本价").error or "")


def test_enum_values_fall_back_to_defaults_with_a_note():
    """库里这三列是 CheckConstraint 卡着的，认不出的写法必须落默认值。

    原样塞进去只会换成 IntegrityError，行级失败原因还是一坨 SQL，用户看不懂。
    """
    assert normalize_enum("有货", STOCK_STATUS_ALIASES, "in_stock") == ("in_stock", None)
    assert normalize_enum("缺货", STOCK_STATUS_ALIASES, "in_stock") == ("out_of_stock", None)
    assert normalize_enum("in_stock", STOCK_STATUS_ALIASES, "unknown") == ("in_stock", None)
    assert normalize_enum("上架", STATUS_ALIASES, "draft") == ("active", None)
    assert normalize_enum("待补充", COMPLETENESS_ALIASES, "complete") == ("pending", None)
    assert normalize_enum("", STOCK_STATUS_ALIASES, "in_stock") == ("in_stock", None)

    value, note = normalize_enum("有货的", STOCK_STATUS_ALIASES, "in_stock")
    assert value == "in_stock"
    assert note is not None and "in_stock" in note

    assert set(STOCK_STATUS_ALIASES.values()) == {
        "in_stock",
        "out_of_stock",
        "preorder",
        "unknown",
    }
    assert set(STATUS_ALIASES.values()) == {"active", "inactive", "draft"}
    assert set(COMPLETENESS_ALIASES.values()) == {"complete", "pending", "unknown"}


def test_split_multi_keeps_order_dedupes_and_never_splits_on_spaces():
    assert split_multi("热销, 新品；爆款|清仓") == ["热销", "新品", "爆款", "清仓"]
    assert split_multi("a\nb\r\nc") == ["a", "b", "c"]
    assert split_multi("热销,热销,新品") == ["热销", "新品"]
    assert split_multi(" , ,") == []
    assert split_multi("") == []
    # 文件名和 URL 里带空格太常见，按空格切会把一个值切碎、图片全找不到。
    assert split_multi("office chair 1.jpg") == ["office chair 1.jpg"]


def test_header_row_is_found_below_a_title_row_and_row_numbers_stay_absolute():
    """真实报价表第一行是「××公司2026年报价单」，第三行才是表头。

    excel_row 必须是绝对行号：内嵌图片是按 (行, 列) 落点归属产品的，跳过的空行
    要是让行号错位，图就会挂到相邻产品身上 —— 这是批量导入里最难发现的一类错。
    """
    payload = _xlsx(
        [
            ["某某家具 2026 年报价单", None, None, None],
            [None, None, None, None],
            ["货号", "品名", "单价", "图片1"],
            ["SUNON-001", "人体工学椅", "1,280", "chair-1.jpg"],
            [None, None, None, None],
            ["SUNON-002", "办公桌", "待核价", None],
        ]
    )

    sheet = read_product_sheet(payload)

    assert (sheet.header_row, sheet.first_data_row) == (3, 4)
    assert [(c.key, c.excel_col) for c in sheet.columns] == [
        ("product_no", 1),
        ("product_name", 2),
        ("face_price", 3),
        ("images", 4),
    ]
    assert [r.excel_row for r in sheet.rows] == [4, 6]
    assert sheet.blank_rows == 1
    assert sheet.rows[0].get("images") == "chair-1.jpg"
    assert sheet.rows[1].get("images") == ""


def test_repeated_image_columns_merge_and_duplicate_scalar_columns_are_dropped():
    payload = _xlsx(
        [
            ["产品编号", "产品名称", "主图", "图片1", "图片2", "产品名称", "单位", "备注"],
            ["SUNON-001", "人体工学椅", "cover.jpg", "a.jpg", "b.jpg", "重复列", "把", "包安装"],
        ]
    )

    sheet = read_product_sheet(payload)

    assert [c.key for c in sheet.columns] == [
        "product_no",
        "product_name",
        "main_image",
        "images",
        "images",
        "description",
    ]
    # 图片列可以有多列，值按列顺序拼起来，交给上层再拆。
    assert [c.excel_col for c in sheet.image_columns] == [3, 4, 5]
    assert sheet.rows[0].get("images") == "a.jpg,b.jpg"
    assert split_multi(sheet.rows[0].get("images")) == ["a.jpg", "b.jpg"]
    # 同名的普通列只认第一个，后面的进 warnings —— 否则「产品名称」会被那列
    # 手写的备注覆盖掉，而用户完全看不出发生了什么。
    assert sheet.rows[0].get("product_name") == "人体工学椅"
    assert any("产品名称" in w for w in sheet.warnings)
    assert sheet.unknown_headers == ["单位"]


def test_detect_header_row_keeps_the_earliest_of_equally_good_candidates():
    """表中间被人又插了一行表头时取第一行：主图选谁、行号对谁，必须可复现。"""
    frame = pd.DataFrame(
        [
            ["产品编号", "产品名称", "面价"],
            ["SUNON-001", "椅", "1280"],
            ["产品编号", "产品名称", "面价"],
        ]
    )

    assert detect_header_row(frame) == 0


def test_sheets_that_cannot_be_read_fail_loudly_instead_of_importing_garbage():
    with pytest.raises(SheetError, match="未识别到表头行"):
        read_product_sheet(_xlsx([["日期", "数量", "金额"], ["2026-08-01", 3, 99]]))

    # 表头在第 20 行（超出 16 行扫描窗口）：宁可退回，也不要把说明行当表头。
    deep = [[f"填写说明第 {i} 条", None] for i in range(19)]
    deep += [["产品编号", "产品名称"], ["SUNON-001", "椅"]]
    with pytest.raises(SheetError, match="未识别到表头行"):
        read_product_sheet(_xlsx(deep))

    with pytest.raises(SheetError, match="缺少必填列"):
        read_product_sheet(_xlsx([["产品编号", "面价"], ["SUNON-001", "1280"]]))

    with pytest.raises(SheetError, match="文件解析失败"):
        read_product_sheet(b"\xd0\xcf\x11\xe0not-an-xlsx")


def test_parse_row_maps_a_complete_row_and_normalises_enums_and_tags():
    row = ProductRow(
        excel_row=7,
        values={
            "product_no": "SUNON-001",
            "product_name": "人体工学椅",
            "brand_name": "示例品牌",
            "supplier_name": "示例供应商",
            "category_name": "办公椅",
            "face_price": "1,280.00",
            "cost_price": "￥860 元",
            "material": "网布+铝合金",
            "specification": "W650×D620×H1150mm",
            "colors": "黑色,灰色",
            "description": "示例描述",
            "data_source": "2026 供应商报价表",
            "stock_status": "有货",
            "status": "上架",
            "tag_names": "热销, 新品；热销",
        },
    )

    fields = parse_row(row)

    assert fields.ok
    assert (fields.excel_row, fields.product_no) == (7, "SUNON-001")
    assert (fields.face_price, fields.cost_price) == (1280.0, 860.0)
    assert (fields.stock_status, fields.status) == ("in_stock", "active")
    assert fields.completeness_status == "complete"
    assert fields.tag_names == ["热销", "新品"]
    # 这四列老代码从来没导进去过（只认 no/name/price），是这次要补的。
    assert (fields.description, fields.specification) == ("示例描述", "W650×D620×H1150mm")
    assert (fields.colors, fields.data_source) == ("黑色,灰色", "2026 供应商报价表")
    assert fields.notes == []


def test_blank_face_price_becomes_the_placeholder_and_marks_completeness_pending():
    """占位价和 pending 是一体的：模型里有
    ``CheckConstraint("face_price <> 99999 OR completeness_status = 'pending'")``，
    只写一个就是 IntegrityError。留空的面价按占位价进来，是为了让「先把表导进来
    再补价」这条最常见的用法走得通。"""
    blank = parse_row(ProductRow(excel_row=4, values={"product_no": "A", "product_name": "椅"}))

    assert blank.ok
    assert (blank.face_price, blank.completeness_status) == (PLACEHOLDER_PRICE, "pending")
    assert any("待核价" in n for n in blank.notes)

    # 表里明写「待核价」（导出侧就是这么写的）走同一条路；哪怕同一行的完整度列
    # 写着「完整」，也不能把它盖回去 —— 那会直接撞约束。
    stated = parse_row(
        ProductRow(
            excel_row=5,
            values={
                "product_no": "A",
                "product_name": "椅",
                "face_price": "待核价",
                "completeness_status": "完整",
            },
        )
    )

    assert (stated.face_price, stated.completeness_status) == (PLACEHOLDER_PRICE, "pending")


def test_only_unusable_rows_fail_while_the_rest_degrade_with_notes():
    """分界线：进不了库的才算 errors，其余一律降级 + 留一条 note。

    让一行因为库存状态写了「有货的」而整行退回，用户就得改表重导一轮 —— 批量导入
    的效率优势正是这样被磨掉的。
    """
    broken = parse_row(ProductRow(excel_row=9, values={"face_price": "看图议价"}))

    assert not broken.ok
    assert broken.errors == ["产品编号为空", "产品名称为空", "面价无法识别：'看图议价'"]

    degraded = parse_row(
        ProductRow(
            excel_row=10,
            values={
                "product_no": "SUNON-001",
                "product_name": "椅",
                "face_price": "1280",
                "cost_price": "面议",
                "stock_status": "有货的",
                "status": "上上架",
                "specification": "长" * 300,
            },
        )
    )

    assert degraded.ok
    assert (degraded.stock_status, degraded.status) == ("in_stock", "draft")
    # 成本价写「面议」就当没填：成本可空，不值得为它退回整行。
    assert degraded.cost_price is None
    assert degraded.specification is not None and len(degraded.specification) == 255
    assert len(degraded.notes) == 3
    assert any("specification 超过 255 字已截断" in n for n in degraded.notes)
    assert any("stock_status" in n and "有货的" in n for n in degraded.notes)


def test_import_template_can_be_read_back_by_this_parser():
    """模板必须能被自己的导入器读回来。

    Import.vue 里一直写着「请下载模板文件」却从来没有这个下载入口，用户只能照页面上
    那段中文列名说明猜，而老代码只认英文键。模板落地后，列名改了但别名表没跟上会让
    「下载模板→填完→导入」直接报缺列 —— 这条用例就是那种回归的兜底。
    """
    payload = build_import_template()

    sheet = read_product_sheet(payload)

    assert sheet.header_row == 1
    assert sheet.unknown_headers == []
    assert sheet.warnings == []
    assert [c.key for c in sheet.image_columns] == ["main_image", "images", "scene_images"]
    assert {"product_no", "product_name", "face_price", "brand_name", "tag_names"} <= {
        c.key for c in sheet.columns
    }
    assert len(sheet.rows) == 1

    fields = parse_row(sheet.rows[0])

    assert (fields.ok, fields.notes) == (True, [])
    assert (fields.product_no, fields.face_price) == ("SUNON-001", 1280.0)
    assert (fields.stock_status, fields.status) == ("in_stock", "draft")
    assert fields.tag_names == ["热销", "新品"]
    # 说明页也得在：三种给图方式全靠它讲清楚。
    assert "填写说明" in pd.ExcelFile(io.BytesIO(payload)).sheet_names
