"""带图批量导入的真实集成测试（POST /api/v1/products/import）。

在专用 PostgreSQL 测试库上跑完整路径：zip 包里解出图片 → 传对象存储 → 建
attachment / scene_image → 按行开 SAVEPOINT 建产品并绑图。MinIO 由隔离的
``FakeMinio`` 接管，绝不触达真实对象存储；也不需要 Pillow —— 用例里全是 png，
走的是直接入库那条路，不经过格式转换。

覆盖：
- ``GET /products/import-template`` 能下载，且模板列名就是导入认的那套；
- zip 包里的图片按「主图列→封面、产品图列→附图、场景图列→场景图」绑定；
- 同一张图被多行引用时全批只传一次、只建一条 attachment / scene_image；
- 某行主数据不存在时只失败那一行，其余行照常入库（SAVEPOINT 隔离）；
- 外链抓取关闭时，直链只留提示、不发请求（SSRF 默认关）；
- ``skipIfExists`` 命中已存在编号时行进失败明细，原因写「已跳过」。
"""

import io
import zipfile
from uuid import uuid4

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import (
    Attachment,
    Brand,
    Category,
    Product,
    ProductImage,
    SceneImage,
    Supplier,
    product_scene_image,
)

# make_blob 按魔术字节认格式（不看后缀），所以一段 PNG 头就够用；尾部塞不同的字节是
# 为了让 sha256 不同 —— 批内去重、attachment 复用全是按 sha256 走的。
_PNG_HEAD = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
)
_COVER = _PNG_HEAD + b"cover"
_EXTRA = _PNG_HEAD + b"extra"
_SCENE = _PNG_HEAD + b"scene"


class FakeMinio:
    """隔离的 MinIO 替身：记录写入，绝不建立真实网络连接。"""

    def __init__(self):
        self.puts = []
        self.buckets = set()

    def bucket_exists(self, name):
        return name in self.buckets

    def make_bucket(self, name):
        self.buckets.add(name)

    def put_object(self, bucket, object_name, data, length, content_type=None):
        self.puts.append(
            {
                "bucket": bucket,
                "object_name": object_name,
                "length": length,
                "content_type": content_type,
            }
        )
        return length


@pytest.fixture
def minio(monkeypatch):
    from app.api.v1 import products as products_mod

    fake = FakeMinio()
    monkeypatch.setattr(products_mod, "get_minio_client", lambda: fake)
    return fake


