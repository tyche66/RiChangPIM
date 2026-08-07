"""批量导入的图片链路：把图从上传包里找出来、认出角色、去重、传进 MinIO。

这一层刻意不 import 任何 ORM：``Attachment`` / ``ProductImage`` / ``SceneImage`` 的
写库动作留在接口层，本模块只输出「这一行该配哪几张图、字节在这里」。这样它才能进
``tests/unit``（那层的约定是不许牵连 ``app.core.database``），而图片归属恰恰是最需要
被钉住的部分 —— 行列口径错一格，图就挂到相邻产品身上，肉眼几乎发现不了。

用户能用的三种给图方式，按「用户少动手」排序：

1. **图直接在表里**（推荐）：WPS 的「嵌入单元格」、Excel 365 的「置于单元格内」、
   压在某一行上的浮动图片，都由 ``excel_images`` 解出来，再按落点的列归到主图/
   产品图/场景图。
2. **xlsx + 图片文件打成 zip**：格里写文件名（chair-1.jpg），或者干脆不写 ——
   文件名以产品编号开头的图会自动归到那一行。内嵌图会把 xlsx 撑到几百兆，供应商
   习惯发「一个表格 + 一个图片文件夹」，这条路是给他们的。
3. **格里填 http(s) 直链**：默认关闭。服务端按用户给的地址发请求就是 SSRF —— 内网
   地址、云元数据服务（169.254.169.254）都能被诱导去访问，所以要管理员显式开启，
   并且这里对每一跳都做「解析出来的 IP 必须是公网地址」的校验。

素材库只收 jpg/png/webp（``app/api/v1/files.py`` 的 ``_ALLOWED``）。gif/bmp/tiff 有
Pillow 时转成 png，没有就跳过并说清原因；wmf/emf 直接拒 —— 从 Word 粘过来的图常是
这两种，浏览器根本不显示，收进来只会变成一堆裂图。
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import re
import socket
import zipfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from typing import IO, Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx

from app.services.excel_images import EmbeddedImage, sniff_image
from app.services.product_import import ProductRow, ProductSheet, split_multi

ROLE_MAIN = "main"
ROLE_PRODUCT = "product"
ROLE_SCENE = "scene"

# 表里的图片列 → 角色。主图列只取一张当封面，另外两种可以有多列。
COLUMN_ROLES: dict[str, str] = {
    "main_image": ROLE_MAIN,
    "images": ROLE_PRODUCT,
    "scene_images": ROLE_SCENE,
}

# 素材库直接收的三种格式（files.py 的 _ALLOWED），以及能转成 png 的几种。
DIRECT_FORMATS: dict[str, str] = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
CONVERTIBLE_FORMATS: frozenset[str] = frozenset({"gif", "bmp", "tiff"})

# 单行图片上限。给个上限是因为「文件名以编号开头就归给这行」这条约定很容易撞上
# 一个装了几百张图的压缩包，一行挂 200 张图对谁都没好处。
MAX_ROW_IMAGES = 10
MAX_ROW_SCENES = 30

# 单张图的兜底上限（接口层用 settings 覆盖）。和 excel_images 的默认值保持一致。
MAX_IMAGE_BYTES = 20 * 1024 * 1024

# zip 里按扩展名先粗筛一遍（真正认格式还是靠 sniff_image 读魔术字节），
# 免得把整个压缩包里的 pdf/mp4 都读进内存。
BUNDLE_IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
)
_XLSX_SUFFIXES: tuple[str, ...] = (".xlsx", ".xlsm", ".xls")

# 文件名里带这些字样的，按场景图处理（约定归属那条路要用）。
_SCENE_WORDS = re.compile(r"场景|scene|效果图|实景", re.IGNORECASE)
_URL_PREFIX = re.compile(r"^https?://", re.IGNORECASE)

URL_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "RiChangPIM-import/1.0"


class MediaError(Exception):
    """这张图/这个包拿不到，原因是人话，直接进 warnings 或行级失败原因。"""


@dataclass(frozen=True)
class ImageBlob:
    """一张已经确认可入库的图（字节就位、格式已认）。

    ``sha256`` 是批内去重的键：同一张场景图被三十行引用时只该上传一次、建一条
    Attachment。frozen 是为了能进 set/dict。
    """

    data: bytes
    ext: str
    content_type: str
    sha256: str
    name: str  # 建议的文件名（Attachment.file_name / SceneImage.name 用）
    source: str  # anchor/dispimg/richvalue（内嵌）| zip | convention | url
    role: str = ROLE_PRODUCT

    @property
    def size(self) -> int:
        return len(self.data)


def _safe_name(name: str, *, fallback: str) -> str:
    """取文件名部分并压到库里的长度上限（Attachment.file_name 是 255）。"""
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip() or fallback
    return base[:200]


def _pillow_image() -> Any | None:
    """拿 ``PIL.Image``，没装 Pillow 返回 None。

    Pillow 在 requirements.txt 里带 ``; python_version < '3.13'``，是条件依赖，
    所以这里和 ``thumbnails.encode_thumbnail`` 一样在函数内 import。
    """
    try:
        from PIL import Image
    except ModuleNotFoundError:
        return None
    return Image


def _convert_to_png(data: bytes) -> bytes | None:
    """gif/bmp/tiff → png。转不动就返回 None（调用方给出提示，不报错）。"""
    module = _pillow_image()
    if module is None:
        return None
    try:
        with module.open(io.BytesIO(data)) as opened:
            image = opened.convert("RGBA" if opened.mode in {"RGBA", "LA", "P"} else "RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
    except Exception:
        return None


def make_blob(
    data: bytes,
    *,
    name: str,
    source: str,
    role: str = ROLE_PRODUCT,
    max_bytes: int | None = None,
) -> tuple[ImageBlob | None, str | None]:
    """字节 → ImageBlob，认不了/太大就返回 (None, 原因)。

    格式一律按魔术字节认，不看扩展名：改过后缀的 jpg 在供应商表里极常见，而
    ``files.py`` 是按 oss_key 的后缀决定响应 Content-Type 的，认错后缀在浏览器里
    就是一张裂图。
    """
    if not data:
        return None, f"{name}：内容是空的"
    if max_bytes is not None and len(data) > max_bytes:
        return None, f"{name}：超过单张体积上限 {max_bytes} 字节，已跳过"
    sniffed = sniff_image(data)
    if sniffed is None:
        return None, f"{name}：不是可识别的图片格式，已跳过"
    ext, content_type = sniffed
    if ext not in DIRECT_FORMATS:
        if ext not in CONVERTIBLE_FORMATS:
            return None, f"{name}：{ext} 不是支持的图片格式（只收 jpg/png/webp），已跳过"
        if _pillow_image() is None:
            return None, f"{name}：{ext} 要转成 png 才能入库，但服务端没有安装 Pillow"
        converted = _convert_to_png(data)
        if converted is None:
            return None, f"{name}：{ext} 转成 png 时失败（文件可能已损坏），已跳过"
        data, ext, content_type = converted, "png", "image/png"
        name = f"{name.rsplit('.', 1)[0]}.png"
    base = _safe_name(name, fallback=f"image.{ext}")
    if "." not in base:
        # 内嵌图片本来没有文件名，补上后缀 —— files.py 是按 oss_key 的后缀回
        # Content-Type 的，素材库列表里也靠它显示类型。
        base = f"{base}.{ext}"
    return (
        ImageBlob(
            data=data,
            ext=ext,
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
            name=base,
            source=source,
            role=role,
        ),
        None,
    )


class BundleFile:
    """压缩包里的一个成员。字节是**按需**读的。

    真实供应商包的量级是「4000+ 张图、解压后 400MB」（圣奥那份样本就是 4242 张、
    394MB）。整包读进内存等于一次导入常驻几百兆，两个人同时导就把容器打爆；而绝大
    多数成员在一次导入里只会被读一次，缓着也没有收益。所以这里只记「在哪、多大」，
    要用时才从压缩包里解出那一个成员。

    ``data`` 可能抛 :class:`MediaError`（成员损坏，或者解出来比压缩头声称的大）——
    调用方按「这一张图没拿到」处理，不要让整行/整批失败。
    """

    __slots__ = ("name", "size", "_data", "_loader")

    def __init__(
        self,
        name: str,
        data: bytes | None = None,
        *,
        size: int | None = None,
        loader: Callable[[], bytes] | None = None,
    ) -> None:
        self.name = name
        self._data = data
        self._loader = loader
        self.size = size if size is not None else len(data or b"")

    @property
    def data(self) -> bytes:
        if self._data is not None:
            return self._data
        if self._loader is None:
            return b""
        return self._loader()

    def __repr__(self) -> str:  # 报错信息里只该出现路径和体积，不该是一堆字节
        return f"BundleFile(name={self.name!r}, size={self.size})"


def _read_member(zf: zipfile.ZipFile, name: str, limit: int | None) -> bytes:
    """从压缩包里解一个成员出来，顺手复核体积。

    ``load_bundle`` 是按中央目录里声称的 ``file_size`` 先筛一遍的，而筛查和真读是
    两个时刻、两段代码；这里多读一个字节就能自己守住上限，代价是零。压缩头往小了
    写（解压炸弹的经典手法）由 zipfile 自己挡：它按声称的大小截断输出，CRC 随即对
    不上并抛 ``BadZipFile``，调用方按「这张图没拿到」处理。
    """
    with zf.open(name) as handle:
        data = handle.read() if limit is None else handle.read(limit + 1)
    if limit is not None and len(data) > limit:
        raise MediaError(f"{name}：解压后超过单张体积上限 {limit} 字节，已跳过")
    return data


def _key(name: str) -> str:
    """查找用的键：只取文件名、转小写。

    用户在格里写的是「chair-1.jpg」，压缩包里可能是「图片/chair-1.JPG」——
    带目录、带大小写差异是常态，按 basename + lower 对齐。
    """
    return name.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def _is_junk(name: str) -> bool:
    """macOS 打包出来的伴生文件和 Excel 的锁文件，不能当图片看。"""
    base = _key(name)
    return name.startswith("__MACOSX/") or base.startswith(("._", "~$", "."))


@dataclass
class ImportBundle:
    """上传上来的东西：一份 xlsx，可能还带一堆图片文件。

    ``zip_file`` 不为 None 时，图片还在压缩包里没解出来（见 :class:`BundleFile`），
    整个导入过程都要保持它打开；用完由接口层调 ``close()``。
    """

    xlsx: bytes
    files: dict[str, BundleFile] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    book_name: str = ""
    zip_file: zipfile.ZipFile | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # 名字排一次序存下来。find() 的兜底匹配和 match_prefix() 都要按名字扫一遍，
        # 每行现排一次的话，4000 行 × 4000 个成员就是几亿次比较 —— 纯浪费。
        self._names: tuple[str, ...] = tuple(sorted(self.files))

    def close(self) -> None:
        if self.zip_file is not None:
            self.zip_file.close()
            self.zip_file = None

    def find(self, token: str) -> BundleFile | None:
        """按格里写的名字找文件。找不到时再按「不带扩展名」试一次。

        用户经常只写「chair-1」，或者写了 .jpg 而压缩包里是 .jpeg —— 这种就近匹配
        比让整行失败有用得多。
        """
        key = _key(token)
        if not key:
            return None
        hit = self.files.get(key)
        if hit is not None:
            return hit
        stem = key.rsplit(".", 1)[0]
        for name in self._names:
            if name.rsplit(".", 1)[0] == stem:
                return self.files[name]
        return None

    def match_prefix(self, product_no: str) -> list[BundleFile]:
        """文件名以产品编号开头的图片，按文件名排序。

        紧跟编号后面必须是分隔符（或中文字样）—— 否则 ``SUNON-001`` 会把
        ``SUNON-0012.jpg``（另一个产品）也吃进来；只挡 ASCII 字母数字，是为了让
        ``SUNON-001场景.jpg`` 这种中文后缀还能归上。
        """
        prefix = product_no.strip().lower()
        if not prefix:
            return []
        out: list[BundleFile] = []
        for name in self._names:
            stem = name.rsplit(".", 1)[0]
            if not stem.startswith(prefix):
                continue
            rest = stem[len(prefix) :]
            if rest and rest[0].isascii() and rest[0].isalnum():
                continue
            out.append(self.files[name])
        return out


def load_bundle(
    payload: bytes | IO[bytes],
    *,
    max_image_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> ImportBundle:
    """把上传的东西认成「裸 xlsx」或「zip 包」。

    xlsx 本身就是个 zip，所以不能只看「是不是 zip」：里面有 ``xl/workbook.xml`` 的
    就是表格本体。不是 zip 时原样透传 —— 让 ``read_product_sheet`` 去报「文件解析
    失败」，那里的话术对用户更有用（可能是 .xls 或者加密文件）。

    ``payload`` 可以是字节，也可以是**已打开的文件对象**。接口层传的是
    Starlette ``UploadFile`` 的底层临时文件：大上传本来就落在磁盘上，再 ``read()``
    成 bytes 只是白占一份内存。走文件对象这条路时压缩包保持打开，图片按需一张张解
    （见 :class:`BundleFile`），调用方用完要 ``ImportBundle.close()``。

    先看 zip 头里的 ``file_size`` 再决定要不要收：解压炸弹（几十 KB 解出几个 G）
    只要读了就晚了。``max_total_bytes`` 是整包图片的预算，超了就停下并留一条提示。
    真读那一下还会再复核一次体积（``_read_member``），因为压缩头声称的大小可以撒谎。
    """
    source: IO[bytes] = io.BytesIO(payload) if isinstance(payload, bytes | bytearray) else payload
    source.seek(0)
    is_zip = zipfile.is_zipfile(source)
    source.seek(0)
    if not is_zip:
        return ImportBundle(xlsx=payload if isinstance(payload, bytes) else source.read())

    zf = zipfile.ZipFile(source)
    try:
        names = [name for name in zf.namelist() if not name.endswith("/")]
        if "xl/workbook.xml" in names:
            # 表格本体。整份读进来：read_product_sheet / extract_embedded_images 都要字节。
            source.seek(0)
            xlsx = payload if isinstance(payload, bytes) else source.read()
            zf.close()
            return ImportBundle(xlsx=xlsx)

        members = [name for name in names if not _is_junk(name)]
        books = sorted(name for name in members if name.lower().endswith(_XLSX_SUFFIXES))
        if not books:
            raise MediaError("压缩包里没有找到表格文件（.xlsx），请把 Excel 一起打进去")

        warnings: list[str] = []
        if len(books) > 1:
            warnings.append(f"压缩包里有 {len(books)} 个表格，只导入了 {books[0]}")

        files: dict[str, BundleFile] = {}
        total = 0
        for member in sorted(members):
            if member == books[0]:
                continue
            if not any(member.lower().endswith(suffix) for suffix in BUNDLE_IMAGE_SUFFIXES):
                continue
            info = zf.getinfo(member)
            if max_image_bytes is not None and info.file_size > max_image_bytes:
                warnings.append(f"{member}：超过单张体积上限 {max_image_bytes} 字节，已跳过")
                continue
            if max_total_bytes is not None and total + info.file_size > max_total_bytes:
                warnings.append(
                    f"压缩包里的图片总量超过 {max_total_bytes} 字节，{member} 之后的都没读"
                )
                break
            key = _key(member)
            if key in files:
                warnings.append(f"压缩包里有多个「{key}」，只用了 {files[key].name}")
                continue
            files[key] = BundleFile(
                member,
                size=info.file_size,
                loader=partial(_read_member, zf, member, max_image_bytes),
            )
            total += info.file_size

        return ImportBundle(
            xlsx=zf.read(books[0]), files=files, warnings=warnings, book_name=books[0], zip_file=zf
        )
    except Exception:
        zf.close()
        raise


def _resolve_host(host: str, port: int) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)]


def _is_public_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        # ::ffff:127.0.0.1 这种映射地址在 IPv6 上 is_loopback 是 False，
        # 不摊平就等于给回环开了个后门。
        ip = mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def guard_url(
    url: str, *, resolve: Callable[[str, int], Iterable[str]] = _resolve_host
) -> str | None:
    """能抓返回 None，不能抓返回人话原因。

    服务端替用户去 GET 一个任意地址就是 SSRF：内网服务（http://10.0.0.5/admin）、
    云上的元数据接口（169.254.169.254，能拿到实例凭证）都是现成的目标。所以先把
    域名解析成 IP，逐个要求是公网地址，再发请求。

    残留风险说明：解析和真正建连之间还有一次 DNS 查询（DNS rebinding），要彻底
    堵住得把连接固定到已校验的 IP 上。这条路默认关闭（配置项
    ``PRODUCT_IMPORT_ALLOW_URL_FETCH``），开之前应该明确只在可信来源的表上用。

    ``resolve`` 可注入，是为了让单元测试不碰 DNS —— 真去解析域名的用例在 CI 里
    必然时快时慢，还会因为网络策略变红。
    """
    raw = url.strip()
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        return f"{raw}：地址解析不了"
    if parsed.scheme.lower() not in {"http", "https"}:
        return f"{raw}：只支持 http/https 图片直链"
    host = parsed.hostname
    if not host:
        return f"{raw}：地址里没有主机名"
    try:
        addresses = list(resolve(host, port or (443 if parsed.scheme.lower() == "https" else 80)))
    except OSError:
        return f"{raw}：域名解析失败"
    if not addresses:
        return f"{raw}：域名解析不到地址"
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return f"{raw}：解析出的地址不合法（{address}）"
        if not _is_public_address(ip):
            return f"{raw}：指向内网/保留地址（{address}），已拒绝"
    return None


def _name_from_url(url: str) -> str:
    path = urlparse(url).path
    return _safe_name(unquote(path), fallback="image")


def fetch_image_url(
    url: str,
    *,
    timeout: float = URL_TIMEOUT_SECONDS,
    max_bytes: int = MAX_IMAGE_BYTES,
    max_redirects: int = 2,
    client: httpx.Client | None = None,
    resolve: Callable[[str, int], Iterable[str]] = _resolve_host,
) -> tuple[bytes, str]:
    """抓一张外链图片，返回 (字节, 建议文件名)。拿不到就抛 ``MediaError``。

    重定向自己跟，每一跳都重新过一遍 ``guard_url``：让 httpx 自动跟的话，一个公网
    域名可以 302 到 ``http://169.254.169.254/``，前面的校验就白做了。

    响应体边读边数，超限立刻掐断（只信 Content-Length 会被没有这个头、或者故意写
    小了的服务端绕过）。
    """
    current = url.strip()
    owns_client = client is None
    session = client or httpx.Client(timeout=timeout, follow_redirects=False)
    try:
        for _ in range(max_redirects + 1):
            reason = guard_url(current, resolve=resolve)
            if reason:
                raise MediaError(reason)
            try:
                with session.stream(
                    "GET", current, headers={"User-Agent": _USER_AGENT}
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location", "")
                        if not location:
                            raise MediaError(f"{current}：重定向没给出目标地址")
                        current = str(httpx.URL(current).join(location))
                        continue
                    if response.status_code != 200:
                        raise MediaError(f"{current}：HTTP {response.status_code}")
                    declared = response.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > max_bytes:
                        raise MediaError(f"{current}：图片超过上限 {max_bytes} 字节")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise MediaError(f"{current}：图片超过上限 {max_bytes} 字节")
                        chunks.append(chunk)
                    return b"".join(chunks), _name_from_url(current)
            except httpx.HTTPError as exc:
                raise MediaError(f"{current}：抓取失败（{type(exc).__name__}）") from exc
        raise MediaError(f"{url}：重定向次数超过 {max_redirects} 次")
    finally:
        if owns_client:
            session.close()


@dataclass
class RowMedia:
    """一行最终该配的图。``cover`` 就是产品封面（``ProductImage.is_cover``）。"""

    excel_row: int
    cover: ImageBlob | None = None
    images: list[ImageBlob] = field(default_factory=list)  # 封面之外的产品图
    scenes: list[ImageBlob] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def blobs(self) -> list[ImageBlob]:
        """要上传的全部图，封面在最前（上传顺序 = 展示顺序）。"""
        return ([self.cover] if self.cover is not None else []) + self.images + self.scenes

    @property
    def count(self) -> int:
        return len(self.blobs)

    @property
    def sources(self) -> set[str]:
        """图是从哪来的（anchor/dispimg/richvalue/zip/convention/url），进导入结果统计。"""
        return {blob.source for blob in self.blobs}


class MediaResolver:
    """把「表 + 内嵌图 + 压缩包 + 外链」摊成每行一份 ``RowMedia``。

    只做归属和取字节，不碰 ORM、不碰 MinIO —— 归属算错（图挂到相邻产品身上）是这条
    链路里最难被发现的错，所以它必须能在单元层被逐条钉住。
    """

    def __init__(
        self,
        sheet: ProductSheet,
        *,
        embedded: Sequence[EmbeddedImage] = (),
        bundle: ImportBundle | None = None,
        url_fetcher: Callable[[str], tuple[bytes, str]] | None = None,
        max_images: int = MAX_ROW_IMAGES,
        max_scenes: int = MAX_ROW_SCENES,
        max_image_bytes: int | None = MAX_IMAGE_BYTES,
    ) -> None:
        self._sheet = sheet
        self._bundle = bundle
        self._fetch = url_fetcher
        self._max_images = max_images
        self._max_scenes = max_scenes
        self._max_bytes = max_image_bytes
        # 图片列 → 角色，按列号升序：一行里的图从左往右取，封面选谁才是可复现的。
        self._columns: list[tuple[int, str]] = sorted(
            (column.excel_col, COLUMN_ROLES[column.key])
            for column in sheet.image_columns
            if column.key in COLUMN_ROLES
        )
        self.warnings: list[str] = []
        self._by_row: dict[int, list[EmbeddedImage]] = {}
        data_rows = {row.excel_row for row in sheet.rows}
        orphans: dict[object, int] = {}
        for image in embedded:
            if image.row is None or image.row not in data_rows:
                # 落在表头、说明行或空行上的图。说清楚而不是静默丢：浮动图片被拖到
                # 标题行上方是常见的手滑，用户看到提示才知道要把图挪进数据行。
                where = image.row if image.row is not None else "?"
                orphans[where] = orphans.get(where, 0) + 1
                continue
            self._by_row.setdefault(image.row, []).append(image)
        for where, count in orphans.items():
            self.warnings.append(f"第 {where} 行不是数据行，上面的 {count} 张图片没有导入")
        # 格里显式写过的文件名。「按编号前缀自动归属」要避开它们，否则同一张图会
        # 既按文件名进 A 行、又按编号前缀进 B 行。
        self._referenced: set[str] = set()
        for row in sheet.rows:
            for key in COLUMN_ROLES:
                for token in split_multi(row.get(key)):
                    if not _URL_PREFIX.match(token):
                        self._referenced.add(_key(token))

    def _role_for(self, image: EmbeddedImage) -> str:
        """内嵌图的角色 = 它落在哪个图片列上。"""
        if not self._columns:
            # 表里没有图片列（供应商表里常见：图片那一列的表头干脆是空的），整行的图
            # 都按产品图处理，第一张作封面。总比整批图片凭空消失好。
            return ROLE_PRODUCT
        col = image.col or 0
        end = image.col_end or col + 1
        for excel_col, role in self._columns:
            if col <= excel_col < max(end, col + 1):
                return role
        # 浮动图片被拖到了表格右边的空白处：仍然算这一行的产品图。
        return ROLE_PRODUCT

    def _from_token(
        self, token: str, *, role: str, excel_row: int
    ) -> tuple[ImageBlob | None, str | None]:
        """格里的一个值 → 图。带 http(s) 的当直链抓，其余当压缩包里的文件名找。"""
        if _URL_PREFIX.match(token):
            if self._fetch is None:
                return None, f"第 {excel_row} 行的图片直链未导入（外链抓取没有开启）：{token}"
            try:
                data, name = self._fetch(token)
            except Exception as exc:
                # 一个链接抓不到不该让整行失败：图缺一张能补，整行退回要重导一轮。
                return None, f"第 {excel_row} 行：{exc}"
            return make_blob(data, name=name, source="url", role=role, max_bytes=self._max_bytes)
        if self._bundle is None or not self._bundle.files:
            return None, f"第 {excel_row} 行填了图片名「{token}」，但上传的文件里没有图片"
        found = self._bundle.find(token)
        if found is None:
            return None, f"第 {excel_row} 行的图片「{token}」在压缩包里没有找到"
        return self._blob_from_file(found, source="zip", role=role)

    def _blob_from_file(
        self, found: BundleFile, *, source: str, role: str
    ) -> tuple[ImageBlob | None, str | None]:
        """压缩包成员 → 图。字节是这一刻才解出来的，解不动只废这一张。"""
        try:
            data = found.data
        except MediaError as exc:
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001 - 坏压缩包的报错五花八门，都当「这张图没拿到」
            return None, f"{found.name}：从压缩包里解出来失败（{type(exc).__name__}），已跳过"
        return make_blob(data, name=found.name, source=source, role=role, max_bytes=self._max_bytes)

    def resolve(self, row: ProductRow, *, product_no: str = "") -> RowMedia:
        """算出这一行该配哪些图。找不到的图只留提示，不让整行失败。

        三种来源按固定顺序收，封面才是可复现的：先格里写的名字/直链（主图列 → 产品图
        列 → 场景图列），再这一行的内嵌图，最后才是「文件名以编号开头」的约定 ——
        约定只在这一行一个图片名都没写时才启用，否则用户明明写了名字却还被塞进来
        一堆同前缀的图。
        """
        media = RowMedia(excel_row=row.excel_row)
        buckets: dict[str, list[ImageBlob]] = {ROLE_MAIN: [], ROLE_PRODUCT: [], ROLE_SCENE: []}
        seen: set[str] = set()

        def keep(blob: ImageBlob | None, reason: str | None) -> None:
            if blob is None:
                if reason:
                    media.warnings.append(reason)
                return
            if blob.sha256 in seen:
                # 同一张图在一行里被引了两遍（复制粘贴出来的表很常见），只留一份。
                return
            seen.add(blob.sha256)
            buckets[blob.role].append(blob)

        named = False
        for key, role in COLUMN_ROLES.items():
            for token in split_multi(row.get(key)):
                named = True
                keep(*self._from_token(token, role=role, excel_row=row.excel_row))

        stem = product_no.strip() or f"row{row.excel_row}"
        for image in self._by_row.get(row.excel_row, []):
            keep(
                *make_blob(
                    image.data,
                    name=f"{stem}-{image.order}",
                    source=image.source,
                    role=self._role_for(image),
                    max_bytes=self._max_bytes,
                )
            )

        if not named and self._bundle is not None:
            for found in self._bundle.match_prefix(product_no):
                if _key(found.name) in self._referenced:
                    continue
                role = ROLE_SCENE if _SCENE_WORDS.search(found.name) else ROLE_PRODUCT
                keep(*self._blob_from_file(found, source="convention", role=role))
        return self._finish(media, buckets)

    def _finish(self, media: RowMedia, buckets: dict[str, list[ImageBlob]]) -> RowMedia:
        """定封面、按上限截断。

        封面取主图列的第一张；主图列没图就取最靠左的产品图 —— 产品列表页全靠
        ``is_cover`` 那张显示，宁可猜一张也不要让整页都是占位图。
        """
        mains = buckets[ROLE_MAIN]
        if len(mains) > 1:
            media.warnings.append(
                f"第 {media.excel_row} 行主图列有多张图，第一张作封面，其余按产品图导入"
            )
        pool = mains + buckets[ROLE_PRODUCT]
        if pool:
            total = len(pool)
            media.cover = replace(pool[0], role=ROLE_MAIN)
            extra = [replace(blob, role=ROLE_PRODUCT) for blob in pool[1:]]
            if total > self._max_images:
                media.warnings.append(
                    f"第 {media.excel_row} 行有 {total} 张产品图，只导入前 {self._max_images} 张"
                )
                extra = extra[: self._max_images - 1]
            media.images = extra
        scenes = [replace(blob, role=ROLE_SCENE) for blob in buckets[ROLE_SCENE]]
        if len(scenes) > self._max_scenes:
            media.warnings.append(
                f"第 {media.excel_row} 行有 {len(scenes)} 张场景图，只导入前 {self._max_scenes} 张"
            )
            scenes = scenes[: self._max_scenes]
        media.scenes = scenes
        return media


@dataclass(frozen=True)
class UploadedObject:
    """已经落进 MinIO 的一个对象，接口层拿它建 ``Attachment``。"""

    oss_key: str
    file_url: str
    content_type: str
    size: int
    sha256: str
    name: str


class MediaUploader:
    """把 ``ImageBlob`` 传进 MinIO，同一 ``sha256`` 只传一次。

    ``client`` 是注入的（接口层传 ``get_minio_client()``），所以这个类也能进单元层。
    minio 的客户端是同步阻塞的：端点里必须用 ``asyncio.to_thread`` 包起来，否则一份
    两百张图的表会把整个事件循环堵住十几秒。

    批内去重的收益很实际：一张「品牌形象场景图」被三十行引用时，只传一次、只建一条
    Attachment，三十个产品共用它（``product_scene_image`` 本来就是多对多）。
    """

    def __init__(self, client: Any, bucket: str, *, prefix: str = "image") -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix
        self._cache: dict[str, UploadedObject] = {}
        self._bucket_checked = False

    @property
    def uploaded(self) -> int:
        """实际传上去的对象数（去重之后）。"""
        return len(self._cache)

    def ensure_bucket(self) -> None:
        """桶不存在就建一次。已存在/并发撞车都咽掉 —— 和 ``files.py`` 一个路子。"""
        if self._bucket_checked:
            return
        self._bucket_checked = True
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        except Exception:
            # 真连不上对象存储的话，下面的 put_object 会给出更准确的报错。
            pass

    def get(self, sha256: str) -> UploadedObject | None:
        return self._cache.get(sha256)

    def upload(self, blob: ImageBlob) -> UploadedObject:
        """传一张图，返回入库要用的字段。传不上去抛 ``MediaError``。

        object key 的格式和 ``files.py`` 的上传接口保持一致
        （``image/{uuid4}.{ext}``）：``/files/{oss_key}`` 那个下载端点是按后缀决定
        响应 Content-Type 的，后缀不对浏览器里就是一张裂图。
        """
        hit = self._cache.get(blob.sha256)
        if hit is not None:
            return hit
        self.ensure_bucket()
        object_key = f"{self._prefix}/{uuid4().hex}.{blob.ext}"
        try:
            self._client.put_object(
                self._bucket,
                object_key,
                data=io.BytesIO(blob.data),
                length=blob.size,
                content_type=blob.content_type,
            )
        except Exception as exc:
            raise MediaError(f"{blob.name}：上传到对象存储失败（{type(exc).__name__}）") from exc
        record = UploadedObject(
            oss_key=object_key,
            file_url=f"/files/{object_key}",
            content_type=blob.content_type,
            size=blob.size,
            sha256=blob.sha256,
            name=blob.name,
        )
        self._cache[blob.sha256] = record
        return record
