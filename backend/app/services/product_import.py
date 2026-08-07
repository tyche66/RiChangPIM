"""批量导入的表格解析层：表头认列、单元格取值、价格/枚举归一、模板生成。

单独拆出来的原因和 ``thumbnails.py`` 一样是可测性：接口层为了 ``get_db`` 必然牵连
``app.core.database``，进不了 ``tests/unit``。本模块只依赖 pandas / openpyxl，是叶子。

为什么要做「表头别名」这件事（而不是继续要求英文列名）：
导出用的是中文表头（``products_export.HEADER_MAP``：产品编号/产品名称/面价…），
而原来的导入只认 ``product_no`` / ``product_name`` / ``face_price`` 这种英文键。
也就是说「导出 → 改几行 → 导回来」这条最常用的路，第一步就报「缺少必填列」。
再加上供应商发来的表用的是「货号/品名/单价」这类叫法，用户只能手工改表头，
批量导入的效率优势直接被抵消。

为什么表头行要扫而不是钉死第一行：
真实报价表第一行往往是「××公司2026年报价单」这种标题，第二、三行才是表头。
``pd.read_excel`` 默认拿第一行当表头，于是所有列都变成 ``Unnamed: N``。

坐标口径：``excel_row`` / ``excel_col`` 都是 1 起（和 ``excel_images`` 一致），
这样内嵌图片的落点能直接和某一行、某一列对上。
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

# 表头往前扫多少行找真正的表头。16 行足够覆盖「标题 + 空行 + 说明 + 表头」这种排版，
# 再多就容易把数据行误认成表头。
MAX_HEADER_SCAN_ROWS = 16

# 面价占位值：模型里有 CheckConstraint("face_price <> 99999 OR completeness_status = 'pending'")，
# 所以填了占位价就必须同时把完整度标成 pending，两者是一体的。
PLACEHOLDER_PRICE = 99999.0

# 每个规范字段的可接受表头写法。第一个元素同时用作导入模板的列名。
# 中文那一列必须覆盖 products_export.HEADER_MAP 的全部取值，否则「导出→改→导回」走不通。
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "product_no": (
        "产品编号",
        "product_no",
        "productno",
        "编号",
        "货号",
        "料号",
        "sku",
        "商品编号",
        "产品编码",
        "itemno",
        "itemcode",
        "model",
    ),
    "product_name": (
        "产品名称",
        "product_name",
        "productname",
        "名称",
        "品名",
        "商品名称",
        "产品",
        "name",
    ),
    "brand_name": ("品牌", "brand_name", "brandname", "brand", "品牌名称", "厂牌"),
    "supplier_name": (
        "供应商",
        "supplier_name",
        "suppliername",
        "supplier",
        "供应商名称",
        "厂商",
        "工厂",
    ),
    "category_name": (
        "分类",
        "category_name",
        "categoryname",
        "category",
        "分类名称",
        "类别",
        "品类",
        "产品分类",
    ),
    "face_price": (
        "面价",
        "face_price",
        "faceprice",
        "价格",
        "单价",
        "零售价",
        "标价",
        "挂牌价",
        "listprice",
        "price",
    ),
    "cost_price": (
        "成本价",
        "cost_price",
        "costprice",
        "成本",
        "采购价",
        "出厂价",
        "供货价",
        "cost",
    ),
    "material": ("材质", "material", "材料", "面料"),
    "specification": ("规格", "specification", "spec", "规格尺寸", "尺寸", "size"),
    "colors": ("颜色", "colors", "color", "可选颜色", "颜色选项"),
    "description": ("描述", "description", "产品描述", "说明", "备注", "remark", "desc"),
    "data_source": ("数据来源", "data_source", "datasource", "来源", "source"),
    "stock_status": ("库存状态", "stock_status", "stockstatus", "库存", "现货状态", "stock"),
    "status": ("状态", "status", "上架状态", "产品状态"),
    "completeness_status": ("完整度状态", "completeness_status", "completenessstatus", "完整度"),
    "tag_names": ("标签", "tag_names", "tagnames", "tags", "标签名称", "tag"),
    "main_image": (
        "主图",
        "main_image",
        "mainimage",
        "主图链接",
        "封面",
        "封面图",
        "产品主图",
        "cover",
        "coverimage",
        "mainimageurl",
    ),
    "images": (
        "产品图",
        "images",
        "image",
        "图片",
        "产品图片",
        "图片链接",
        "附图",
        "细节图",
        "实拍图",
        "imageurls",
    ),
    "scene_images": (
        "场景图",
        "scene_images",
        "sceneimages",
        "sceneimage",
        "场景图片",
        "场景",
        "应用场景图",
        "效果图",
        "使用场景",
        "sceneimageurls",
    ),
}

# 导出会带上、但导入没有意义的列（产品ID 是主键、时间是库里生成的），认出来直接忽略，
# 不进 unknown_headers，免得每次导回来都提示一堆「无法识别的列」。
IGNORED_HEADERS: tuple[str, ...] = (
    "产品id",
    "productid",
    "id",
    "创建时间",
    "createtime",
    "更新时间",
    "updatetime",
    "序号",
    "no",
    "行号",
)

# 三种图片列：主图列只取一张（封面），产品图/场景图列可以有多列（图片1/图片2…）。
IMAGE_KEYS: tuple[str, ...] = ("main_image", "images", "scene_images")
REQUIRED_KEYS: tuple[str, ...] = ("product_no", "product_name")

# 归一化时抹掉的字符：空格（含全角）、下划线、各种括号和标点、必填星号。
# 「产品编号*」「产品 编号」「产品编号（必填）」都要能落到同一个键上。
_STRIP_CHARS = re.compile(r"[\s　_\-—/\\()（）\[\]【】<>《》:：,，.。、;；*#＃'\"]+")
_TRAILING_DIGITS = re.compile(r"[0-9０-９]+$")
# 表头末尾那对括号里通常是给人看的补充说明：「产品名称（必填）」「单价（元/把）」
# 「面价(含税)」。归一化会把括号本身抹掉，但「必填」「元」这些字留在里面就认不出列了，
# 所以匹配之前先把最后一组括号连内容一起摘掉。只摘最后一组、不摘中间的。
_BRACKET_SUFFIX = re.compile(r"[（(\[【][^（(【\[]*[)）】\]]\s*$")


def normalize_header(text: object) -> str:
    """表头文字归一：去标点、去空白、转小写、全角数字转半角。"""
    raw = "" if text is None else str(text)
    normalized = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return _STRIP_CHARS.sub("", normalized).strip().lower()


_ALIAS_INDEX: dict[str, str] = {
    normalize_header(alias): key for key, aliases in HEADER_ALIASES.items() for alias in aliases
}
_IGNORED_INDEX: frozenset[str] = frozenset(normalize_header(item) for item in IGNORED_HEADERS)


def resolve_header(text: object) -> str | None:
    """表头 → 规范字段名。认不出返回 None，命中「该忽略的列」返回空串。

    两层退让：
    * 末尾括号里的说明先摘掉再认一次（「产品名称（必填）」「单价（元）」）。
    * 带序号的图片列（图片1 / 主图2 / scene_image_3）去掉尾数再认 —— 供应商表里
      多图几乎都是这么排的，一列一张。只对图片列做这一步：对「价格2」这种辅助列
      去掉数字会把它当成面价用，宁可报「无法识别」让用户看见。
    """
    canon = normalize_header(text)
    if not canon:
        return None
    if canon in _IGNORED_INDEX:
        return ""
    key = _ALIAS_INDEX.get(canon)
    if key is not None:
        return key

    base = normalize_header(_BRACKET_SUFFIX.sub("", str(text)))
    if base and base != canon:
        if base in _IGNORED_INDEX:
            return ""
        key = _ALIAS_INDEX.get(base)
        if key is not None:
            return key
    else:
        base = canon

    stripped = _TRAILING_DIGITS.sub("", base)
    if stripped != base:
        key = _ALIAS_INDEX.get(stripped)
        if key in IMAGE_KEYS:
            return key
    return None


def cell_text(value: object) -> str:
    """单元格 → 字符串，空值统一成 ""。

    ``float`` 那个分支是必须的：一列产品编号里只要有一个空格，pandas 就把整列
    推成 float64，``str(100234.0)`` 变成 ``"100234.0"`` —— 编号凭空多个小数点，
    去重和「编号已存在」全部失灵。
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return repr(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


# 「这个价还没定」的各种写法。命中就写占位价 99999 + completeness_status=pending，
# 和导出侧（face_price == 99999 时导出成「待核价」）对称，保证导出→导回不丢信息。
PLACEHOLDER_PRICE_WORDS: frozenset[str] = frozenset(
    {
        "待核价",
        "待定",
        "待报价",
        "面议",
        "电议",
        "询价",
        "另议",
        "tbd",
        "na",
        "n/a",
        "-",
        "--",
        "?",
        "？",
    }
)
# 去掉货币符号、千分位和「元/个」这类单位后再 float()。留着不管就是整单 500。
_PRICE_NOISE = re.compile(r"[¥￥$＄,，\s　]|/.*$|元.*$|rmb", re.IGNORECASE)


@dataclass(frozen=True)
class Price:
    value: float | None
    placeholder: bool = False
    error: str | None = None


def parse_price(text: object, *, field_label: str = "面价") -> Price:
    """解析价格。空 → value=None；「待核价」类 → 占位价；解不动 → 带原因返回。

    原实现是 ``float(row.get("face_price", 0))``：导出的「待核价」再导回去直接
    ValueError，而它没有 try —— 一行脏数据让整份导入 500，前面几百行也一起没了。
    这里把「解不动」降级成行级失败原因。
    """
    raw = cell_text(text)
    if not raw:
        return Price(value=None)
    if raw.lower() in PLACEHOLDER_PRICE_WORDS:
        return Price(value=PLACEHOLDER_PRICE, placeholder=True)
    cleaned = _PRICE_NOISE.sub("", raw)
    try:
        value = float(cleaned)
    except ValueError:
        return Price(value=None, error=f"{field_label}无法识别：'{raw}'")
    if math.isnan(value) or math.isinf(value):
        return Price(value=None, error=f"{field_label}无法识别：'{raw}'")
    if value < 0:
        return Price(value=None, error=f"{field_label}不能为负数：'{raw}'")
    if value == PLACEHOLDER_PRICE:
        # 有人手填 99999，按占位价处理，否则会撞 check_product_placeholder_price 约束。
        return Price(value=PLACEHOLDER_PRICE, placeholder=True)
    return Price(value=value)


# 枚举列的中英文取值。库里是 CheckConstraint 卡着的，认不出的写法必须落到默认值，
# 不能原样塞进去 —— 那会变成 IntegrityError，行级失败原因还是一坨 SQL。
STOCK_STATUS_ALIASES: dict[str, str] = {
    "instock": "in_stock",
    "有货": "in_stock",
    "现货": "in_stock",
    "在库": "in_stock",
    "有库存": "in_stock",
    "充足": "in_stock",
    "是": "in_stock",
    "outofstock": "out_of_stock",
    "无货": "out_of_stock",
    "缺货": "out_of_stock",
    "售罄": "out_of_stock",
    "无库存": "out_of_stock",
    "断货": "out_of_stock",
    "否": "out_of_stock",
    "preorder": "preorder",
    "预售": "preorder",
    "预订": "preorder",
    "订货": "preorder",
    "期货": "preorder",
    "unknown": "unknown",
    "未知": "unknown",
    "待确认": "unknown",
}
STATUS_ALIASES: dict[str, str] = {
    "active": "active",
    "上架": "active",
    "启用": "active",
    "在售": "active",
    "正常": "active",
    "inactive": "inactive",
    "下架": "inactive",
    "停用": "inactive",
    "停售": "inactive",
    "draft": "draft",
    "草稿": "draft",
    "待发布": "draft",
}
COMPLETENESS_ALIASES: dict[str, str] = {
    "complete": "complete",
    "完整": "complete",
    "已完善": "complete",
    "pending": "pending",
    "待完善": "pending",
    "待补充": "pending",
    "unknown": "unknown",
    "未知": "unknown",
}


def normalize_enum(text: object, aliases: dict[str, str], default: str) -> tuple[str, str | None]:
    """枚举归一，返回 (取值, 提示)。认不出就用默认值并给一条行级提示。"""
    raw = cell_text(text)
    if not raw:
        return default, None
    resolved = aliases.get(normalize_header(raw))
    if resolved is None:
        return default, f"'{raw}' 不是可识别的取值，已按默认值 {default} 处理"
    return resolved, None


# 一格里塞多个值时的分隔符：中英文逗号/分号/竖线/换行。
# 不用空格分隔：文件名和 URL 里出现空格太常见，按空格切会把一个值切碎。
_MULTI_SEP = re.compile(r"[,，;；|\r\n\t]+")


def split_multi(text: object) -> list[str]:
    """把「a, b; c」拆成 [a, b, c]，顺序保留、去重、丢空值。"""
    raw = cell_text(text)
    if not raw:
        return []
    out: list[str] = []
    for piece in _MULTI_SEP.split(raw):
        item = piece.strip()
        if item and item not in out:
            out.append(item)
    return out


@dataclass(frozen=True)
class SheetColumn:
    key: str  # 规范字段名
    header: str  # 表里的原始表头文字，报错时回显给用户
    position: int  # DataFrame 列下标（0 起）
    excel_col: int  # Excel 列号（1 起），内嵌图片按这个对列


@dataclass
class ProductRow:
    excel_row: int  # Excel 行号（1 起）
    values: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str:
        return self.values.get(key, "")


@dataclass
class ProductSheet:
    header_row: int  # 表头所在 Excel 行号（1 起）
    columns: list[SheetColumn]
    rows: list[ProductRow]
    unknown_headers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blank_rows: int = 0

    def has(self, key: str) -> bool:
        return any(column.key == key for column in self.columns)

    def columns_for(self, key: str) -> list[SheetColumn]:
        return [column for column in self.columns if column.key == key]

    @property
    def image_columns(self) -> list[SheetColumn]:
        return [column for column in self.columns if column.key in IMAGE_KEYS]

    @property
    def first_data_row(self) -> int:
        return self.header_row + 1


class SheetError(Exception):
    """表格连「哪行是表头、必填列在哪」都定不下来，只能整单退回。"""


def detect_header_row(frame: pd.DataFrame) -> int:
    """在前若干行里找表头行，返回 DataFrame 行下标（0 起）。

    评分规则：认得出的列越多越好，且必须至少含 product_no 或 product_name ——
    只按「认得出几列」选，会把带「单价」「备注」的小计行误判成表头。
    """
    best_index = -1
    best_score = 0
    limit = min(len(frame), MAX_HEADER_SCAN_ROWS)
    for index in range(limit):
        keys = {resolve_header(value) for value in frame.iloc[index].tolist()}
        keys.discard(None)
        keys.discard("")
        if not keys & set(REQUIRED_KEYS):
            continue
        if len(keys) > best_score:
            best_index, best_score = index, len(keys)
    if best_index < 0:
        raise SheetError(
            "未识别到表头行：至少需要一列「产品编号」和一列「产品名称」（英文列名 "
            "product_no / product_name 同样可以）。可先下载导入模板。"
        )
    return best_index


def read_product_sheet(xlsx_bytes: bytes) -> ProductSheet:
    """读第一张表并按规范字段整理成行。

    整表以 ``header=None`` 读进来（不让 pandas 自己认表头），原因有两个：表头行
    未必是第一行；以及我们要的是「Excel 行号」这个绝对坐标，好让内嵌图片按行列
    对上产品，pandas 自己认表头时行号偏移多少取决于它跳了几行，不可控。
    """
    try:
        frame = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=0, header=None, dtype=object)
    except Exception as exc:  # pandas 会抛各式各样的解析错，统一成一条人话
        raise SheetError(f"文件解析失败：{exc}") from exc
    if frame.empty:
        raise SheetError("表格是空的，没有可导入的数据行")

    header_index = detect_header_row(frame)
    columns: list[SheetColumn] = []
    unknown: list[str] = []
    warnings: list[str] = []
    seen_scalar: set[str] = set()
    for position, value in enumerate(frame.iloc[header_index].tolist()):
        header = cell_text(value)
        if not header:
            continue
        key = resolve_header(value)
        if key is None:
            unknown.append(header)
            continue
        if not key:
            continue
        if key not in IMAGE_KEYS:
            if key in seen_scalar:
                warnings.append(f"列「{header}」和前面的同名列重复，已忽略后者")
                continue
            seen_scalar.add(key)
        columns.append(
            SheetColumn(key=key, header=header, position=position, excel_col=position + 1)
        )

    missing = [key for key in REQUIRED_KEYS if not any(c.key == key for c in columns)]
    if missing:
        raise SheetError(f"缺少必填列：{'、'.join(missing)}")

    rows: list[ProductRow] = []
    blank = 0
    for offset in range(header_index + 1, len(frame)):
        record = frame.iloc[offset]
        values: dict[str, str] = {}
        for column in columns:
            text = cell_text(record.iloc[column.position])
            if not text:
                continue
            # 图片列可能有多列，同键的值按列顺序拼起来，交给上层再拆。
            if column.key in values:
                values[column.key] = f"{values[column.key]},{text}"
            else:
                values[column.key] = text
        if not values:
            blank += 1
            continue
        rows.append(ProductRow(excel_row=offset + 1, values=values))

    return ProductSheet(
        header_row=header_index + 1,
        columns=columns,
        rows=rows,
        unknown_headers=unknown,
        warnings=warnings,
        blank_rows=blank,
    )


