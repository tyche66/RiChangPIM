"""列表缩略图：服务端按固定档位缩图 + MinIO 读穿缓存。

这些函数原来长在 ``app/api/v1/files.py`` 里。挪出来的原因是可测性：
``tests/unit/conftest.py`` 写死了单元层的约定 —— 单元测试只许 import 不牵连
``app.main`` / ``app.core.database`` 的叶子模块，而 files.py 为了 ``get_db``
必然牵连数据库，于是这套纯图像/键名逻辑一直没有单元覆盖。本模块只依赖
``app.core.config`` 和 ``app.core.minio_client``（两者都是叶子，import 不触网、
不连库），可以直接在单元层测。

为什么要有服务端缩略图：产品列表的表格缩略图是 64px 方框、卡片图约 240–360px，
原来直接把封面原图挂上去。实测库里 14 张封面有 13 张是 4000×3000（1200 万像素
一张），一页 20 条就是上亿像素的解码量和几百 MB 位图，滚动时浏览器反复丢弃/重
解码，必然掉帧（验收退回的第 3 条：滚轮卡顿）。改成服务端缩好再发之后，同一页
封面从 5,112,803 B 降到 20,030 B（w=192）/ 72,900 B（w=480）。

为什么宽度是白名单而不是任意值：任意宽度等于让外部随便触发一次全尺寸解码，并在
桶里堆无限多派生对象。不在白名单里的宽度由接口层直接回 422，**不静默退回原图**
—— 否则前端把宽度写错（比如写成 137）永远发现不了，性能又悄悄退回原点。
"""

from __future__ import annotations

import io

from app.core.config import settings
from app.core.minio_client import get_minio_client

# 档位要和前端用到的宽度对齐：frontend/src/views/Products.vue 里
# TABLE_THUMB_WIDTH=192、TILE_THUMB_WIDTH=480。改这里要同时改那边（有单元用例钉住）。
THUMB_WIDTHS = (96, 192, 240, 480, 960)
THUMB_PREFIX = "derived/thumb"


def thumb_object_key(oss_key: str, width: int) -> str:
    """派生对象的 key。

    带上原始 oss_key（含扩展名）而不是重新造名字：原图删掉时能按 key 精确清理，
    也方便在桶里一眼看出某个缩略图是谁的派生物。
    """
    return f"{THUMB_PREFIX}/w{width}/{oss_key}.webp"


def read_minio_object(client, object_key: str) -> bytes:
    obj = client.get_object(settings.MINIO_BUCKET, object_key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()


def encode_thumbnail(data: bytes, width: int) -> bytes:
    """把原图缩到短边 = width（不放大）并编码成 WebP。

    按短边而不是长边缩：列表里的图是 object-fit: cover 铺满方框的，按长边缩会把
    4000×3000 变成 240×180，再被撑到 240×240 就发虚。

    Pillow 故意在函数里 import，不放模块顶层：requirements.txt 里它带
    ``; python_version < '3.13'`` 标记（10.2.0 在 3.13+ 上没轮子、源码也编不过），
    顶层 import 会让整个 app 在 3.13+ 的机器上 import 就崩 —— 生产镜像是
    python:3.11-slim 不受影响，但宿主上 pytest 连 collect 都做不了（实测 3.14 上
    tests/unit 有两个模块直接 ModuleNotFoundError）。放进函数之后：缺 Pillow 时
    只有缩略图这一条路会报错，其余接口照常。
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.mode in {"RGBA", "LA", "P"}:
            image = image.convert("RGBA")
        elif image.mode != "RGB":
            image = image.convert("RGB")
        shortest = min(image.width, image.height)
        if shortest > width:
            scale = width / shortest
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=82, method=4)
        return buffer.getvalue()


def thumbnail_bytes(oss_key: str, width: int) -> bytes:
    """取缩略图字节：先查 MinIO 里的缓存对象，没有就现缩并回写。

    整个过程是阻塞的（minio 客户端同步 + Pillow 解码），调用方必须用
    ``asyncio.to_thread`` 包起来，别把事件循环按住几百毫秒。
    """
    client = get_minio_client()
    thumb_key = thumb_object_key(oss_key, width)
    try:
        return read_minio_object(client, thumb_key)
    except Exception:
        # 缓存不存在（首次访问）或读失败，都走下面现缩这条路。
        pass

    thumb = encode_thumbnail(read_minio_object(client, oss_key), width)
    try:
        client.put_object(
            settings.MINIO_BUCKET,
            thumb_key,
            data=io.BytesIO(thumb),
            length=len(thumb),
            content_type="image/webp",
        )
    except Exception:
        # 回写缓存失败不该影响这次响应，下次请求再试。
        pass
    return thumb


def purge_thumbnails(client, oss_key: str) -> None:
    """删掉某个原图对应的全部缓存缩略图。

    替换文件时原对象会被 remove_object 掉，但派生对象的 key 里带的是旧 oss_key
    （新文件是新的 uuid4，不会撞上），不清就永远留在桶里 —— 不是正确性问题，是
    反复替换后的存储泄漏。逐个删而不是 list_objects：宽度就 5 个，枚举更贵。
    """
    for width in THUMB_WIDTHS:
        try:
            client.remove_object(settings.MINIO_BUCKET, thumb_object_key(oss_key, width))
        except Exception:
            pass
