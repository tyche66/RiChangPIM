"""批量导入图片链路的单元用例（app/services/product_import_media.py）。

四块：格式准入（make_blob）、上传包解析（load_bundle）、行→图片归属（MediaResolver）、
外链抓取与上传（guard_url / fetch_image_url / MediaUploader）。

归属那一块是重点：图挂到相邻产品身上是这条链路里最难被发现的错 —— 页面上每个产品
都有图，看着一切正常，只有逐个核对才会发现整列错了一格。所以每条归属规则（列→角色、
封面选谁、约定前缀、批内去重、上限截断）都单独钉一条。

夹具里的「图片」是魔术字节 + 几个填充字节：这一层只按魔数认格式、按 sha256 去重，
不解码像素，所以不需要真图，也就不牵连 Pillow（宿主 python 3.14 上没有它）。
"""

import hashlib
import io
import ipaddress
import zipfile

import httpx
import pandas as pd
import pytest

from app.services.excel_images import EmbeddedImage
from app.services.product_import import ProductRow, ProductSheet, SheetColumn, read_product_sheet
from app.services.product_import_media import (
    MAX_IMAGE_BYTES,
    ROLE_MAIN,
    ROLE_PRODUCT,
    ROLE_SCENE,
    BundleFile,
    ImportBundle,
    MediaError,
    MediaResolver,
    MediaUploader,
    _read_member,
    fetch_image_url,
    guard_url,
    load_bundle,
    make_blob,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"png-payload-1"
PNG2 = b"\x89PNG\r\n\x1a\n" + b"png-payload-2"
PNG3 = b"\x89PNG\r\n\x1a\n" + b"png-payload-3"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-payload-1"
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"webp-payload"
GIF = b"GIF89a" + b"x" * 20
WMF = b"\xd7\xcd\xc6\x9a" + b"wmf-payload"

HAS_PILLOW = True
try:  # pragma: no cover - 取决于宿主装没装 Pillow
    from PIL import Image  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    HAS_PILLOW = False


# --------------------------------------------------------------------------- 格式准入


def test_make_blob_reads_the_format_from_magic_bytes_not_the_extension():
    """改过后缀的 jpg 在供应商表里极常见。

    ``files.py`` 的下载端点是按 oss_key 的后缀回 Content-Type 的：认错格式，浏览器
    里就是一张裂图。
    """
    blob, reason = make_blob(JPEG, name="chair.png", source="zip")

    assert reason is None
    assert blob is not None
    assert (blob.ext, blob.content_type) == ("jpeg", "image/jpeg")
    assert (blob.source, blob.role, blob.size) == ("zip", ROLE_PRODUCT, len(JPEG))
    assert blob.sha256 == hashlib.sha256(JPEG).hexdigest()

    for payload, ext in ((PNG, "png"), (WEBP, "webp")):
        ok, _ = make_blob(payload, name="x", source="anchor")
        assert ok is not None and ok.ext == ext
        # 内嵌图片没有文件名，补后缀是为了让 oss_key 的后缀正确。
        assert ok.name == f"x.{ext}"


def test_unusable_bytes_come_back_with_a_reason_instead_of_an_exception():
    """一张图进不了库不该让整行、更不该让整份导入失败。"""
    assert make_blob(b"", name="empty.jpg", source="zip")[1] == "empty.jpg：内容是空的"

    _, oversized = make_blob(PNG, name="big.png", source="zip", max_bytes=4)
    assert oversized is not None and "超过单张体积上限" in oversized

    _, junk = make_blob(b"\x00\x01\x02not-an-image", name="a.pdf", source="zip")
    assert junk is not None and "不是可识别的图片格式" in junk

    # Word 里粘过来的图常是 wmf/emf：浏览器根本不显示，收进来只会变成裂图。
    _, vector = make_blob(WMF, name="paste.wmf", source="anchor")
    assert vector is not None and "不是支持的图片格式" in vector


def test_gif_needs_a_conversion_and_says_which_step_failed():
    """gif/bmp/tiff 素材库不收（files.py 的 _ALLOWED 只有 jpg/png/webp）。

    「没装 Pillow」和「转换失败」要分开说：前者是运维能解决的，后者是文件本身的问题，
    混成一句话会让人白装一遍依赖。这里的 GIF 夹具只有魔数、解不开，所以装了 Pillow
    的机器上走的是后一条。
    """
    blob, reason = make_blob(GIF, name="scene.gif", source="zip")

    assert blob is None
    assert reason is not None
    assert ("转成 png 时失败" if HAS_PILLOW else "没有安装 Pillow") in reason


@pytest.mark.skipif(not HAS_PILLOW, reason="需要 Pillow 才能真转格式")
def test_real_gif_is_converted_to_png_and_renamed():
    buffer = io.BytesIO()
    Image.new("P", (4, 4)).save(buffer, format="GIF")

    blob, reason = make_blob(buffer.getvalue(), name="scene.gif", source="zip")

    assert reason is None
    assert blob is not None
    assert (blob.ext, blob.content_type, blob.name) == ("png", "image/png", "scene.png")


# --------------------------------------------------------------------------- 上传包


def _xlsx(rows: list[list[object]]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, header=False, sheet_name="报价单")
    return buffer.getvalue()


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
    return buffer.getvalue()


def test_a_plain_workbook_or_a_non_zip_upload_passes_straight_through():
    """xlsx 本身就是 zip，所以不能只看「是不是 zip」——里面有 xl/workbook.xml 的
    就是表格本体。.xls / 加密文件不是 zip，原样透传给 read_product_sheet 去报错，
    那边的话术（「文件解析失败」）对用户更有用。"""
    book = _xlsx([["产品编号", "产品名称"], ["SUNON-001", "椅"]])

    plain = load_bundle(book)
    assert (plain.xlsx, plain.files, plain.warnings) == (book, {}, [])

    raw = load_bundle(b"\xd0\xcf\x11\xe0not-an-xlsx")
    assert raw.xlsx == b"\xd0\xcf\x11\xe0not-an-xlsx"


def test_zip_bundle_indexes_photos_by_basename_and_ignores_companion_files():
    """供应商发的是「一个表格 + 一个图片文件夹」，压缩包里带目录、带大小写差异是常态。

    macOS 打包出来的 ``__MACOSX/._x``、Excel 的锁文件 ``~$x.xlsx``、``.DS_Store``
    都不是图片；非图片扩展名（pdf/mp4）先按后缀筛掉，免得把整包读进内存。
    """
    payload = _zip(
        {
            "报价单.xlsx": _xlsx([["产品编号"], ["SUNON-001"]]),
            "图片/Chair-1.JPG": JPEG,
            "图片/chair-2.png": PNG,
            "__MACOSX/._Chair-1.JPG": b"junk",
            "~$报价单.xlsx": b"lock",
            ".DS_Store": b"junk",
            "说明.pdf": b"%PDF-1.7",
        }
    )

    bundle = load_bundle(payload)

    assert bundle.book_name == "报价单.xlsx"
    assert sorted(bundle.files) == ["chair-1.jpg", "chair-2.png"]
    assert bundle.warnings == []
    assert bundle.find("图片/chair-1.jpg") is not None
    # 用户在格里常只写「chair-1」，或者写 .jpeg 而包里是 .jpg —— 去扩展名再试一次。
    assert bundle.find("Chair-1") is not None
    assert bundle.find("chair-1.jpeg") is not None
    assert bundle.find("chair-9.jpg") is None
    assert bundle.find("") is None


def test_zip_without_a_workbook_fails_and_extra_workbooks_only_warn():
    with pytest.raises(MediaError, match="没有找到表格文件"):
        load_bundle(_zip({"chair-1.jpg": JPEG}))

    two = load_bundle(
        _zip(
            {
                "a报价单.xlsx": _xlsx([["产品编号"], ["A"]]),
                "b报价单.xlsx": _xlsx([["产品编号"], ["B"]]),
                "chair-1.jpg": JPEG,
            }
        )
    )

    assert two.book_name == "a报价单.xlsx"
    assert any("只导入了 a报价单.xlsx" in w for w in two.warnings)


def test_zip_members_are_checked_against_the_size_budget_before_being_read():
    """解压炸弹只要读了就晚了，所以先看 zip 头里的 file_size 再决定要不要读。"""
    book = _xlsx([["产品编号"], ["A"]])
    payload = _zip({"book.xlsx": book, "a.jpg": JPEG, "b.png": PNG * 40, "c.png": PNG2})

    limited = load_bundle(payload, max_image_bytes=64)
    assert sorted(limited.files) == ["a.jpg", "c.png"]
    assert any("超过单张体积上限" in w and "b.png" in w for w in limited.warnings)

    budget = load_bundle(payload, max_total_bytes=len(JPEG))
    assert sorted(budget.files) == ["a.jpg"]
    assert any("图片总量超过" in w for w in budget.warnings)


def test_duplicate_basenames_in_a_zip_keep_the_first_and_say_so():
    """两个目录里各有一张 chair-1.jpg：按 basename 索引就只能留一张，
    但必须说出来 —— 否则用户看到的是「图不对」而不知道为什么。"""
    bundle = load_bundle(
        _zip(
            {
                "book.xlsx": _xlsx([["产品编号"], ["A"]]),
                "a/chair-1.jpg": JPEG,
                "b/chair-1.jpg": PNG,
            }
        )
    )

    assert bundle.files["chair-1.jpg"].data == JPEG
    assert any("多个「chair-1.jpg」" in w for w in bundle.warnings)


def test_prefix_matching_stops_at_a_separator_so_neighbour_skus_stay_apart():
    """``SUNON-001`` 不能把 ``SUNON-0012.jpg``（另一个产品）吃进来。

    只挡 ASCII 字母数字，是为了让 ``SUNON-001场景.jpg`` 这种中文后缀还能归上 ——
    用中文给图片起名的表比想象中多。
    """
    bundle = ImportBundle(
        xlsx=b"",
        files={
            name: BundleFile(name=name, data=PNG)
            for name in ("sunon-001.jpg", "sunon-001_2.jpg", "sunon-001场景.jpg", "sunon-0012.jpg")
        },
    )

    assert [f.name for f in bundle.match_prefix("SUNON-001")] == [
        "sunon-001.jpg",
        "sunon-001_2.jpg",
        "sunon-001场景.jpg",
    ]
    assert bundle.match_prefix("") == []


# --------------------------------------------------------------------------- 归属


def _sheet(columns: dict[int, str], rows: dict[int, dict[str, str]] | None = None) -> ProductSheet:
    """按 {excel_col: key} 造一张只有图片列的表。

    直接构造 ProductSheet 而不是走 xlsx：归属规则要按列号逐格钉，用真表格造反而
    会让「第几列」被 pandas 的读入行为绕一层。真表格的路径由本文件最后一条
    端到端用例覆盖。
    """
    return ProductSheet(
        header_row=1,
        columns=[
            SheetColumn(key=key, header=key, position=col - 1, excel_col=col)
            for col, key in sorted(columns.items())
        ],
        rows=[ProductRow(excel_row=row, values=values) for row, values in (rows or {}).items()],
    )


def _embedded(row: int, col: int, data: bytes, *, order: int = 1, span: int = 1) -> EmbeddedImage:
    return EmbeddedImage(
        data=data,
        ext="png",
        content_type="image/png",
        source="anchor",
        order=order,
        row=row,
        col=col,
        row_end=row + 1,
        col_end=col + span,
    )


def test_embedded_images_take_the_role_of_the_column_they_sit_in():
    """形态一/二/三解出来的图只有 (行, 列)，角色全靠落点判断。

    主图列 → 封面，产品图列 → 产品图，场景图列 → 场景图。列错一格，封面就会变成
    一张场景效果图。
    """
    sheet = _sheet({3: "main_image", 4: "images", 5: "images", 6: "scene_images"}, {7: {}})
    resolver = MediaResolver(
        sheet,
        embedded=[
            _embedded(7, 4, PNG2, order=1),
            _embedded(7, 3, PNG, order=2),
            _embedded(7, 6, PNG3, order=3),
            _embedded(7, 5, JPEG, order=4),
        ],
    )

    media = resolver.resolve(sheet.rows[0], product_no="SUNON-001")

    assert media.cover is not None
    assert (media.cover.data, media.cover.role) == (PNG, ROLE_MAIN)
    # 产品图按列从左到右：封面之外还剩 4 列、5 列那两张。
    assert [b.data for b in media.images] == [PNG2, JPEG]
    assert [b.data for b in media.scenes] == [PNG3]
    assert all(b.role == ROLE_PRODUCT for b in media.images)
    assert media.scenes[0].role == ROLE_SCENE
    assert media.count == 4
    assert media.sources == {"anchor"}
    assert media.warnings == []
    # 内嵌图没有文件名，用编号 + 次序补一个，素材库里才认得出是谁的图。
    assert media.cover.name == "SUNON-001-2.png"


def test_a_floating_image_spanning_columns_lands_on_the_image_column_it_covers():
    """浮动图片常被画得比单元格大，左上角落在名称列、右边压到图片列上。

    只看左上角就会把它判成「不在任何图片列里」；按 from→to 的跨度找，才符合用户
    肉眼看到的那一格。
    """
    sheet = _sheet({4: "scene_images"}, {9: {}})
    resolver = MediaResolver(sheet, embedded=[_embedded(9, 2, PNG, span=4)])

    media = resolver.resolve(sheet.rows[0])

    assert (media.cover, [b.data for b in media.scenes]) == (None, [PNG])


def test_sheets_without_image_columns_treat_every_row_image_as_a_product_photo():
    """很多供应商表的图片列压根没有表头文字，图就那么压在行上。

    这时候整行的图都当产品图、第一张作封面 —— 总比「一张图都没导进来」好。
    """
    sheet = _sheet({}, {5: {}})
    resolver = MediaResolver(sheet, embedded=[_embedded(5, 9, PNG, order=1), _embedded(5, 2, JPEG)])

    media = resolver.resolve(sheet.rows[0])

    assert media.cover is not None and media.cover.data == PNG
    assert [b.data for b in media.images] == [JPEG]


def test_images_outside_the_data_rows_are_reported_once_per_row():
    """图被拖到标题行/空行上是常见手滑。静默丢掉的话，用户只会觉得「导入丢图」。"""
    sheet = _sheet({3: "images"}, {7: {}})

    resolver = MediaResolver(
        sheet,
        embedded=[_embedded(1, 3, PNG), _embedded(1, 3, JPEG, order=2), _embedded(7, 3, PNG3)],
    )

    assert resolver.warnings == ["第 1 行不是数据行，上面的 2 张图片没有导入"]
    media = resolver.resolve(sheet.rows[0])
    assert media.count == 1


def test_filenames_written_in_cells_are_looked_up_in_the_zip():
    sheet = _sheet(
        {3: "main_image", 4: "images", 5: "scene_images"},
        {
            4: {
                "main_image": "cover.JPG",
                "images": "chair-1.png,missing.png",
                "scene_images": "室内",
            }
        },
    )
    bundle = load_bundle(
        _zip(
            {
                "book.xlsx": _xlsx([["产品编号"], ["A"]]),
                "图片/cover.jpg": JPEG,
                "chair-1.png": PNG,
                "室内.png": PNG2,
            }
        )
    )

    media = MediaResolver(sheet, bundle=bundle).resolve(sheet.rows[0], product_no="A")

    assert media.cover is not None and media.cover.data == JPEG
    assert [b.data for b in media.images] == [PNG]
    assert [b.data for b in media.scenes] == [PNG2]
    assert media.sources == {"zip"}
    # 找不到的图只留一条提示，这一行的其它图照样入库。
    assert media.warnings == ["第 4 行的图片「missing.png」在压缩包里没有找到"]


def test_naming_a_file_without_uploading_a_bundle_explains_itself():
    sheet = _sheet({3: "images"}, {4: {"images": "chair-1.jpg"}})

    media = MediaResolver(sheet).resolve(sheet.rows[0])

    assert media.count == 0
    assert media.warnings == ["第 4 行填了图片名「chair-1.jpg」，但上传的文件里没有图片"]


def test_prefix_convention_only_applies_to_rows_that_named_nothing():
    """「文件名以产品编号开头」是给「懒得填文件名」的行用的。

    已经写了名字的行不能再被塞进一堆同前缀的图（用户明确选过了）；被别的行显式引用
    过的文件也不能再按前缀归给这一行，否则同一张图会挂到两个产品上。
    """
    sheet = _sheet(
        {3: "images"},
        {4: {"images": "SUNON-003-1.png"}, 5: {}, 6: {}},
    )
    bundle = load_bundle(
        _zip(
            {
                "book.xlsx": _xlsx([["产品编号"], ["A"]]),
                "SUNON-003-1.png": PNG,
                "SUNON-002.jpg": JPEG,
                "SUNON-002_2.jpg": PNG2,
                "SUNON-002场景图.png": PNG3,
                "SUNON-0021.jpg": WEBP,
            }
        )
    )
    resolver = MediaResolver(sheet, bundle=bundle)

    # 第 4 行明确写了一个「按前缀本该属于 SUNON-003」的文件名：以它写的为准。
    named = resolver.resolve(sheet.rows[0], product_no="SUNON-001")
    assert [b.data for b in named.blobs] == [PNG]
    assert named.sources == {"zip"}

    convention = resolver.resolve(sheet.rows[1], product_no="SUNON-002")
    assert convention.cover is not None and convention.cover.data == JPEG
    assert [b.data for b in convention.images] == [PNG2]
    # 名字里带「场景」的走场景图；SUNON-0021 是另一个编号，不能被吃进来。
    assert [b.data for b in convention.scenes] == [PNG3]
    assert convention.sources == {"convention"}

    # SUNON-003-1.png 已经被第 4 行显式引用，不能再按前缀归给 SUNON-003 ——
    # 否则同一张图会同时挂到两个产品上。
    other = resolver.resolve(sheet.rows[2], product_no="SUNON-003")
    assert other.count == 0


def test_the_same_photo_referenced_twice_in_a_row_is_kept_once():
    """一张「品牌形象图」在同一行被写两遍很常见（复制粘贴出来的表）。

    按 sha256 去重：产品图列表里不该出现两张一模一样的图。
    """
    sheet = _sheet({3: "images"}, {4: {"images": "a.png,图片/a.png,b.png"}})
    bundle = load_bundle(
        _zip({"book.xlsx": _xlsx([["产品编号"], ["A"]]), "a.png": PNG, "b.png": PNG})
    )

    media = MediaResolver(sheet, bundle=bundle).resolve(sheet.rows[0])

    assert media.count == 1
    assert media.cover is not None and media.cover.data == PNG


def test_extra_main_column_images_become_product_photos_with_a_note():
    sheet = _sheet({3: "main_image"}, {4: {}})
    resolver = MediaResolver(sheet, embedded=[_embedded(4, 3, PNG), _embedded(4, 3, JPEG, order=2)])

    media = resolver.resolve(sheet.rows[0])

    assert media.cover is not None and media.cover.data == PNG
    assert [(b.data, b.role) for b in media.images] == [(JPEG, ROLE_PRODUCT)]
    assert any("主图列有多张图" in w for w in media.warnings)


def test_row_image_caps_truncate_and_say_how_many_were_dropped():
    """「文件名以编号开头就归给这行」很容易撞上一个装了几百张图的压缩包。

    一行挂 200 张图对谁都没好处，截断并说清楚。
    """
    sheet = _sheet({3: "images", 4: "scene_images"}, {4: {}})
    resolver = MediaResolver(
        sheet,
        embedded=[
            _embedded(4, 3, PNG, order=1),
            _embedded(4, 3, PNG2, order=2),
            _embedded(4, 3, PNG3, order=3),
            _embedded(4, 4, JPEG, order=4),
            _embedded(4, 4, WEBP, order=5),
        ],
        max_images=2,
        max_scenes=1,
    )

    media = resolver.resolve(sheet.rows[0])

    assert media.cover is not None and media.cover.data == PNG
    assert [b.data for b in media.images] == [PNG2]
    assert [b.data for b in media.scenes] == [JPEG]
    assert any("3 张产品图，只导入前 2 张" in w for w in media.warnings)
    assert any("2 张场景图，只导入前 1 张" in w for w in media.warnings)


def test_url_cells_need_the_fetcher_to_be_enabled_and_never_fail_the_row():
    """外链抓取默认关闭（PRODUCT_IMPORT_ALLOW_URL_FETCH）：服务端替用户 GET 任意
    地址就是 SSRF。关着的时候要说清楚为什么没导，而不是假装没看见那一格。"""
    sheet = _sheet({3: "images"}, {4: {"images": "https://cdn.example.com/a.png"}})

    off = MediaResolver(sheet).resolve(sheet.rows[0])
    assert off.count == 0
    assert any("外链抓取没有开启" in w for w in off.warnings)

    def broken(url: str) -> tuple[bytes, str]:
        raise MediaError(f"{url}：HTTP 404")

    failed = MediaResolver(sheet, url_fetcher=broken).resolve(sheet.rows[0])
    assert failed.count == 0
    assert failed.warnings == ["第 4 行：https://cdn.example.com/a.png：HTTP 404"]

    ok = MediaResolver(sheet, url_fetcher=lambda url: (PNG, "a.png")).resolve(sheet.rows[0])
    assert ok.cover is not None and (ok.cover.data, ok.cover.source) == (PNG, "url")


# --------------------------------------------------------------------------- 外链


def _resolve_to(address: str):
    """假 DNS：域名一律解析到给定地址，IP 字面量原样返回。

    后者是关键 —— 真的 ``getaddrinfo("169.254.169.254", …)`` 返回的就是它自己。
    要是连 IP 字面量都替换成公网地址，重定向那条用例就会假绿。
    """

    def resolve(host: str, port: int) -> list[str]:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return [address]
        return [host]

    return resolve


def test_guard_url_rejects_internal_targets_and_non_http_schemes():
    """169.254.169.254 是云上的元数据服务，能拿到实例凭证；10.x/127.0.0.1 是内网。

    ``::ffff:127.0.0.1`` 单独钉一条：IPv6 映射地址的 ``is_loopback`` 是 False，
    不摊平就等于给回环开了个后门。
    """
    assert guard_url("https://cdn.example.com/a.png", resolve=_resolve_to("93.184.216.34")) is None

    for address in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "::ffff:127.0.0.1"):
        reason = guard_url("http://target/a.png", resolve=_resolve_to(address))
        assert reason is not None and "内网/保留地址" in reason, address

    assert "只支持 http/https" in (guard_url("ftp://example.com/a.png") or "")
    assert "只支持 http/https" in (guard_url("file:///etc/passwd") or "")
    assert "没有主机名" in (guard_url("http:///a.png") or "")

    def boom(host: str, port: int):
        raise OSError("no such host")

    assert "域名解析失败" in (guard_url("http://nope.invalid/a.png", resolve=boom) or "")
    assert "解析不到地址" in (guard_url("http://nope/a.png", resolve=lambda h, p: []) or "")


