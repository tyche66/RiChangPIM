"""xlsx 内嵌图片提取的单元用例（app/services/excel_images.py）。

这里的夹具全是手搓的 OOXML 包，不用 openpyxl 生成 —— 两个原因：

1. openpyxl 写图片同样要 Pillow，而宿主 python 3.14 上没有它（requirements.txt
   里 Pillow 带 ``; python_version < '3.13'``），用它造夹具会让整组用例在开发机上
   直接跳过，等于没测。
2. 更重要的是 openpyxl 只会生成「标准浮动图」这一种形态。WPS 的 DISPIMG 和
   Microsoft 365 的「置于单元格内」根本造不出来，而这两种恰恰是真实供应商报价表里
   最常见的 —— 用生成器造夹具，等于永远测不到我们真正要支持的那两条链路。

夹具刻意只放必要部件（不写 styles/sharedStrings 等），顺便钉住一件事：解析器不能
依赖那些可选部件存在。
"""

import io
import zipfile

from app.services.excel_images import (
    EmbeddedImage,
    column_to_index,
    extract_embedded_images,
    parse_cell_ref,
    sniff_image,
)

NS_DECL = (
    'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)
DRAW_DECL = (
    'xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)
REL_DECL = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
REL_BASE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-payload"
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-payload"
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"fake-webp-payload"


def _rels(*entries: tuple[str, str, str]) -> str:
    body = "".join(
        f'<Relationship Id="{rid}" Type="{REL_BASE}/{kind}" Target="{target}"/>'
        for rid, kind, target in entries
    )
    return f"<Relationships {REL_DECL}>{body}</Relationships>"


def _workbook(sheet_files: tuple[str, ...] = ("sheet1.xml",)) -> dict[str, str]:
    sheets = "".join(
        f'<sheet name="Sheet{i + 1}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i in range(len(sheet_files))
    )
    return {
        "xl/workbook.xml": f"<workbook {NS_DECL}><sheets>{sheets}</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": _rels(
            *(
                (f"rId{i + 1}", "worksheet", f"worksheets/{name}")
                for i, name in enumerate(sheet_files)
            )
        ),
    }


def _sheet(cells: str = "", drawing: bool = False) -> str:
    tail = '<drawing r:id="rId1"/>' if drawing else ""
    return f"<worksheet {NS_DECL}><sheetData>{cells}</sheetData>{tail}</worksheet>"


def _build(parts: dict[str, str | bytes]) -> bytes:
    """打成 xlsx 包。[Content_Types].xml 给个最小可用的，解析器不该依赖它。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        zf.writestr(
            "_rels/.rels",
            _rels(("rId1", "officeDocument", "xl/workbook.xml")),
        )
        for name, payload in parts.items():
            zf.writestr(name, payload)
    return buffer.getvalue()


def _anchor(col: int, row: int, rid: str, *, descr: str = "", to: tuple[int, int] | None = None):
    """一个 twoCellAnchor。col/row 是 OOXML 的 0 起坐标（col=2,row=1 就是 C2）。"""
    end = to or (col + 1, row + 1)
    return (
        '<xdr:twoCellAnchor editAs="oneCell">'
        f"<xdr:from><xdr:col>{col}</xdr:col><xdr:colOff>0</xdr:colOff>"
        f"<xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
        f"<xdr:to><xdr:col>{end[0]}</xdr:col><xdr:colOff>0</xdr:colOff>"
        f"<xdr:row>{end[1]}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>"
        "<xdr:pic><xdr:nvPicPr>"
        f'<xdr:cNvPr id="1" name="图片 1" descr="{descr}"/><xdr:cNvPicPr/>'
        "</xdr:nvPicPr>"
        f'<xdr:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch>'
        "</xdr:blipFill><xdr:spPr/></xdr:pic>"
        "<xdr:clientData/></xdr:twoCellAnchor>"
    )


def anchored_workbook(anchors: str, media: dict[str, bytes], rels: tuple) -> bytes:
    return _build(
        {
            **_workbook(),
            "xl/worksheets/sheet1.xml": _sheet(drawing=True),
            "xl/worksheets/_rels/sheet1.xml.rels": _rels(
                ("rId1", "drawing", "../drawings/drawing1.xml")
            ),
            "xl/drawings/drawing1.xml": f"<xdr:wsDr {DRAW_DECL}>{anchors}</xdr:wsDr>",
            "xl/drawings/_rels/drawing1.xml.rels": _rels(*rels),
            **media,
        }
    )


def test_anchored_image_lands_on_the_cell_its_anchor_points_at():
    """形态一（标准浮动图）：OOXML 的 0 起 col=2/row=1 要变成 1 起的 C2。

    行列口径搞错一格，图就会挂到相邻产品身上 —— 批量导入里这是最难被发现、
    后果最脏的一类错，所以坐标换算单独钉住。
    """
    payload = anchored_workbook(
        _anchor(2, 1, "rId1", descr="主图"),
        {"xl/media/image1.png": PNG},
        (("rId1", "image", "../media/image1.png"),),
    )

    result = extract_embedded_images(payload)

    assert result.warnings == []
    assert len(result.images) == 1
    image = result.images[0]
    assert (image.row, image.col) == (2, 3)
    assert (image.row_end, image.col_end) == (3, 4)
    assert image.source == "anchor"
    assert image.data == PNG
    assert (image.ext, image.content_type) == ("png", "image/png")
    assert image.name == "主图"


def _cell_images(entries: tuple[tuple[str, str], ...]) -> str:
    body = "".join(
        "<etc:cellImage><xdr:pic><xdr:nvPicPr>"
        f'<xdr:cNvPr id="1" name="{image_id}"/><xdr:cNvPicPr/></xdr:nvPicPr>'
        f'<xdr:blipFill><a:blip r:embed="{rid}"/></xdr:blipFill>'
        "<xdr:spPr/></xdr:pic></etc:cellImage>"
        for image_id, rid in entries
    )
    return (
        '<etc:cellImages xmlns:etc="http://www.wps.cn/officeDocument/2017/etCustomData" '
        f"{DRAW_DECL}>{body}</etc:cellImages>"
    )


def test_wps_dispimg_images_are_found_and_land_on_the_formula_cell():
    """形态二（WPS 嵌入单元格图片）：openpyxl 在这种表上返回「零张图」。

    国内供应商的报价表大多是 WPS 存的：单元格里只有 ``_xlfn.DISPIMG("ID_x",1)``，
    图片实体在 xl/cellimages.xml。顺带钉住 rels 的相对路径解析 ——
    ``xl/_rels/cellimages.xml.rels`` 里的 Target 是相对 ``xl/`` 的（``media/x.png``），
    而 drawings 那边是 ``../media/x.png``，两套基准都得对。
    """
    payload = _build(
        {
            **_workbook(),
            "xl/worksheets/sheet1.xml": _sheet(
                '<row r="2">'
                '<c r="C2" t="str"><f>_xlfn.DISPIMG("ID_1A2B3C4D5E6F7A8B",1)</f>'
                "<v>#VALUE!</v></c>"
                '<c r="D2" t="str"><f>_xlfn.DISPIMG("ID_99887766554433ZZ",1)</f></c>'
                "</row>"
                '<row r="3"><c r="C3" t="str">'
                '<f>=_xlfn.DISPIMG("ID_1A2B3C4D5E6F7A8B",1)</f></c></row>'
            ),
            "xl/cellimages.xml": _cell_images(
                (("ID_1A2B3C4D5E6F7A8B", "rId1"), ("ID_99887766554433ZZ", "rId2"))
            ),
            "xl/_rels/cellimages.xml.rels": _rels(
                ("rId1", "image", "media/image1.png"),
                ("rId2", "image", "media/image2.jpeg"),
            ),
            "xl/media/image1.png": PNG,
            "xl/media/image2.jpeg": JPEG,
        }
    )

    result = extract_embedded_images(payload)

    assert [(i.row, i.col, i.data) for i in result.images] == [
        (2, 3, PNG),
        (2, 4, JPEG),
        (3, 3, PNG),
    ]
    assert {i.source for i in result.images} == {"dispimg"}
    # 同一张图被两个单元格引用：两条记录、各自的坐标，字节只解压一次（同一对象）。
    assert result.images[0].data is result.images[2].data
    assert result.images[0].name == "ID_1A2B3C4D5E6F7A8B"


def _rich_data(count: int, *, structure_slot: int = 0) -> dict[str, str]:
    """M365「置于单元格内」那条链路的四个部件。

    ``structure_slot`` 用来把图片下标挪到 rv 的第二个 <v> 上，验证解析器是按
    ``_rvRel:LocalImageIdentifier`` 这个 key 找槽位，而不是傻取第一个 <v>。
    """
    keys = ['<k n="CalcOrigin" t="i"/>'] * structure_slot
    keys.insert(structure_slot, '<k n="_rvRel:LocalImageIdentifier" t="i"/>')
    values = "".join(
        '<rv s="0">'
        + "".join(f"<v>{index if slot == structure_slot else 1}</v>" for slot in range(len(keys)))
        + "</rv>"
        for index in range(count)
    )
    return {
        "xl/richData/rdrichvaluestructure.xml": (
            '<rvStructures xmlns="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata"'
            f' count="1"><s t="_localImage">{"".join(keys)}</s></rvStructures>'
        ),
        "xl/richData/rdrichvalue.xml": (
            '<rvData xmlns="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata"'
            f' count="{count}">{values}</rvData>'
        ),
        "xl/richData/richValueRel.xml": (
            '<richValueRels xmlns="http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + "".join(f'<rel r:id="rId{i + 1}"/>' for i in range(count))
            + "</richValueRels>"
        ),
        "xl/richData/_rels/richValueRel.xml.rels": _rels(
            *((f"rId{i + 1}", "image", f"../media/rich{i + 1}.png") for i in range(count))
        ),
    }


def _metadata(count: int) -> str:
    """metadataTypes 里刻意把 XLRICHVALUE 放第二个：``rc@t`` 是 1 起下标，
    按名字找而不是假定它排第一，是这段解析唯一容易写错的地方。"""
    future = "".join(
        '<bk><extLst><ext uri="{3e2802c4-a4d2-4d8b-9148-e3be6c30e623}">'
        f'<xlrd:rvb i="{i}"/></ext></extLst></bk>'
        for i in range(count)
    )
    value = "".join(f'<bk><rc t="2" v="{i}"/></bk>' for i in range(count))
    return (
        f"<metadata {NS_DECL} "
        'xmlns:xlrd="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata">'
        '<metadataTypes count="2"><metadataType name="XLDAPR"/>'
        '<metadataType name="XLRICHVALUE"/></metadataTypes>'
        f'<futureMetadata name="XLRICHVALUE" count="{count}">{future}</futureMetadata>'
        f'<valueMetadata count="{count}">{value}</valueMetadata>'
        "</metadata>"
    )


def test_m365_place_in_cell_images_are_found_via_rich_value_chain():
    """形态三（Microsoft 365「置于单元格内」）：单元格里只有个 ``vm`` 属性。

    2023 年以后的 Excel 默认就用这种方式插图，从手机端/网页端贴图更是只有这条路。
    链路长且每一跳都能踩坑：vm → metadata.xml → futureMetadata → rdrichvalue →
    结构表指定的槽位 → richValueRel → media。
    """
    payload = _build(
        {
            **_workbook(),
            "xl/worksheets/sheet1.xml": _sheet(
                '<row r="2"><c r="C2" t="e" vm="1"><v>#VALUE!</v></c>'
                '<c r="E2" t="e" vm="2"><v>#VALUE!</v></c></row>'
            ),
            "xl/metadata.xml": _metadata(2),
            **_rich_data(2, structure_slot=1),
            "xl/media/rich1.png": PNG,
            "xl/media/rich2.png": WEBP,
        }
    )

    result = extract_embedded_images(payload)

    assert [(i.row, i.col, i.source) for i in result.images] == [
        (2, 3, "richvalue"),
        (2, 5, "richvalue"),
    ]
    assert result.images[0].data == PNG
    assert (result.images[1].ext, result.images[1].content_type) == ("webp", "image/webp")


def test_rich_value_falls_back_when_metadata_part_is_missing():
    """metadata.xml 缺失/解不开时退回「vm-1 就是富值下标」。

    只放图片的表里两者本来一致，救得回一部分文件；坐标来自单元格本身，所以退化
    路径也不会把图配错行 —— 宁可少一层校验，也不要整列图片凭空消失。
    """
    payload = _build(
        {
            **_workbook(),
            "xl/worksheets/sheet1.xml": _sheet('<row r="5"><c r="B5" t="e" vm="1"/></row>'),
            **_rich_data(1),
            "xl/media/rich1.png": PNG,
        }
    )

    result = extract_embedded_images(payload)

    assert [(i.row, i.col) for i in result.images] == [(5, 2)]


def test_mixed_formats_are_merged_and_sorted_by_cell_then_order():
    """一份表里三种形态混着用是常态（多人接手同一个报价表）。

    排序键是 (行, 列, 出现次序)：主图选谁必须在同一份文件上可复现，否则同一次
    重导会换封面。
    """
    payload = _build(
        {
            **_workbook(),
            "xl/worksheets/sheet1.xml": (
                f"<worksheet {NS_DECL}><sheetData>"
                '<row r="2"><c r="D2" t="str"><f>_xlfn.DISPIMG("ID_AAAABBBBCCCCDDDD",1)</f></c>'
                '<c r="E2" t="e" vm="1"/></row>'
                '</sheetData><drawing r:id="rId1"/></worksheet>'
            ),
            "xl/worksheets/_rels/sheet1.xml.rels": _rels(
                ("rId1", "drawing", "../drawings/drawing1.xml")
            ),
            "xl/drawings/drawing1.xml": (
                f"<xdr:wsDr {DRAW_DECL}>"
                + _anchor(2, 1, "rId1")
                + _anchor(2, 1, "rId2")
                + "</xdr:wsDr>"
            ),
            "xl/drawings/_rels/drawing1.xml.rels": _rels(
                ("rId1", "image", "../media/image1.png"),
                ("rId2", "image", "../media/image2.jpeg"),
            ),
            "xl/cellimages.xml": _cell_images((("ID_AAAABBBBCCCCDDDD", "rId1"),)),
            "xl/_rels/cellimages.xml.rels": _rels(("rId1", "image", "media/wps.png")),
            "xl/metadata.xml": _metadata(1),
            **_rich_data(1),
            "xl/media/image1.png": PNG,
            "xl/media/image2.jpeg": JPEG,
            "xl/media/wps.png": b"\x89PNG\r\n\x1a\n" + b"wps-payload-xx",
            "xl/media/rich1.png": WEBP,
        }
    )

    result = extract_embedded_images(payload)

    assert [(i.row, i.col, i.source, i.order) for i in result.images] == [
        (2, 3, "anchor", 1),
        (2, 3, "anchor", 2),
        (2, 4, "dispimg", 3),
        (2, 5, "richvalue", 4),
    ]


def test_first_sheet_follows_workbook_declaration_order_not_zip_filenames():
    """取第一张表要按 workbook.xml 的声明顺序，不能按 sheet1/sheet2 的文件名。

    另存过几轮的表里 sheet3.xml 排在声明首位是常事，而 pandas 的 ``sheet_name=0``
    取的正是声明顺序 —— 两边口径不一致，图会挂到另一张表的行号上。
    """
    payload = _build(
        {
            "xl/workbook.xml": (
                f"<workbook {NS_DECL}><sheets>"
                '<sheet name="报价表" sheetId="3" r:id="rId1"/>'
                '<sheet name="说明" sheetId="1" r:id="rId2"/>'
                "</sheets></workbook>"
            ),
            "xl/_rels/workbook.xml.rels": _rels(
                ("rId1", "worksheet", "worksheets/sheet3.xml"),
                ("rId2", "worksheet", "worksheets/sheet1.xml"),
            ),
            "xl/worksheets/sheet3.xml": _sheet(
                '<row r="9"><c r="A9" t="str">'
                '<f>_xlfn.DISPIMG("ID_REALSHEETIMAGE1",1)</f></c></row>'
            ),
            "xl/worksheets/sheet1.xml": _sheet(
                '<row r="2"><c r="A2" t="str"><f>_xlfn.DISPIMG("ID_WRONGSHEETIMG1",1)</f></c></row>'
            ),
            "xl/cellimages.xml": _cell_images(
                (("ID_REALSHEETIMAGE1", "rId1"), ("ID_WRONGSHEETIMG1", "rId2"))
            ),
            "xl/_rels/cellimages.xml.rels": _rels(
                ("rId1", "image", "media/a.png"),
                ("rId2", "image", "media/b.png"),
            ),
            "xl/media/a.png": PNG,
            "xl/media/b.png": JPEG,
        }
    )

    result = extract_embedded_images(payload)

    assert [(i.row, i.data) for i in result.images] == [(9, PNG)]


def test_oversized_and_unrecognisable_media_are_skipped_with_a_warning():
    """超限/不是图片的对象要跳过并说清楚，不能静默丢也不能整单失败。

    Excel 里从 Word 粘过来的图常是 EMF/WMF，还有人把 xlsx 当网盘塞附件。这些
    进不了素材库（只收 jpg/png/webp），但不该让整份导入报错。
    """
    payload = anchored_workbook(
        _anchor(0, 1, "rId1") + _anchor(1, 1, "rId2") + _anchor(2, 1, "rId3"),
        {
            "xl/media/image1.png": PNG * 200,
            "xl/media/oleObject1.bin": b"\x00\x01\x02\x03not-an-image-at-all",
            "xl/media/image3.jpeg": JPEG,
        },
        (
            ("rId1", "image", "../media/image1.png"),
            ("rId2", "image", "../media/oleObject1.bin"),
            ("rId3", "image", "../media/image3.jpeg"),
        ),
    )

    result = extract_embedded_images(payload, max_image_bytes=64)

    assert [(i.col, i.data) for i in result.images] == [(3, JPEG)]
    assert any("超过单张体积上限" in w and "image1.png" in w for w in result.warnings)
    assert any("不是可识别的图片格式" in w and "oleObject1.bin" in w for w in result.warnings)


def test_non_xlsx_payload_reports_a_warning_instead_of_raising():
    """.xls（BIFF）和加密文件不是 zip 包。这里只能拿不到内嵌图，不该抛异常 ——
    上传 .xls 的用户还是应该能把文字列导进去。"""
    result = extract_embedded_images(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1old-biff-file")

    assert result.images == []
    assert result.warnings == ["文件不是 xlsx 包，跳过内嵌图片识别"]


def test_workbook_without_any_image_part_is_not_an_error():
    payload = _build({**_workbook(), "xl/worksheets/sheet1.xml": _sheet()})

    result = extract_embedded_images(payload)

    assert result.images == []
    assert result.warnings == []


def test_cell_reference_helpers():
    assert column_to_index("A") == 1
    assert column_to_index("Z") == 26
    assert column_to_index("AA") == 27
    assert column_to_index("AMJ") == 1024
    assert parse_cell_ref("C7") == (7, 3)
    assert parse_cell_ref("aa10") == (10, 27)
    assert parse_cell_ref("$C$7") is None
    assert parse_cell_ref("") is None


def test_sniff_image_reads_magic_bytes_not_extensions():
    """媒体目录里的文件名是 Excel 自己造的，改过扩展名的 jpg 极常见。"""
    assert sniff_image(PNG) == ("png", "image/png")
    assert sniff_image(JPEG) == ("jpeg", "image/jpeg")
    assert sniff_image(WEBP) == ("webp", "image/webp")
    assert sniff_image(b"GIF89a" + b"x" * 20) == ("gif", "image/gif")
    assert sniff_image(b"RIFF" + b"\x00" * 4 + b"WAVEfmt ") is None
    assert sniff_image(b"too-short") is None


def test_embedded_image_is_hashable_so_callers_can_dedupe():
    """行→图片的归属计算里会把同一张图放进集合去重，dataclass 必须是 frozen。"""
    image = EmbeddedImage(
        data=PNG, ext="png", content_type="image/png", source="anchor", order=1, row=2, col=3
    )
    assert len({image, image}) == 1
