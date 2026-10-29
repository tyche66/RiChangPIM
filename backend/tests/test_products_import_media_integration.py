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
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import (
    Attachment,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductTag,
    SceneImage,
    Supplier,
    Tag,
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


# ---------------------------------------------------------------------------
# 重传产品包：preflight -> commit（覆盖 / 追加 / 跳过）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_staging(tmp_path, monkeypatch):
    """预检暂存落到每个用例自己的临时目录，用例之间不共享 token。"""
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "PRODUCT_IMPORT_STAGING_DIR", str(tmp_path / "import_staging")
    )


async def _post_preflight(
    client: AsyncClient, headers: dict, payload: bytes, *, name: str = "products.xlsx"
) -> dict:
    resp = await client.post(
        "/api/v1/products/import/preflight",
        files={"file": (name, payload, "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    return body["data"]


async def _post_commit(
    client: AsyncClient,
    headers: dict,
    token: str,
    mode: str,
    *,
    backup: bool = True,
    new_tag_type: str = "series",
    alias_action: str | None = None,
    alias_decisions: list[dict] | None = None,
):
    payload: dict = {
        "token": token,
        "mode": mode,
        "backup": backup,
        "new_tag_type": new_tag_type,
    }
    if alias_action is not None:
        payload["alias_action"] = alias_action
    if alias_decisions is not None:
        payload["alias_decisions"] = alias_decisions
    return await client.post(
        "/api/v1/products/import/commit", json=payload, headers=headers
    )


@pytest.mark.anyio
async def test_preflight_counts_then_skip_mode_changes_nothing(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """预检只读不写；skip 模式只导入新增，已存在的产品一个字段都不动。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    existing_no = f"IMP-{uuid4().hex[:6].upper()}"
    new_no = f"IMP-{uuid4().hex[:6].upper()}"

    def _row(no: str, name: str, price: str) -> dict:
        return {
            "产品编号*": no,
            "产品名称*": name,
            "面价*": price,
            "品牌": master["品牌"],
            "供应商": master["供应商"],
            "分类": master["分类"],
            "状态": "上架",
        }

    first = await _post_import(
        client, headers, _sheet_bytes([_row(existing_no, "老产品", "760")]), name="a.xlsx"
    )
    assert first["created_count"] == 1

    before = (
        await db.execute(select(Product).where(Product.product_no == existing_no))
    ).scalar_one()
    before_id, before_price, before_status = before.id, before.face_price, before.status

    sheet = _sheet_bytes(
        [
            _row(existing_no, "改个名字", "999"),
            _row(new_no, "新产品", "1200"),
        ]
    )
    preflight = await _post_preflight(client, headers, sheet)
    assert preflight["total_rows"] == 2
    assert preflight["new_count"] == 1
    assert preflight["existing_count"] == 1
    assert preflight["invalid_count"] == 0
    assert preflight["conflicts"][0]["product_no"] == existing_no
    assert preflight["conflicts"][0]["existing_name"] == "老产品"

    # 预检不许写库
    still_old = (
        await db.execute(select(Product.product_name).where(Product.id == before_id))
    ).scalar_one()
    assert still_old == "老产品"

    resp = await _post_commit(client, headers, preflight["token"], "skip")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["skipped_count"] == 1
    assert data["created_count"] == 1
    assert data["updated_count"] == 0

    db.expire_all()
    after = (
        await db.execute(select(Product).where(Product.product_no == existing_no))
    ).scalar_one()
    assert (after.id, after.face_price, after.status, after.product_name) == (
        before_id,
        before_price,
        before_status,
        "老产品",
    )

    # token 单次消费：再提交同一个 token 必须失败而不是把包再写一遍
    replay = await _post_commit(client, headers, preflight["token"], "skip")
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == 40901


@pytest.mark.anyio
async def test_overwrite_keeps_id_and_only_touches_provided_cells(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """覆盖：id 不变、没填的单元格保留原值、面价按表更新。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    no = f"IMP-{uuid4().hex[:6].upper()}"

    first_sheet = _sheet_bytes(
        [
            {
                "产品编号*": no,
                "产品名称*": "原名",
                "面价*": "760",
                "品牌": master["品牌"],
                "供应商": master["供应商"],
                "分类": master["分类"],
                "材质": "原材质",
                "状态": "上架",
            }
        ]
    )
    await _post_import(client, headers, first_sheet, name="first.xlsx")
    before = (
        await db.execute(select(Product).where(Product.product_no == no))
    ).scalar_one()
    product_id = before.id
    assert before.material == "原材质"
    assert before.status == "active"

    # 第二份表只改面价与名称：「材质 / 状态」整列不出现
    second_sheet = _sheet_bytes(
        [
            {
                "产品编号*": no,
                "产品名称*": "新名字",
                "面价*": "880",
                "品牌": master["品牌"],
                "供应商": master["供应商"],
                "分类": master["分类"],
            }
        ]
    )
    preflight = await _post_preflight(client, headers, second_sheet)
    assert preflight["existing_count"] == 1

    resp = await _post_commit(
        client, headers, preflight["token"], "overwrite", backup=True
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["updated_count"] == 1
    assert data["backup_id"], "覆盖模式应留下可回滚的快照"

    db.expire_all()
    after = (
        await db.execute(select(Product).where(Product.id == product_id))
    ).scalar_one()
    assert after.id == product_id
    assert after.product_name == "新名字"
    assert after.face_price == 880
    # 空白 = 不改
    assert after.material == "原材质"
    assert after.status == "active"


@pytest.mark.anyio
async def test_append_only_fills_blank_fields(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """追加：只补空字段；已有面价不动。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    no = f"IMP-{uuid4().hex[:6].upper()}"

    base = {
        "产品编号*": no,
        "产品名称*": "追加测试",
        "面价*": "760",
        "品牌": master["品牌"],
        "供应商": master["供应商"],
        "分类": master["分类"],
    }
    await _post_import(client, headers, _sheet_bytes([base]), name="base.xlsx")
    before = (
        await db.execute(select(Product).where(Product.product_no == no))
    ).scalar_one()
    product_id = before.id
    assert before.material is None

    sheet = _sheet_bytes([{**base, "面价*": "999", "材质": "新材质"}])
    preflight = await _post_preflight(client, headers, sheet)
    resp = await _post_commit(client, headers, preflight["token"], "append")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["appended_count"] == 1

    db.expire_all()
    after = (
        await db.execute(select(Product).where(Product.id == product_id))
    ).scalar_one()
    assert after.material == "新材质"
    # 面价已有值 → 追加模式不动
    assert after.face_price == 760


@pytest.mark.anyio
async def test_preflight_reports_invalid_rows_without_touching_them(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    headers = await _login_admin(client)
    master = await _seed_master(db)
    sheet = _sheet_bytes(
        [
            {
                "产品编号*": f"IMP-{uuid4().hex[:6].upper()}",
                "产品名称*": "缺品牌",
                "面价*": "100",
                "品牌": "系统里没有的品牌",
                "供应商": master["供应商"],
                "分类": master["分类"],
            }
        ]
    )
    preflight = await _post_preflight(client, headers, sheet)
    assert preflight["invalid_count"] == 1
    assert preflight["new_count"] == 0
    assert "系统里没有" in preflight["invalid"][0]["reason"]


@pytest.mark.anyio
async def test_import_creates_unknown_tags_and_binds_them(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """新系列（如摩耳）以前会被「已忽略」，现在必须建标签并绑到产品上。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    series_name = f"摩耳{uuid4().hex[:4]}"
    no = f"IMP-{uuid4().hex[:6].upper()}"

    sheet = _sheet_bytes(
        [
            {
                "产品编号*": no,
                "产品名称*": "新系列椅子",
                "面价*": "900",
                "品牌": master["品牌"],
                "供应商": master["供应商"],
                "分类": master["分类"],
                "标签": f"系列:{series_name},热销",
            }
        ]
    )

    preflight = await _post_preflight(client, headers, sheet)
    assert preflight["new_tag_count"] == 2
    typed = {tag["name"]: tag["tag_type"] for tag in preflight["new_tags"]}
    assert typed[series_name] == "series"
    assert typed["热销"] == "series"  # 预检按默认类型展示，最终以提交参数为准

    resp = await _post_commit(client, headers, preflight["token"], "overwrite")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created_tags"] == 2, data
    assert series_name in data["new_tag_names"]

    tag = (
        await db.execute(
            select(Tag).where(Tag.tag_name == series_name, Tag.is_deleted.is_(False))
        )
    ).scalar_one()
    assert tag.tag_type == "series"

    product = (
        await db.execute(select(Product).where(Product.product_no == no))
    ).scalar_one()
    links = (
        await db.execute(
            select(ProductTag.tag_id).where(
                ProductTag.product_id == product.id, ProductTag.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    assert tag.id in links

    # 第二次导入同一份表：标签已存在，不应重复创建
    again = await _post_preflight(client, headers, sheet)
    assert again["new_tag_count"] == 0


# ---------------------------------------------------------------------------
# 产品编号别名：103800022 ↔ P-103800022
# ---------------------------------------------------------------------------

_ALIAS_NO = "103800022"
_ALIAS_PREFIXED = f"P-{_ALIAS_NO}"


def _alias_row(
    product_no: str,
    name: str,
    master: dict[str, str],
    *,
    price: str = "760",
    image: str | None = "cover.png",
    tag: str | None = None,
) -> dict:
    row = {
        "产品编号*": product_no,
        "产品名称*": name,
        "面价*": price,
        "品牌": master["品牌"],
        "供应商": master["供应商"],
        "分类": master["分类"],
        "主图": image,
    }
    if tag:
        row["标签"] = tag
    return row


async def _create_base_product(
    client: AsyncClient,
    headers: dict,
    master: dict[str, str],
    *,
    product_no: str,
    name: str,
    price: str = "760",
) -> None:
    data = await _post_import(
        client,
        headers,
        _zip_bytes(
            _sheet_bytes([_alias_row(product_no, name, master, price=price)]),
            {"cover.png": _COVER},
        ),
        name="base.zip",
    )
    assert data["created_count"] == 1, data


async def _active_product(db: AsyncSession, product_id) -> Product:
    db.expire_all()
    return (
        await db.execute(
            select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
        )
    ).scalar_one()


async def _active_images(db: AsyncSession, product_id) -> list[ProductImage]:
    return list(
        (
            await db.execute(
                select(ProductImage)
                .where(
                    ProductImage.product_id == product_id,
                    ProductImage.is_deleted.is_(False),
                )
                .order_by(ProductImage.sort)
            )
        ).scalars()
    )


@pytest.mark.anyio
async def test_alias_preflight_requires_choice_then_overwrites_original_id(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """已有 103800022，再导入 P-103800022：未选处理方式不写库，选了按别名覆盖后 ID 不变。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    name = f"别名椅{uuid4().hex[:4]}"
    await _create_base_product(client, headers, master, product_no=_ALIAS_NO, name=name)
    base = (
        await db.execute(select(Product).where(Product.product_no == _ALIAS_NO))
    ).scalar_one()
    base_id = base.id
    old_images = await _active_images(db, base_id)
    old_attachment_id = old_images[0].attachment_id

    tag_name = f"别名系列{uuid4().hex[:4]}"
    sheet = _sheet_bytes(
        [
            _alias_row(
                _ALIAS_PREFIXED,
                name,
                master,
                price="999",
                image="new.png",
                tag=f"系列:{tag_name}",
            )
        ]
    )
    payload = _zip_bytes(sheet, {"new.png": _EXTRA})
    preflight = await _post_preflight(client, headers, payload, name="alias.zip")

    assert preflight["new_count"] == 0
    assert preflight["existing_count"] == 0
    assert preflight["exact_existing_count"] == 0
    assert preflight["alias_conflict_count"] == 1
    assert preflight["alias_safe_count"] == 1
    assert preflight["alias_high_risk_count"] == 0
    conflict = preflight["alias_conflicts"][0]
    assert conflict["risk"] == "safe"
    assert conflict["alias_product_id"] == str(base_id)
    assert conflict["alias_product_no"] == _ALIAS_NO

    # 未明确选择：409，且不新增、不覆盖（token 未被消费）
    resp = await _post_commit(client, headers, preflight["token"], "overwrite")
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == 40903
    unchanged = await _active_product(db, base_id)
    assert (unchanged.product_no, unchanged.face_price, unchanged.product_name) == (
        _ALIAS_NO,
        760,
        name,
    )
    assert await _count(db, Product) == 1

    # 明确选择按别名覆盖：写回原产品 ID，编号仍是库里存储的原值
    resp = await _post_commit(
        client, headers, preflight["token"], "overwrite", alias_action="overwrite_alias"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["success_count"] == 1
    assert data["fail_count"] == 0, data["failures"]
    assert data["alias_updated_count"] == 1
    assert data["updated_count"] == 1
    assert data["created_count"] == 0

    after = await _active_product(db, base_id)
    assert after.id == base_id
    assert after.product_no == _ALIAS_NO
    assert after.face_price == 999
    assert await _count(db, Product) == 1

    images = await _active_images(db, base_id)
    assert [img.is_cover for img in images] == [True]
    assert images[0].attachment_id != old_attachment_id

    tag = (
        await db.execute(
            select(Tag).where(Tag.tag_name == tag_name, Tag.is_deleted.is_(False))
        )
    ).scalar_one()
    links = (
        await db.execute(
            select(ProductTag.tag_id).where(
                ProductTag.product_id == base_id, ProductTag.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    assert tag.id in links


@pytest.mark.anyio
async def test_alias_reverse_order_keeps_prefixed_stored_number(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """已有 P-103800022，再导入 103800022：同样按别名覆盖，存储编号保持 P- 前缀。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    name = f"反向别名椅{uuid4().hex[:4]}"
    await _create_base_product(
        client, headers, master, product_no=_ALIAS_PREFIXED, name=name
    )
    base = (
        await db.execute(select(Product).where(Product.product_no == _ALIAS_PREFIXED))
    ).scalar_one()
    base_id = base.id

    sheet = _sheet_bytes([_alias_row(_ALIAS_NO, name, master, price="888")])
    payload = _zip_bytes(sheet, {"cover.png": _EXTRA})
    preflight = await _post_preflight(client, headers, payload, name="reverse.zip")
    assert preflight["alias_conflict_count"] == 1
    assert preflight["alias_safe_count"] == 1
    assert preflight["alias_conflicts"][0]["alias_product_no"] == _ALIAS_PREFIXED

    resp = await _post_commit(
        client, headers, preflight["token"], "overwrite", alias_action="overwrite_alias"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["alias_updated_count"] == 1

    after = await _active_product(db, base_id)
    assert after.id == base_id
    assert after.product_no == _ALIAS_PREFIXED
    assert after.face_price == 888
    assert await _count(db, Product) == 1


@pytest.mark.anyio
async def test_alias_name_mismatch_is_high_risk_and_never_auto_overwrites(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """名称不同 → 高风险：全局「按别名覆盖」被拒绝；只能明确作为新产品创建。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    await _create_base_product(client, headers, master, product_no=_ALIAS_NO, name="椅子甲")
    base = (
        await db.execute(select(Product).where(Product.product_no == _ALIAS_NO))
    ).scalar_one()
    base_id = base.id

    sheet = _sheet_bytes(
        [_alias_row(_ALIAS_PREFIXED, "椅子乙", master, price="1200", image=None)]
    )
    preflight = await _post_preflight(client, headers, sheet)
    assert preflight["alias_conflict_count"] == 1
    assert preflight["alias_safe_count"] == 0
    assert preflight["alias_high_risk_count"] == 1
    conflict = preflight["alias_conflicts"][0]
    assert conflict["risk"] == "high"
    assert "名称不一致" in conflict["reason"]
    assert conflict["alias_product_id"] == str(base_id)

    # 未选择：409
    resp = await _post_commit(client, headers, preflight["token"], "overwrite")
    assert resp.status_code == 409

    # 全局「按别名覆盖」也不允许吞掉高风险行：409，仍不写库
    resp = await _post_commit(
        client, headers, preflight["token"], "overwrite", alias_action="overwrite_alias"
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == 40903
    unchanged = await _active_product(db, base_id)
    assert (unchanged.product_name, unchanged.face_price) == ("椅子甲", 760)
    assert await _count(db, Product) == 1

    # 明确选择作为新产品创建：原产品一字不动，新增第二条
    resp = await _post_commit(
        client, headers, preflight["token"], "overwrite", alias_action="create_new"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created_count"] == 1
    assert data["alias_created_count"] == 1
    assert data["updated_count"] == 0
    assert await _count(db, Product) == 2
    untouched = await _active_product(db, base_id)
    assert untouched.product_name == "椅子甲"
    assert untouched.face_price == 760
    created = (
        await db.execute(select(Product).where(Product.product_no == _ALIAS_PREFIXED))
    ).scalar_one()
    assert created.product_name == "椅子乙"


@pytest.mark.anyio
async def test_alias_multiple_candidates_is_high_risk(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """103800022 与 P-103800022 同时存在时，第三行 p-103800022 候选不唯一 → 高风险。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    name = f"多候选椅{uuid4().hex[:4]}"
    await _create_base_product(client, headers, master, product_no=_ALIAS_NO, name=name)
    brand_id = (
        await db.execute(select(Brand.id).where(Brand.brand_name == master["品牌"]))
    ).scalar_one()
    supplier_id = (
        await db.execute(
            select(Supplier.id).where(Supplier.supplier_name == master["供应商"])
        )
    ).scalar_one()
    category_id = (
        await db.execute(
            select(Category.id).where(Category.category_name == master["分类"])
        )
    ).scalar_one()
    db.add(
        Product(
            product_no=_ALIAS_PREFIXED,
            product_name=name,
            brand_id=brand_id,
            supplier_id=supplier_id,
            category_id=category_id,
            face_price=760,
            status="active",
            completeness_status="complete",
        )
    )
    await db.commit()
    assert await _count(db, Product) == 2

    # 小写 p- 不与库里的 P- 精确相同，因此走别名匹配，且能看见两条候选
    sheet = _sheet_bytes(
        [_alias_row(f"p-{_ALIAS_NO}", name, master, price="1000", image=None)]
    )
    preflight = await _post_preflight(client, headers, sheet)
    assert preflight["exact_existing_count"] == 0
    assert preflight["alias_conflict_count"] == 1
    assert preflight["alias_safe_count"] == 0
    assert preflight["alias_high_risk_count"] == 1
    conflict = preflight["alias_conflicts"][0]
    assert conflict["risk"] == "high"
    assert "不唯一" in conflict["reason"]
    assert conflict["alias_product_id"] is None

    resp = await _post_commit(
        client, headers, preflight["token"], "overwrite", alias_action="overwrite_alias"
    )
    assert resp.status_code == 409, resp.text
    assert await _count(db, Product) == 2


@pytest.mark.anyio
async def test_alias_deleted_candidate_is_high_risk(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """别名对应的产品已删除 → 高风险，不能被当成覆盖目标。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    name = f"已删除椅{uuid4().hex[:4]}"
    await _create_base_product(client, headers, master, product_no=_ALIAS_NO, name=name)
    base = (
        await db.execute(select(Product).where(Product.product_no == _ALIAS_NO))
    ).scalar_one()
    base_id = base.id
    await db.execute(
        sa_update(Product)
        .where(Product.id == base_id)
        .values(is_deleted=True, deleted_at=func.now())
    )
    await db.commit()

    sheet = _sheet_bytes(
        [_alias_row(_ALIAS_PREFIXED, name, master, price="1001", image=None)]
    )
    preflight = await _post_preflight(client, headers, sheet)
    assert preflight["exact_existing_count"] == 0
    assert preflight["alias_conflict_count"] == 1
    assert preflight["alias_high_risk_count"] == 1
    conflict = preflight["alias_conflicts"][0]
    assert conflict["risk"] == "high"
    assert "已删除" in conflict["reason"]

    resp = await _post_commit(
        client, headers, preflight["token"], "overwrite", alias_action="overwrite_alias"
    )
    assert resp.status_code == 409, resp.text
    db.expire_all()
    still_deleted = (
        await db.execute(select(Product).where(Product.id == base_id))
    ).scalar_one()
    assert still_deleted.is_deleted is True
    assert still_deleted.face_price == 760


@pytest.mark.anyio
async def test_alias_conflict_skip_mode_is_explicit_and_keeps_everything(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """skip 的既有语义不变：别名行也视为「已存在」，不需要额外选择且零写入。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    name = f"跳过椅{uuid4().hex[:4]}"
    await _create_base_product(client, headers, master, product_no=_ALIAS_NO, name=name)
    base = (
        await db.execute(select(Product).where(Product.product_no == _ALIAS_NO))
    ).scalar_one()
    base_id = base.id

    sheet = _sheet_bytes(
        [_alias_row(_ALIAS_PREFIXED, name, master, price="1234", image=None)]
    )
    preflight = await _post_preflight(client, headers, sheet)
    assert preflight["alias_conflict_count"] == 1

    resp = await _post_commit(client, headers, preflight["token"], "skip")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["skipped_count"] == 1
    assert data["created_count"] == 0
    assert data["updated_count"] == 0

    after = await _active_product(db, base_id)
    assert after.face_price == 760
    assert await _count(db, Product) == 1


@pytest.mark.anyio
async def test_alias_explicit_per_row_decision_can_handle_high_risk(
    client: AsyncClient, db: AsyncSession, minio: FakeMinio
):
    """高风险行只有逐行明确选择才允许按别名覆盖；产品 ID 同样保持不变。"""
    headers = await _login_admin(client)
    master = await _seed_master(db)
    await _create_base_product(client, headers, master, product_no=_ALIAS_NO, name="逐行甲")
    base = (
        await db.execute(select(Product).where(Product.product_no == _ALIAS_NO))
    ).scalar_one()
    base_id = base.id

    sheet = _sheet_bytes(
        [_alias_row(_ALIAS_PREFIXED, "逐行乙", master, price="555", image=None)]
    )
    preflight = await _post_preflight(client, headers, sheet)
    row = preflight["alias_conflicts"][0]["row"]

    resp = await _post_commit(
        client,
        headers,
        preflight["token"],
        "overwrite",
        alias_decisions=[{"row": row, "action": "overwrite_alias"}],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["alias_updated_count"] == 1
    assert data["fail_count"] == 0, data["failures"]

    after = await _active_product(db, base_id)
    assert after.id == base_id
    assert after.product_no == _ALIAS_NO
    assert after.product_name == "逐行乙"
    assert after.face_price == 555
    assert await _count(db, Product) == 1