def test_fetch_image_url_revalidates_every_redirect_hop():
    """让 httpx 自动跟重定向的话，一个公网域名可以 302 到 169.254.169.254，
    前面的校验就全白做了 —— 所以重定向自己跟，每一跳重新过一遍 guard_url。"""
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        if request.url.host == "cdn.example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta"})
        return httpx.Response(200, content=PNG)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(MediaError, match="内网/保留地址"):
        fetch_image_url(
            "https://cdn.example.com/a.png", client=client, resolve=_resolve_to("93.184.216.34")
        )

    assert hops == ["https://cdn.example.com/a.png"]


def test_fetch_image_url_returns_bytes_and_a_name_and_stops_at_the_cap():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("big.png"):
            return httpx.Response(200, content=PNG * 100)
        return httpx.Response(200, content=PNG)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    public = _resolve_to("93.184.216.34")

    data, name = fetch_image_url(
        "https://cdn.example.com/photos/%E6%A4%85%E5%AD%90.png", client=client, resolve=public
    )

    assert (data, name) == (PNG, "椅子.png")

    # 只信 Content-Length 会被没有这个头、或者故意写小了的服务端绕过，所以边读边数。
    with pytest.raises(MediaError, match="超过上限"):
        fetch_image_url(
            "https://cdn.example.com/big.png", client=client, resolve=public, max_bytes=64
        )

    assert MAX_IMAGE_BYTES == 20 * 1024 * 1024


