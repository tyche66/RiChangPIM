"""缩略图服务的单元用例（app/services/thumbnails.py）。

覆盖的是「滚轮卡顿」那条修法的服务端契约：宽度档位、派生对象 key、按短边缩、
不放大、读穿缓存只编码一次、替换文件时把派生对象清干净。

这些逻辑此前没有任何后端测试 —— 它原来长在 app/api/v1/files.py 里，那个模块为了
get_db 牵连 app.core.database，按 tests/unit/conftest.py 的约定进不了单元层，
所以先把它抽成叶子模块再测（不是为了测试改结构，是那条约定要求的方向）。
"""

import io

import pytest

from app.services.thumbnails import (
    THUMB_PREFIX,
    THUMB_WIDTHS,
    encode_thumbnail,
    purge_thumbnails,
    thumb_object_key,
    thumbnail_bytes,
)

# Pillow 在 backend/requirements.txt 里带 `; python_version < '3.13'`（10.2.0 在
# 3.13+ 上没轮子），所以宿主 python 3.14 上可能根本没有它。缺它时跳过要解码的用例
# 而不是让它们红：一条「没装依赖就必红」的用例会永久污染验收信号。key/档位这些
# 纯字符串逻辑不依赖 Pillow，照跑。
try:
    from PIL import Image

    HAS_PILLOW = True
except ModuleNotFoundError:  # pragma: no cover - 取决于宿主环境
    HAS_PILLOW = False

requires_pillow = pytest.mark.skipif(not HAS_PILLOW, reason="宿主没装 pillow（条件依赖）")


def _source_jpeg(width: int, height: int) -> bytes:
    """造一张能被解码的测试图。用渐变而不是纯色：纯色 WebP 压到几十字节，
    「缩完比原图小」这种断言就变得没有意义。"""
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for x in range(width):
        for y in range(height):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, (x * y) % 256)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


class _FakeMinioObject:
    """minio 的 get_object 返回的是个要 close()+release_conn() 的流对象，
    这里照抄那套形状 —— 服务里 finally 会调它们，假对象少一个方法就会 AttributeError。"""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeMinio:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects: dict[str, bytes] = dict(objects or {})
        self.gets: list[str] = []
        self.puts: list[tuple[str, int, str]] = []
        self.removed: list[str] = []
        self.streams: list[_FakeMinioObject] = []
        self.remove_fails_for: set[str] = set()

    def get_object(self, bucket: str, key: str):
        self.gets.append(key)
        if key not in self.objects:
            # 真实的 minio 抛 S3Error(NoSuchKey)；服务只 except Exception，
            # 所以这里抛什么都行，用 KeyError 免得为了测试引进 minio 依赖。
            raise KeyError(key)
        stream = _FakeMinioObject(self.objects[key])
        self.streams.append(stream)
        return stream

    def put_object(self, bucket: str, key: str, data, length: int, content_type: str) -> None:
        self.puts.append((key, length, content_type))
        self.objects[key] = data.read()

    def remove_object(self, bucket: str, key: str) -> None:
        self.removed.append(key)
        if key in self.remove_fails_for:
            raise RuntimeError(f"boom: {key}")
        self.objects.pop(key, None)


def test_thumb_widths_cover_the_widths_the_frontend_requests():
    """档位是白名单，前端只会请求这几个值。

    192 / 480 分别是 frontend/src/views/Products.vue 里的 TABLE_THUMB_WIDTH 和
    TILE_THUMB_WIDTH：这两个数一旦从档位里消失，列表会收 422、封面全变裂图，
    所以在这里钉住 —— 改档位必须同时改那两个常量。
    """
    assert 192 in THUMB_WIDTHS
    assert 480 in THUMB_WIDTHS
    assert THUMB_WIDTHS == (96, 192, 240, 480, 960)
    assert len(set(THUMB_WIDTHS)) == len(THUMB_WIDTHS)
    assert list(THUMB_WIDTHS) == sorted(THUMB_WIDTHS)


def test_thumb_object_key_keeps_original_key_and_is_width_scoped():
    key = thumb_object_key("products/2026/07/abc123.jpg", 192)
    assert key == f"{THUMB_PREFIX}/w192/products/2026/07/abc123.jpg.webp"
    # 原始 key 原样嵌在里面：删原图时能按 key 精确清理派生物。
    assert "products/2026/07/abc123.jpg" in key
    # 每个宽度一个独立对象，否则两个档位会互相覆盖。
    keys = {thumb_object_key("products/abc.jpg", w) for w in THUMB_WIDTHS}
    assert len(keys) == len(THUMB_WIDTHS)