async def _login_admin(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _seed_master(db: AsyncSession) -> dict[str, str]:
    """先建好品牌/供应商/分类：三者在库里都是 NOT NULL，导入不会替用户新建。"""
    suffix = uuid4().hex[:8]
    brand = Brand(brand_name=f"品牌{suffix}", description="import test")
    supplier = Supplier(supplier_name=f"供应商{suffix}", contact="t", phone="123")
    category = Category(category_name=f"分类{suffix}", level=1, sort=0)
    db.add_all([brand, supplier, category])
    await db.commit()
    return {
        "品牌": brand.brand_name,
        "供应商": supplier.supplier_name,
        "分类": category.category_name,
    }


def _sheet_bytes(rows: list[dict]) -> bytes:
    """按模板列名写一张表。列名带 * 也认（normalize_header 会把星号抹掉）。"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="产品")
    return buffer.getvalue()


def _zip_bytes(xlsx: bytes, images: dict[str, bytes]) -> bytes:
    """表格 + 图片打成一个 zip —— 这是「方式二」的上传形态。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("products.xlsx", xlsx)
        for name, data in images.items():
            zf.writestr(name, data)
    return buffer.getvalue()


async def _post_import(
    client: AsyncClient,
    headers: dict,
    payload: bytes,
    *,
    name: str = "products.zip",
    skip_if_exists: bool = False,
) -> dict:
    resp = await client.post(
        "/api/v1/products/import",
        files={"file": (name, payload, "application/octet-stream")},
        params={"skipIfExists": str(skip_if_exists).lower()},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    return body["data"]


async def _count(db: AsyncSession, target) -> int:
    result = await db.execute(select(func.count()).select_from(target))
    return result.scalar_one()


@pytest.mark.anyio
async def test_import_template_columns_are_the_ones_import_recognises(client: AsyncClient):
    """模板下载不能只是「有个文件」：它的列名必须正好是导入认得的那套。"""
    from app.services.product_import import resolve_header

    headers = await _login_admin(client)
    resp = await client.get("/api/v1/products/import-template", headers=headers)
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml" in resp.headers["content-type"]
    assert "products_import_template.xlsx" in resp.headers["content-disposition"]

    book = pd.ExcelFile(io.BytesIO(resp.content))
    assert book.sheet_names == ["产品", "填写说明"]
    columns = list(book.parse("产品").columns)
    for name in ("产品编号*", "产品名称*", "面价*", "主图", "产品图", "场景图"):
        assert name in columns
    # 认不出的列会进 unknown_headers 被忽略 —— 模板自己的列一个都不该落到那里。
    assert [name for name in columns if resolve_header(name) is None] == []
    notes = book.parse("填写说明")["填写说明"].tolist()
    assert any("嵌入单元格" in str(note) for note in notes)


@pytest.mark.anyio
async def test_zip_bundle_binds_cover_extra_and_shared_scene(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """zip 里的图片按列归位；跨行同图只传一次、只建一条 attachment / scene_image。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    no_a, no_b = f"IMP-{uuid4().hex[:6].upper()}", f"IMP-{uuid4().hex[:6].upper()}"
    xlsx = _sheet_bytes(
        [
            {
                "产品编号*": no_a,
                "产品名称*": "办公椅 A",
                "面价*": "1,280.00",
                "品牌": master["品牌"],
                "供应商": master["供应商"],
                "分类": master["分类"],
                "规格": "W650×D620×H1150mm",
                "颜色": "黑色,灰色",
                "数据来源": "2026 报价表",
                "主图": "cover.png",
                "产品图": "extra.png",
                "场景图": "scene.png",
            },
            {
                "产品编号*": no_b,
                "产品名称*": "办公椅 B",
                "面价*": "980",
                "品牌": master["品牌"],
                "供应商": master["供应商"],
                "分类": master["分类"],
                "规格": None,
                "颜色": None,
                "数据来源": None,
                # 和 A 行引用同一张图：批内去重要在这里体现。
                "主图": "cover.png",
                "产品图": None,
                "场景图": "scene.png",
            },
        ]
    )
    payload = _zip_bytes(xlsx, {"cover.png": _COVER, "图片/extra.png": _EXTRA, "scene.png": _SCENE})

    data = await _post_import(client, headers, payload)
    assert data["total"] == 2
    assert data["success_count"] == 2
    assert data["fail_count"] == 0, data["failures"]
    # A 行封面 + 附图 = 2，B 行只有封面 = 1。
    assert data["image_count"] == 3
    assert data["scene_image_count"] == 2
    # 去重后只有 cover / extra / scene 三个对象真的传上去。
    assert data["uploaded_count"] == 3
    assert data["image_sources"] == ["zip"]
    assert len(minio.puts) == 3
    assert {put["content_type"] for put in minio.puts} == {"image/png"}

    # 库里三条 attachment（cover / extra / scene 各一条），而不是「每行各存一份」。
    assert await _count(db, Attachment) == 3
    assert await _count(db, SceneImage) == 1
    assert await _count(db, ProductImage) == 3
    assert await _count(db, product_scene_image) == 2

    product_a = (
        await db.execute(select(Product).where(Product.product_no == no_a))
    ).scalar_one()
    # 带千分位的「1,280.00」要能认；文本列原样落库。
    assert product_a.face_price == 1280.0
    assert product_a.specification == "W650×D620×H1150mm"
    assert product_a.colors == "黑色,灰色"
    assert product_a.data_source == "2026 报价表"
    assert product_a.completeness_status == "complete"

    images_a = (
        (
            await db.execute(
                select(ProductImage)
                .where(ProductImage.product_id == product_a.id)
                .order_by(ProductImage.sort)
            )
        )
        .scalars()
        .all()
    )
    # 主图列那张是封面（sort=0），产品图列那张排在后面。
    assert [(img.sort, img.is_cover) for img in images_a] == [(0, True), (1, False)]

    product_b = (
        await db.execute(select(Product).where(Product.product_no == no_b))
    ).scalar_one()
    images_b = (
        (await db.execute(select(ProductImage).where(ProductImage.product_id == product_b.id)))
        .scalars()
        .all()
    )
    assert [(img.sort, img.is_cover) for img in images_b] == [(0, True)]
    # 两行的封面指向同一条 attachment —— sha256 相同的图全批只入库一次。
    assert images_a[0].attachment_id == images_b[0].attachment_id

    scene_rows = (
        await db.execute(
            select(product_scene_image.c.product_id, product_scene_image.c.scene_image_id)
        )
    ).all()
    assert {row.product_id for row in scene_rows} == {product_a.id, product_b.id}
    assert len({row.scene_image_id for row in scene_rows}) == 1


@pytest.mark.anyio
async def test_missing_brand_fails_only_that_row(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """一行主数据不存在只废这一行 —— 其余行照常入库（每行一个 SAVEPOINT）。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    ok_no, bad_no = f"IMP-{uuid4().hex[:6].upper()}", f"IMP-{uuid4().hex[:6].upper()}"
    common = {"供应商": master["供应商"], "分类": master["分类"], "面价*": "1200"}
    xlsx = _sheet_bytes(
        [
            {
                "产品编号*": ok_no,
                "产品名称*": "好行",
                "品牌": master["品牌"],
                "主图": "cover.png",
                **common,
            },
            # 品牌名系统里没有：导入不会替用户新建（brand_id 是 NOT NULL 外键）。
            {
                "产品编号*": bad_no,
                "产品名称*": "坏行",
                "品牌": "没建过的品牌",
                "主图": "extra.png",
                **common,
            },
        ]
    )
    payload = _zip_bytes(xlsx, {"cover.png": _COVER, "extra.png": _EXTRA})

    data = await _post_import(client, headers, payload)
    assert data["total"] == 2
    assert data["success_count"] == 1
    assert data["fail_count"] == 1
    failure = data["failures"][0]
    assert failure["product_no"] == bad_no
    assert "系统里没有" in failure["reason"]
    # 判不过的行在取图之前就被摘掉了：它引用的 extra.png 一个字节都不该上传。
    assert data["uploaded_count"] == 1
    assert [put["object_name"].endswith(".png") for put in minio.puts] == [True]
    assert await _count(db, Product) == 1
    assert await _count(db, ProductImage) == 1
    assert await _count(db, Attachment) == 1


@pytest.mark.anyio
async def test_image_url_only_warns_when_fetching_is_off(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio, monkeypatch
):
    """外链抓取默认关：直链只留提示、不发请求（SSRF 面不该由一张上传的表打开）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "PRODUCT_IMPORT_ALLOW_URL_FETCH", False)
    headers = await _login_admin(client)
    master = await _seed_master(db)
    no = f"IMP-{uuid4().hex[:6].upper()}"
    xlsx = _sheet_bytes(
        [
            {
                "产品编号*": no,
                "产品名称*": "外链行",
                "面价*": "待核价",
                "品牌": master["品牌"],
                "供应商": master["供应商"],
                "分类": master["分类"],
                "主图": "https://example.invalid/a.png",
            }
        ]
    )

    # 裸 xlsx（不打包）也是合法上传形态：load_bundle 靠 xl/workbook.xml 认出来。
    data = await _post_import(client, headers, xlsx, name="products.xlsx")
    assert data["success_count"] == 1
    assert data["image_count"] == 0
    assert data["image_sources"] == []
    assert any("外链抓取" in warning for warning in data["image_warnings"])
    # 真没发请求：一个字节都没进对象存储。
    assert minio.puts == []
    assert await _count(db, ProductImage) == 0

    product = (
        await db.execute(select(Product).where(Product.product_no == no))
    ).scalar_one()
    # 面价写「待核价」→ 占位价 99999 + 待补充（和导出侧对称）。
    assert product.face_price == 99999.0
    assert product.completeness_status == "pending"


@pytest.mark.anyio
async def test_skip_if_exists_reports_the_row_as_skipped(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """重复导同一份表：勾了跳过是「已跳过」，没勾是「产品编号已存在」，都只进失败明细。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    no = f"IMP-{uuid4().hex[:6].upper()}"
    xlsx = _sheet_bytes(
        [
            {
                "产品编号*": no,
                "产品名称*": "重复行",
                "面价*": "760",
                "品牌": master["品牌"],
                "供应商": master["供应商"],
                "分类": master["分类"],
            }
        ]
    )

    first = await _post_import(client, headers, xlsx, name="products.xlsx")
    assert first["success_count"] == 1
    assert first["fail_count"] == 0, first["failures"]

    second = await _post_import(
        client, headers, xlsx, name="products.xlsx", skip_if_exists=True
    )
    assert second["success_count"] == 0
    assert second["fail_count"] == 1
    assert second["failures"][0]["reason"] == "编号已存在，已跳过"

    third = await _post_import(client, headers, xlsx, name="products.xlsx")
    assert third["failures"][0]["reason"] == "产品编号已存在"

    # 三次下来库里始终只有一条产品。
    assert await _count(db, Product) == 1
