"""从 xlsx 里把「嵌在单元格上的图片」抠出来，并定位到第几行第几列。

为什么要自己解 zip，而不是用 openpyxl：

1. openpyxl 读图必须有 Pillow。``Reader.find_images()`` 在 ``PILLOW is False``
   时直接 ``return charts, []`` —— 不报错，**静默丢掉所有图**。requirements.txt
   里 Pillow 带 ``; python_version < '3.13'`` 标记（10.2.0 在 3.13+ 没轮子），
   宿主机上 pytest 环境就是没有 Pillow 的，用 openpyxl 会得到「导入成功 0 张图」
   这种最难查的结果。
2. openpyxl 只认标准 drawing 锚点这一种形态。国内供应商发来的报价表大量是 WPS
   存的 ``DISPIMG``（图片在 ``xl/cellimages.xml``，单元格里只有个公式），还有
   Microsoft 365 的「置于单元格内」（richValue，单元格里只有个 ``vm`` 属性）。
   这两种在 openpyxl 眼里都是「没有图片」。
3. 我们要的不只是图片字节，还要「这张图属于哪一行、哪一列」—— 行决定它归哪个
   产品，列决定它是主图还是场景图。openpyxl 的 ``ws._images`` 只给锚点对象，
   另外两种形态压根拿不到坐标。

所以这里只用 stdlib（zipfile + ElementTree）。附带好处：本模块是叶子模块，
不 import ``app.main`` / ``app.core.database``，符合 ``tests/unit/conftest.py``
的单元测试约定，三种形态都能用手搓的 xlsx 夹具在单元层钉住。

坐标一律用 1 起的 Excel 行列号（A1 = row 1, col 1），和 pandas 的 0 起下标差 1，
调用方自己换算，避免两套口径混在一起。
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

# OOXML 命名空间。这些串是格式规范的一部分，写死比动态嗅探可靠。
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/main"
# WPS 的 cellimages.xml 用自己的根命名空间，但里面的 xdr:pic / a:blip 是标准的。
NS_XLRD = "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata"

REL_IMAGE = f"{NS_REL}/image"
REL_DRAWING = f"{NS_REL}/drawing"

# 只认这几种真正能进素材库的格式。魔数嗅探而不是看扩展名：Excel 里 media 目录
# 的文件名是它自己造的（image1.png），改过扩展名的 jpg 很常见。
_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpeg", "image/jpeg"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
    (b"BM", "bmp", "image/bmp"),
    (b"II*\x00", "tiff", "image/tiff"),
    (b"MM\x00*", "tiff", "image/tiff"),
    (b"\xd7\xcd\xc6\x9a", "wmf", "image/wmf"),
    (b"\x01\x00\x00\x00", "emf", "image/emf"),
)


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """按魔数判断 (扩展名, content_type)，认不出返回 None。"""
    if len(data) < 12:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    for magic, ext, content_type in _SIGNATURES:
        if data.startswith(magic):
            return ext, content_type
    return None


@dataclass(frozen=True)
class EmbeddedImage:
    """一张从工作簿里抠出来的图，带它在表格里的落点。

    ``row`` / ``col`` 是 1 起的 Excel 坐标，指图片左上角所在的单元格。
    ``row_end`` / ``col_end`` 是右下角（twoCellAnchor 才有），用来判断一张浮动图
    是否压在表头上 —— 供应商表里常见把图画得比单元格大、顶到表头行里去。
    ``order`` 是同一坐标下的稳定次序（决定谁当封面），跨形态全局递增。
    """

    data: bytes
    ext: str
    content_type: str
    source: str  # anchor | dispimg | richvalue
    order: int
    row: int | None = None
    col: int | None = None
    row_end: int | None = None
    col_end: int | None = None
    name: str = ""


@dataclass(frozen=True)
class _Rel:
    target: str  # 解析成绝对包内路径（不带前导斜杠），External 的话留原样
    type: str
    external: bool


def _rels_path(part: str) -> str:
    folder, base = posixpath.split(part)
    return posixpath.join(folder, "_rels", base + ".rels")


def _resolve(base_part: str, target: str) -> str:
    """把 rels 里的相对 Target 解析成包内绝对路径。

    Target 是相对于**引用它的部件所在目录**的，不是相对于包根。踩过的坑：
    ``xl/_rels/cellimages.xml.rels`` 里写的是 ``media/image1.png``，base 是 ``xl``，
    真实路径是 ``xl/media/image1.png``；而 ``xl/drawings/_rels/*.rels`` 里同样写
    ``../media/image1.png``，base 是 ``xl/drawings``。两者都得靠 normpath 收敛。
    """
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_part), target))


def _load_rels(zf: zipfile.ZipFile, part: str, names: set[str]) -> dict[str, _Rel]:
    path = _rels_path(part)
    if path not in names:
        return {}
    try:
        root = ET.fromstring(zf.read(path))
    except ET.ParseError:
        return {}
    out: dict[str, _Rel] = {}
    for rel in root.findall(f"{{{NS_PKG_REL}}}Relationship"):
        rid = rel.get("Id")
        target = rel.get("Target") or ""
        if not rid or not target:
            continue
        external = (rel.get("TargetMode") or "") == "External"
        out[rid] = _Rel(
            target=target if external else _resolve(part, target),
            type=rel.get("Type") or "",
            external=external,
        )
    return out


_CELL_REF = re.compile(r"^([A-Za-z]+)(\d+)$")


def column_to_index(letters: str) -> int:
    """``A`` → 1，``AA`` → 27。"""
    value = 0
    for char in letters.upper():
        value = value * 26 + (ord(char) - 64)
    return value


def parse_cell_ref(ref: str) -> tuple[int, int] | None:
    """``C7`` → (7, 3)。认不出返回 None。"""
    matched = _CELL_REF.match((ref or "").strip())
    if not matched:
        return None
    return int(matched.group(2)), column_to_index(matched.group(1))


def _sheet_part(zf: zipfile.ZipFile, names: set[str], sheet_index: int) -> str | None:
    """定位第 N 个工作表的 xml 部件路径。

    必须按 ``xl/workbook.xml`` 里 ``<sheets>`` 的**声明顺序**取，不能按 zip 里
    sheet1/sheet2 的文件名排序 —— 另存过的表里 sheet3.xml 排在第一位是常事，
    而 pandas 的 ``sheet_name=0`` 取的是声明顺序的第一张，两边必须对齐，否则
    图和数据会错到不同的表上。
    """
    if "xl/workbook.xml" not in names:
        return None
    try:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
    except ET.ParseError:
        return None
    sheets = root.findall(f"{{{NS_MAIN}}}sheets/{{{NS_MAIN}}}sheet")
    if not 0 <= sheet_index < len(sheets):
        return None
    rid = sheets[sheet_index].get(f"{{{NS_REL}}}id")
    rels = _load_rels(zf, "xl/workbook.xml", names)
    rel = rels.get(rid or "")
    if rel and not rel.external and rel.target in names:
        return rel.target
    # 少数生成器不写 workbook rels，退回按文件名猜。
    guess = f"xl/worksheets/sheet{sheet_index + 1}.xml"
    return guess if guess in names else None


def _blips(node: ET.Element) -> list[str]:
    """取一个节点下所有 ``a:blip@r:embed``（分组图形里会有多张）。"""
    out = []
    for blip in node.iter(f"{{{NS_DRAW}}}blip"):
        rid = blip.get(f"{{{NS_REL}}}embed")
        if rid:
            out.append(rid)
    return out


def _pic_name(node: ET.Element) -> str:
    for prop in node.iter(f"{{{NS_XDR}}}cNvPr"):
        return prop.get("descr") or prop.get("name") or ""
    return ""


class _MediaReader:
    """读 xl/media 下的字节并组装 ``EmbeddedImage``。

    存在的意义有三个：字节按部件路径缓存（WPS 里同一张图会被多个单元格引用，
    不缓存就重复解压）；``order`` 全局单调递增（跨三种形态统一排序，封面选谁才
    是确定的）；单张体积上限在这里卡掉，避免一份表里塞几十张 20MB 原图直接把
    进程内存打爆。
    """

    def __init__(self, zf: zipfile.ZipFile, names: set[str], max_bytes: int) -> None:
        self._zf = zf
        self._names = names
        self._max_bytes = max_bytes
        self._cache: dict[str, tuple[bytes, str, str] | None] = {}
        self._order = 0
        self.oversized: list[str] = []
        self.unknown_format: list[str] = []

    def _read(self, part: str) -> tuple[bytes, str, str] | None:
        if part in self._cache:
            return self._cache[part]
        result: tuple[bytes, str, str] | None = None
        if part in self._names:
            info = self._zf.getinfo(part)
            if info.file_size > self._max_bytes:
                self.oversized.append(posixpath.basename(part))
            else:
                data = self._zf.read(part)
                sniffed = sniff_image(data)
                if sniffed is None:
                    self.unknown_format.append(posixpath.basename(part))
                else:
                    result = (data, sniffed[0], sniffed[1])
        self._cache[part] = result
        return result

    def build(self, part: str, *, source: str, name: str = "", **coords: int | None):
        payload = self._read(part)
        if payload is None:
            return None
        data, ext, content_type = payload
        self._order += 1
        return EmbeddedImage(
            data=data,
            ext=ext,
            content_type=content_type,
            source=source,
            order=self._order,
            name=name or posixpath.basename(part),
            **coords,  # type: ignore[arg-type]
        )


def _anchor_cell(anchor: ET.Element, tag: str) -> tuple[int | None, int | None]:
    node = anchor.find(f"{{{NS_XDR}}}{tag}")
    if node is None:
        return None, None
    row = node.findtext(f"{{{NS_XDR}}}row")
    col = node.findtext(f"{{{NS_XDR}}}col")
    return (
        int(row) + 1 if row is not None and row.strip().isdigit() else None,
        int(col) + 1 if col is not None and col.strip().isdigit() else None,
    )


def _extract_anchored(
    zf: zipfile.ZipFile,
    names: set[str],
    sheet: str,
    sheet_root: ET.Element,
    media: _MediaReader,
) -> list[EmbeddedImage]:
    """形态一：标准浮动图（Excel「插入图片」，openpyxl 也只认这种）。

    链路：sheet.xml ``<drawing r:id>`` → worksheets/_rels → xl/drawings/drawingN.xml
    → 每个 anchor 的 ``xdr:from`` 给坐标、``a:blip@r:embed`` 给图 → drawings/_rels
    → xl/media/*。
    """
    out: list[EmbeddedImage] = []
    sheet_rels = _load_rels(zf, sheet, names)
    for node in sheet_root.iter(f"{{{NS_MAIN}}}drawing"):
        rel = sheet_rels.get(node.get(f"{{{NS_REL}}}id") or "")
        if rel is None or rel.external or rel.target not in names:
            continue
        drawing_rels = _load_rels(zf, rel.target, names)
        try:
            drawing_root = ET.fromstring(zf.read(rel.target))
        except ET.ParseError:
            continue
        for anchor in list(drawing_root):
            local = anchor.tag.rsplit("}", 1)[-1]
            if not local.endswith("Anchor"):
                continue
            row, col = _anchor_cell(anchor, "from")
            row_end, col_end = _anchor_cell(anchor, "to")
            pics = list(anchor.iter(f"{{{NS_XDR}}}pic")) or [anchor]
            for pic in pics:
                for rid in _blips(pic):
                    media_rel = drawing_rels.get(rid)
                    if media_rel is None or media_rel.external:
                        continue
                    image = media.build(
                        media_rel.target,
                        source="anchor",
                        row=row,
                        col=col,
                        row_end=row_end,
                        col_end=col_end,
                        name=_pic_name(pic),
                    )
                    if image is not None:
                        out.append(image)
    return out


@dataclass(frozen=True)
class _Cell:
    row: int
    col: int
    text: str
    vm: str | None


def _shared_strings(zf: zipfile.ZipFile, names: set[str]) -> list[str]:
    if "xl/sharedStrings.xml" not in names:
        return []
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except ET.ParseError:
        return []
    return ["".join(item.itertext()) for item in root.findall(f"{{{NS_MAIN}}}si")]


def _scan_cells(sheet_root: ET.Element, shared: list[str]) -> list[_Cell]:
    """把工作表里「有公式或有 vm 标记」的单元格扫出来。

    只留这两类：DISPIMG 的图片 ID 藏在公式里，M365 单元格图片靠 ``vm`` 指向
    metadata。纯数据格没必要留，一张几千行的表全留下来是白占内存。
    """
    cells: list[_Cell] = []
    for cell in sheet_root.iter(f"{{{NS_MAIN}}}c"):
        vm = cell.get("vm")
        formula = cell.find(f"{{{NS_MAIN}}}f")
        if vm is None and formula is None:
            continue
        coord = parse_cell_ref(cell.get("r") or "")
        if coord is None:
            continue
        parts = []
        if formula is not None:
            parts.append("".join(formula.itertext()))
        if cell.get("t") == "s":
            index = (cell.findtext(f"{{{NS_MAIN}}}v") or "").strip()
            if index.isdigit() and int(index) < len(shared):
                parts.append(shared[int(index)])
        else:
            inline = cell.find(f"{{{NS_MAIN}}}is")
            parts.append(
                "".join(inline.itertext())
                if inline is not None
                else (cell.findtext(f"{{{NS_MAIN}}}v") or "")
            )
        cells.append(_Cell(row=coord[0], col=coord[1], text=" ".join(parts), vm=vm))
    return cells


# WPS 的图片 ID 形如 ID_2C2C7D6B6E0F4A8F9E1D...，公式是 _xlfn.DISPIMG("ID_...",1)。
_DISPIMG_ID = re.compile(r"ID_[0-9A-Za-z]{8,}")


def _extract_dispimg(
    zf: zipfile.ZipFile, names: set[str], cells: list[_Cell], media: _MediaReader
) -> list[EmbeddedImage]:
    """形态二：WPS 的「嵌入单元格图片」（DISPIMG）。

    国内供应商发来的报价表十有八九是这种：单元格里只有个
    ``=_xlfn.DISPIMG("ID_xxx",1)`` 公式，图片实体全塞在 ``xl/cellimages.xml``，
    靠 ``xdr:cNvPr@name`` 里的那个 ID 对应。openpyxl 完全看不见它们。

    坐标直接就是公式所在单元格，比浮动图的锚点还准。
    """
    if "xl/cellimages.xml" not in names:
        return []
    try:
        root = ET.fromstring(zf.read("xl/cellimages.xml"))
    except ET.ParseError:
        return []
    rels = _load_rels(zf, "xl/cellimages.xml", names)
    by_id: dict[str, str] = {}
    for pic in root.iter(f"{{{NS_XDR}}}pic"):
        image_id = ""
        for prop in pic.iter(f"{{{NS_XDR}}}cNvPr"):
            image_id = (prop.get("name") or "").strip()
            break
        blips = _blips(pic)
        if not image_id or not blips:
            continue
        rel = rels.get(blips[0])
        if rel is not None and not rel.external:
            by_id[image_id] = rel.target
    if not by_id:
        return []
    out: list[EmbeddedImage] = []
    for cell in cells:
        for image_id in _DISPIMG_ID.findall(cell.text):
            part = by_id.get(image_id)
            if part is None:
                continue
            image = media.build(part, source="dispimg", row=cell.row, col=cell.col, name=image_id)
            if image is not None:
                out.append(image)
    return out


def _iter_local(node: ET.Element, name: str):
    """按 local-name 遍历，忽略命名空间。

    richData 那几个部件的命名空间带版本号（richdata / richdata2 / …），微软换过
    好几轮，写死前缀就是给自己埋雷；这条链上一律按 local-name 匹配。
    """
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] == name:
            yield child


def _rich_value_parts(zf: zipfile.ZipFile, names: set[str]) -> list[str | None]:
    """rdrichvalue.xml 里第 i 个富值 → 对应的 media 部件路径。"""
    rel_parts: list[str | None] = []
    if "xl/richData/richValueRel.xml" in names:
        try:
            root = ET.fromstring(zf.read("xl/richData/richValueRel.xml"))
        except ET.ParseError:
            root = None
        if root is not None:
            rels = _load_rels(zf, "xl/richData/richValueRel.xml", names)
            for rel_node in _iter_local(root, "rel"):
                rel = rels.get(rel_node.get(f"{{{NS_REL}}}id") or "")
                rel_parts.append(None if rel is None or rel.external else rel.target)
    if not rel_parts:
        return []

    # 结构表告诉我们「图片下标」是 rv 的第几个 <v>：_localImage 结构通常是
    # (_rvRel:LocalImageIdentifier, CalcOrigin, Text?)，但顺序不保证，得按 key 名找。
    slots: dict[int, int] = {}
    if "xl/richData/rdrichvaluestructure.xml" in names:
        try:
            struct_root = ET.fromstring(zf.read("xl/richData/rdrichvaluestructure.xml"))
        except ET.ParseError:
            struct_root = None
        if struct_root is not None:
            for index, structure in enumerate(_iter_local(struct_root, "s")):
                for slot, key in enumerate(_iter_local(structure, "k")):
                    if (key.get("n") or "").endswith("LocalImageIdentifier"):
                        slots[index] = slot
                        break

    out: list[str | None] = []
    if "xl/richData/rdrichvalue.xml" not in names:
        return out
    try:
        value_root = ET.fromstring(zf.read("xl/richData/rdrichvalue.xml"))
    except ET.ParseError:
        return out
    for value in _iter_local(value_root, "rv"):
        raw = (value.get("s") or "0").strip()
        slot = slots.get(int(raw) if raw.isdigit() else 0, 0)
        texts = [(node.text or "").strip() for node in _iter_local(value, "v")]
        if slot >= len(texts) or not texts[slot].isdigit():
            out.append(None)
            continue
        index = int(texts[slot])
        out.append(rel_parts[index] if index < len(rel_parts) else None)
    return out


def _value_metadata_map(zf: zipfile.ZipFile, names: set[str]) -> dict[int, int]:
    """单元格的 ``vm="N"`` → rdrichvalue.xml 里第几个富值（0 起）。

    链路：``vm`` 是 1 起下标，指向 metadata.xml 的 ``valueMetadata/bk``；bk 里
    ``rc@t`` 是 1 起下标指向 ``metadataTypes``（要的是名字叫 XLRICHVALUE 的那个），
    ``rc@v`` 是 0 起下标指向同名 ``futureMetadata`` 的 bk；那个 bk 里的
    ``xlrd:rvb@i`` 才是富值下标。
    """
    if "xl/metadata.xml" not in names:
        return {}
    try:
        root = ET.fromstring(zf.read("xl/metadata.xml"))
    except ET.ParseError:
        return {}
    type_names = [node.get("name") or "" for node in root.findall(f"{{{NS_MAIN}}}metadataTypes/*")]
    future: dict[str, list[int | None]] = {}
    for block in root.findall(f"{{{NS_MAIN}}}futureMetadata"):
        indexes: list[int | None] = []
        for bk in block.findall(f"{{{NS_MAIN}}}bk"):
            found: int | None = None
            for rvb in _iter_local(bk, "rvb"):
                raw = (rvb.get("i") or "").strip()
                found = int(raw) if raw.isdigit() else None
                break
            indexes.append(found)
        future[block.get("name") or ""] = indexes

    out: dict[int, int] = {}
    for position, bk in enumerate(root.findall(f"{{{NS_MAIN}}}valueMetadata/{{{NS_MAIN}}}bk"), 1):
        rc = bk.find(f"{{{NS_MAIN}}}rc")
        if rc is None:
            continue
        type_index = (rc.get("t") or "").strip()
        value_index = (rc.get("v") or "").strip()
        if not type_index.isdigit() or not value_index.isdigit():
            continue
        slot = int(type_index) - 1
        name = type_names[slot] if 0 <= slot < len(type_names) else ""
        indexes = future.get(name) or []
        offset = int(value_index)
        if offset < len(indexes) and indexes[offset] is not None:
            out[position] = indexes[offset]  # type: ignore[assignment]
    return out


def _extract_rich_value(
    zf: zipfile.ZipFile, names: set[str], cells: list[_Cell], media: _MediaReader
) -> list[EmbeddedImage]:
    """形态三：Microsoft 365 的「置于单元格内」图片（richValue）。

    单元格本身只有个 ``vm="3"``，值是 ``#VALUE!``；图在 xl/richData 下面。
    2023 年之后的 Excel 默认插入方式就是这个，用户从手机/网页版贴图基本都走这条路。
    """
    parts = _rich_value_parts(zf, names)
    if not parts:
        return []
    vm_map = _value_metadata_map(zf, names)
    out: list[EmbeddedImage] = []
    for cell in cells:
        if not cell.vm or not cell.vm.strip().isdigit():
            continue
        vm = int(cell.vm.strip())
        # metadata 缺失或没解出来时退回「vm - 1 就是富值下标」：绝大多数只放图片的
        # 表里两者本来就一致，能救一部分文件，也不会把图配错行（坐标来自单元格）。
        index = vm_map.get(vm, vm - 1)
        if not 0 <= index < len(parts):
            continue
        part = parts[index]
        if part is None:
            continue
        image = media.build(part, source="richvalue", row=cell.row, col=cell.col)
        if image is not None:
            out.append(image)
    return out


@dataclass
class ExtractResult:
    images: list[EmbeddedImage]
    warnings: list[str]


def extract_embedded_images(
    xlsx_bytes: bytes, *, sheet_index: int = 0, max_image_bytes: int = 20 * 1024 * 1024
) -> ExtractResult:
    """把工作簿第 ``sheet_index`` 张表上的图片全抠出来，按落点排好序。

    三种形态一起收：同一份表里混用（有人贴浮动图、有人用 WPS 嵌入）是常态。
    排序键是 (行, 列, 出现次序)，让「谁是主图」这件事在同一份文件上可复现。
    """
    warnings: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    except (zipfile.BadZipFile, OSError):
        # .xls（BIFF）和加密文件都会走到这，不是错误，只是没有可读的内嵌图。
        return ExtractResult(images=[], warnings=["文件不是 xlsx 包，跳过内嵌图片识别"])
    with zf:
        names = set(zf.namelist())
        sheet = _sheet_part(zf, names, sheet_index)
        if sheet is None:
            return ExtractResult(images=[], warnings=["未找到工作表内容，跳过内嵌图片识别"])
        try:
            sheet_root = ET.fromstring(zf.read(sheet))
        except (KeyError, ET.ParseError):
            return ExtractResult(images=[], warnings=["工作表 XML 解析失败，跳过内嵌图片识别"])
        media = _MediaReader(zf, names, max_image_bytes)
        cells = _scan_cells(sheet_root, _shared_strings(zf, names))
        images = _extract_anchored(zf, names, sheet, sheet_root, media)
        images += _extract_dispimg(zf, names, cells, media)
        images += _extract_rich_value(zf, names, cells, media)
        if media.oversized:
            warnings.append(
                f"{len(media.oversized)} 张内嵌图片超过单张体积上限已跳过："
                + "、".join(sorted(set(media.oversized))[:5])
            )
        if media.unknown_format:
            warnings.append(
                f"{len(media.unknown_format)} 个内嵌对象不是可识别的图片格式已跳过："
                + "、".join(sorted(set(media.unknown_format))[:5])
            )
    images.sort(key=lambda item: (item.row or 0, item.col or 0, item.order))
    return ExtractResult(images=images, warnings=warnings)