# --------------------------------------------------------------------------- 上传


class _FakeMinio:
    """够用的假 MinIO：只记下调用。真客户端是同步阻塞的，端点里要 to_thread 包。"""

    def __init__(self, *, exists: bool = False, fail: bool = False) -> None:
        self.exists = exists
        self.fail = fail
        self.made: list[str] = []
        self.objects: list[tuple[str, str, bytes, str]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return self.exists

    def make_bucket(self, bucket: str) -> None:
        self.made.append(bucket)
        self.exists = True

    def put_object(self, bucket, key, data, length, content_type):
        if self.fail:
            raise OSError("minio down")
        payload = data.read()
        assert len(payload) == length
        self.objects.append((bucket, key, payload, content_type))


def test_uploader_puts_each_distinct_image_once_and_reuses_the_key():
    """同一张场景图被三十行引用时只该上传一次、只建一条 Attachment ——
    product_scene_image 本来就是多对多，三十个产品共用它。"""
    client = _FakeMinio()
    uploader = MediaUploader(client, "pim")
    blob, _ = make_blob(JPEG, name="chair.jpg", source="zip")
    again, _ = make_blob(JPEG, name="别的名字.jpg", source="convention")
    other, _ = make_blob(PNG, name="scene.png", source="anchor")
    assert blob is not None and again is not None and other is not None

    first = uploader.upload(blob)
    second = uploader.upload(again)
    third = uploader.upload(other)

    assert first is second
    assert uploader.uploaded == 2
    assert len(client.objects) == 2
    assert client.made == ["pim"]
    # key 的格式跟 files.py 的上传接口一致：/files/{oss_key} 是按后缀回 Content-Type 的。
    assert first.oss_key.startswith("image/") and first.oss_key.endswith(".jpeg")
    assert len(first.oss_key) == len("image/") + 32 + len(".jpeg")
    assert first.file_url == f"/files/{first.oss_key}"
    assert (first.content_type, first.size, first.name) == ("image/jpeg", len(JPEG), "chair.jpg")
    assert uploader.get(blob.sha256) is first
    assert uploader.get("nope") is None
    assert third.oss_key.endswith(".png")


def test_uploader_skips_bucket_creation_when_it_already_exists_and_reports_failures():
    existing = _FakeMinio(exists=True)
    blob, _ = make_blob(PNG, name="a.png", source="zip")
    assert blob is not None
    MediaUploader(existing, "pim").upload(blob)
    assert existing.made == []

    with pytest.raises(MediaError, match="上传到对象存储失败"):
        MediaUploader(_FakeMinio(fail=True), "pim").upload(blob)


# --------------------------------------------------------------------------- 端到端


def test_a_real_zip_of_a_workbook_and_photos_resolves_row_by_row():
    """真表格 + 真压缩包走一遍：这是「供应商发来一个压缩包」的完整路径。

    表头在第 2 行、中间有空行 —— 行号口径错一格图就会挂到相邻产品身上，所以这里
    连着 read_product_sheet 一起验。
    """
    book = _xlsx(
        [
            ["某某家具 2026 年报价单", None, None, None],
            ["货号", "品名", "主图", "图片1"],
            ["SUNON-001", "人体工学椅", "cover.jpg", "chair-1.png"],
            [None, None, None, None],
            ["SUNON-002", "办公桌", None, None],
        ]
    )
    bundle = load_bundle(
        _zip(
            {
                "报价单.xlsx": book,
                "图片/cover.jpg": JPEG,
                "图片/chair-1.png": PNG,
                "图片/SUNON-002.png": PNG2,
                "图片/SUNON-002场景.png": PNG3,
            }
        )
    )

    sheet = read_product_sheet(bundle.xlsx)
    resolver = MediaResolver(sheet, bundle=bundle)
    first = resolver.resolve(sheet.rows[0], product_no="SUNON-001")
    second = resolver.resolve(sheet.rows[1], product_no="SUNON-002")

    assert [r.excel_row for r in sheet.rows] == [3, 5]
    assert first.cover is not None and first.cover.data == JPEG
    assert [b.data for b in first.images] == [PNG]
    assert first.warnings == []

    assert second.cover is not None and second.cover.data == PNG2
    assert [b.data for b in second.scenes] == [PNG3]
    assert second.sources == {"convention"}
    assert resolver.warnings == []


# --------------------------------------------------------------------------- 按需解压


def _lie_about_size(payload: bytes, member: str, claimed: int) -> bytes:
    """把中央目录里那个成员的「解压后大小」改小 —— 解压炸弹就是这么写头的。

    zipfile 会按这个数字截断输出，于是 CRC 对不上、``read()`` 抛 ``BadZipFile``：
    坏成员/撒谎的头在这一层表现成「这张图读不出来」，本文件用它来验「只废这一张」。
    """
    data = bytearray(payload)
    at = data.index(b"PK\x01\x02")
    while data[at : at + 4] == b"PK\x01\x02":
        name_len = int.from_bytes(data[at + 28 : at + 30], "little")
        extra_len = int.from_bytes(data[at + 30 : at + 32], "little")
        comment_len = int.from_bytes(data[at + 32 : at + 34], "little")
        if bytes(data[at + 46 : at + 46 + name_len]) == member.encode():
            data[at + 24 : at + 28] = claimed.to_bytes(4, "little")
            return bytes(data)
        at += 46 + name_len + extra_len + comment_len
    raise AssertionError(f"{member} 不在中央目录里")


def test_a_bundle_reads_one_member_at_a_time_and_close_releases_the_zip():
    """4242 张图、解压后 394MB 的包不能整包读进内存：成员是用到那一下才解的。

    所以 ``load_bundle`` 收的可以是上传的临时文件本身（Starlette 早就落盘了），
    整个导入期间压缩包保持打开，接口层用完调 ``close()``。
    """
    payload = _zip({"book.xlsx": _xlsx([["产品编号"], ["A"]]), "chair-1.jpg": JPEG})

    bundle = load_bundle(io.BytesIO(payload))

    assert bundle.zip_file is not None
    entry = bundle.files["chair-1.jpg"]
    # 索引阶段只记「在哪、多大」，字节还在包里。
    assert entry.size == len(JPEG)
    assert "jpeg-payload" not in repr(entry)
    assert entry.data == JPEG

    bundle.close()
    assert bundle.zip_file is None
    bundle.close()  # 幂等：接口层的 finally 可能在早退路径上已经关过一次


def test_reading_a_member_never_hands_back_more_than_the_caller_allowed():
    """体积筛查看的是压缩头，真读是另一个时刻、另一段代码 ——
    ``_read_member`` 自己也要守住上限，代价是多读一个字节。"""
    big = PNG * 40
    payload = _zip({"book.xlsx": _xlsx([["产品编号"], ["A"]]), "big.png": big})

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        assert _read_member(zf, "big.png", None) == big
        assert _read_member(zf, "big.png", len(big)) == big
        with pytest.raises(MediaError, match="解压后超过单张体积上限"):
            _read_member(zf, "big.png", 64)


def test_a_member_that_cannot_be_read_only_costs_that_one_photo():
    """解不动的那张图只该变成一条提示 —— 4000 行的导入不能被一张坏图带走。

    压缩头声称 10 字节、实际解出 800 多字节：体积筛查按头放它进来了，坏在真读那一刻。
    """
    book = _xlsx(
        [["产品编号", "产品名称", "主图", "图片1"], ["SUNON-001", "椅", "cover.jpg", "chair-1.png"]]
    )
    payload = _lie_about_size(
        _zip({"报价单.xlsx": book, "cover.jpg": JPEG, "chair-1.png": PNG * 40}),
        "chair-1.png",
        10,
    )
    bundle = load_bundle(payload, max_image_bytes=64)
    assert sorted(bundle.files) == ["chair-1.png", "cover.jpg"]

    sheet = read_product_sheet(bundle.xlsx)
    media = MediaResolver(sheet, bundle=bundle).resolve(sheet.rows[0], product_no="SUNON-001")

    assert media.cover is not None and media.cover.data == JPEG
    assert media.images == []
    assert any("chair-1.png" in w and "从压缩包里解出来失败" in w for w in media.warnings)