@dataclass
class RowFields:
    """一行解析完的产品字段（还没查库，所以品牌/供应商/分类仍是名字）。"""

    excel_row: int
    product_no: str = ""
    product_name: str = ""
    brand_name: str = ""
    supplier_name: str = ""
    category_name: str = ""
    face_price: float | None = None
    cost_price: float | None = None
    material: str | None = None
    specification: str | None = None
    colors: str | None = None
    description: str | None = None
    data_source: str | None = None
    stock_status: str = "in_stock"
    status: str = "draft"
    completeness_status: str = "complete"
    tag_names: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# 文本字段的库内长度上限（models/product.py），超了直接截断并提示：
# 一个 300 字的产品名让整行失败太亏，用户要的是「先进来再改」。
_TEXT_LIMITS: dict[str, int] = {
    "product_no": 64,
    "product_name": 255,
    "material": 128,
    "specification": 255,
    "data_source": 512,
}


def parse_row(row: ProductRow) -> RowFields:
    """把一行文本按字段规则解析成入库用的值，问题都记在 errors / notes 里。

    只有「没编号、没名称、价格解不动」才算 errors（这行确实进不去）；枚举写错、
    文本超长都归 notes 并降级处理 —— 批量导入里让一行因为库存状态写了「有货的」
    而整行退回，用户得反复来回改表。
    """
    out = RowFields(excel_row=row.excel_row)
    out.product_no = row.get("product_no")
    out.product_name = row.get("product_name")
    if not out.product_no:
        out.errors.append("产品编号为空")
    if not out.product_name:
        out.errors.append("产品名称为空")
    out.brand_name = row.get("brand_name")
    out.supplier_name = row.get("supplier_name")
    out.category_name = row.get("category_name")

    price = parse_price(row.get("face_price"))
    if price.error:
        out.errors.append(price.error)
    elif price.value is None:
        out.face_price = PLACEHOLDER_PRICE
        out.completeness_status = "pending"
        out.notes.append("面价为空，已按待核价（99999）导入并标记为待补充")
    else:
        out.face_price = price.value
        if price.placeholder:
            out.completeness_status = "pending"

    cost = parse_price(row.get("cost_price"), field_label="成本价")
    if cost.error:
        out.notes.append(cost.error + "，已留空")
    elif not cost.placeholder:
        out.cost_price = cost.value

    for key in ("material", "specification", "colors", "description", "data_source"):
        text = row.get(key)
        limit = _TEXT_LIMITS.get(key)
        if limit and len(text) > limit:
            out.notes.append(f"{key} 超过 {limit} 字已截断")
            text = text[:limit]
        setattr(out, key, text or None)

    for key, aliases, default in (
        ("stock_status", STOCK_STATUS_ALIASES, "in_stock"),
        ("status", STATUS_ALIASES, "draft"),
    ):
        value, note = normalize_enum(row.get(key), aliases, default)
        setattr(out, key, value)
        if note:
            out.notes.append(f"{key}: {note}")

    if row.get("completeness_status") and out.completeness_status != "pending":
        value, note = normalize_enum(
            row.get("completeness_status"), COMPLETENESS_ALIASES, "complete"
        )
        out.completeness_status = value
        if note:
            out.notes.append(f"completeness_status: {note}")

    out.tag_names = split_multi(row.get("tag_names"))
    for key in ("product_no", "product_name"):
        limit = _TEXT_LIMITS[key]
        value = getattr(out, key)
        if len(value) > limit:
            out.notes.append(f"{key} 超过 {limit} 字已截断")
            setattr(out, key, value[:limit])
    return out