@requires_pillow
def test_encode_thumbnail_shrinks_short_edge_and_returns_webp():
    """按短边缩：4:3 的图要 w=192 应得到 256×192，而不是长边 192 的 192×144。

    列表里图是 object-fit: cover 铺满方框的，按长边缩会让短边不够、撑开发虚。
    """
    source = _source_jpeg(800, 600)
    thumb = encode_thumbnail(source, 192)

    with Image.open(io.BytesIO(thumb)) as decoded:
        assert decoded.format == "WEBP"
        assert min(decoded.size) == 192
        assert decoded.size == (256, 192)
    assert len(thumb) < len(source)


@requires_pillow
def test_encode_thumbnail_never_upscales():
    """原图比档位还小就原样编码 —— 放大只会更糊、字节还更多。"""
    source = _source_jpeg(100, 80)
    thumb = encode_thumbnail(source, 960)

    with Image.open(io.BytesIO(thumb)) as decoded:
        assert decoded.size == (100, 80)


@requires_pillow
def test_thumbnail_bytes_encodes_once_then_serves_from_cache(monkeypatch):
    """读穿缓存：第一次现缩并回写，第二次只读缓存，不再解码。

    这条是「滚轮卡顿」修法的核心 —— 如果每次请求都重新解一张 1200 万像素的图，
    首页字节数是降了，服务端 CPU 反而更糟。断言 put_object 只发生一次。
    """
    oss_key = "products/cover.jpg"
    source = _source_jpeg(800, 600)
    client = _FakeMinio({oss_key: source})
    monkeypatch.setattr("app.services.thumbnails.get_minio_client", lambda: client)

    first = thumbnail_bytes(oss_key, 192)

    thumb_key = thumb_object_key(oss_key, 192)
    # 先摸缓存（miss），再读原图。
    assert client.gets == [thumb_key, oss_key]
    assert len(client.puts) == 1
    assert client.puts[0][0] == thumb_key
    assert client.puts[0][1] == len(first)
    assert client.puts[0][2] == "image/webp"
    with Image.open(io.BytesIO(first)) as decoded:
        assert decoded.format == "WEBP"

    second = thumbnail_bytes(oss_key, 192)

    # 第二次只读了缓存那一个 key，没再碰原图、没再回写。
    assert client.gets == [thumb_key, oss_key, thumb_key]
    assert len(client.puts) == 1
    assert second == first
    # 每个取到的流都被 close + release_conn 了，不然连接池会漏。
    assert all(s.closed and s.released for s in client.streams)


@requires_pillow
def test_thumbnail_bytes_still_returns_image_when_cache_writeback_fails(monkeypatch):
    """回写缓存失败不该让这次请求 500，下次再试就行。"""
    oss_key = "products/cover.jpg"
    client = _FakeMinio({oss_key: _source_jpeg(400, 400)})

    def boom(*args, **kwargs):
        raise RuntimeError("minio 挂了")

    client.put_object = boom  # type: ignore[method-assign]
    monkeypatch.setattr("app.services.thumbnails.get_minio_client", lambda: client)

    thumb = thumbnail_bytes(oss_key, 96)

    with Image.open(io.BytesIO(thumb)) as decoded:
        assert decoded.size == (96, 96)


def test_purge_thumbnails_removes_one_object_per_width():
    """替换文件时把派生物清干净：新文件是新 uuid4，不会撞上旧 key，
    不清就永远留在桶里（存储泄漏，不是正确性问题，但反复替换会越堆越多）。"""
    oss_key = "products/old.jpg"
    client = _FakeMinio({thumb_object_key(oss_key, w): b"x" for w in THUMB_WIDTHS})

    purge_thumbnails(client, oss_key)

    assert client.removed == [thumb_object_key(oss_key, w) for w in THUMB_WIDTHS]
    assert client.objects == {}


def test_purge_thumbnails_keeps_going_when_one_delete_fails():
    """删某个宽度失败（比如那个档位从来没被访问过）不能打断后面几个 ——
    删除是替换文件流程里的收尾动作，这里抛出去会让替换整体失败。"""
    oss_key = "products/old.jpg"
    client = _FakeMinio()
    client.remove_fails_for = {thumb_object_key(oss_key, THUMB_WIDTHS[0])}

    purge_thumbnails(client, oss_key)

    assert client.removed == [thumb_object_key(oss_key, w) for w in THUMB_WIDTHS]