# 模板列顺序照着导出走（products_export.HEADER_MAP），最后补三列图片。
# 这样「导出 → 改 → 导回」和「下载模板 → 填 → 导入」是同一套列名，用户只需要记一套。
TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("产品编号*", "SUNON-001"),
    ("产品名称*", "人体工学办公椅"),
    ("面价*", "1280"),
    ("品牌", "示例品牌"),
    ("供应商", "示例供应商"),
    ("分类", "办公椅"),
    ("成本价", "860"),
    ("材质", "网布+铝合金"),
    ("规格", "W650×D620×H1150mm"),
    ("颜色", "黑色,灰色"),
    ("描述", "示例描述，可留空"),
    ("数据来源", "2026 供应商报价表"),
    ("库存状态", "有货"),
    ("状态", "草稿"),
    ("标签", "热销,新品"),
    ("主图", "把图片直接贴进这一格，或填 chair-1.jpg / https://…"),
    ("产品图", "chair-2.jpg,chair-3.jpg"),
    ("场景图", "office-scene.jpg"),
)

TEMPLATE_NOTES: tuple[str, ...] = (
    "【必填列】产品编号、产品名称、面价。其余列可以整列删掉。",
    (
        "【列名】中文、英文（product_no / product_name / face_price …）都认；"
        "也认「货号/品名/单价」这类常见叫法。表头不必是第一行，标题行可以留着。"
    ),
    (
        "【品牌/供应商/分类】必须是系统里已存在的名称，不存在的行会失败并给出原因；"
        "三列都留空时该行也会失败（库里这三个是必填外键）。"
    ),
    (
        "【面价】支持「1,280.00」「1280元」这类写法；"
        "填「待核价/面议/待定」或留空会按占位价 99999 导入，并把完整度标成「待补充」。"
    ),
    (
        "【图片·方式一（推荐）】直接把图片贴进「主图/产品图/场景图」那一格："
        "WPS 的「嵌入单元格」、Excel 365 的「置于单元格内」、"
        "以及压在该行上的浮动图片都能识别。"
    ),
    (
        "【图片·方式二】把 xlsx 和图片文件一起打成 .zip 上传，"
        "格中填图片文件名（chair-1.jpg）。也支持不写文件名 —— "
        "文件名以产品编号开头的图片（SUNON-001.jpg / SUNON-001_2.jpg）会自动归到该产品，"
        "名字里带「场景/scene」的进场景图。"
    ),
    "【图片·方式三】格里填 http(s) 图片直链（需要管理员开启外链抓取）。",
    "【主图】主图列的第一张图会设为封面；没有主图列时，该行最靠左的产品图作封面。",
    "【场景图】多行填同一张场景图时只会入库一份，并同时关联到这些产品上。",
    (
        "【重复编号】默认整行失败；勾选「跳过已存在的产品编号」时跳过并计入失败明细"
        "（原因写「已跳过」）。"
    ),
    "【一行失败不影响其它行】每行独立提交，失败明细里会给出行号、编号和原因。",
)


def build_import_template() -> bytes:
    """生成导入模板 xlsx（含示例行和填写说明页）。

    Import.vue 里一直写着「请下载模板文件」，但从来没有这个下载入口，用户只能靠
    页面上那段列名说明猜 —— 而那段说明写的是中文列名，老代码只认英文键。模板落地
    之后这个歧义才算真的消掉。

    只写文字，不写图片：openpyxl 写图片同样要 Pillow（条件依赖），模板不能依赖它。
    """
    headers = [name for name, _ in TEMPLATE_COLUMNS]
    sample = [value for _, value in TEMPLATE_COLUMNS]
    products = pd.DataFrame([sample], columns=headers)
    notes = pd.DataFrame({"填写说明": list(TEMPLATE_NOTES)})

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        products.to_excel(writer, index=False, sheet_name="产品")
        notes.to_excel(writer, index=False, sheet_name="填写说明")
        # 列宽给够：默认 8 字符宽的模板，用户第一眼看到的是一排 ####。
        sheet = writer.sheets["产品"]
        for position, name in enumerate(headers, start=1):
            width = 42 if resolve_header(name) in IMAGE_KEYS else max(12, len(name) * 2 + 4)
            sheet.column_dimensions[sheet.cell(row=1, column=position).column_letter].width = width
        writer.sheets["填写说明"].column_dimensions["A"].width = 120
    return output.getvalue()
