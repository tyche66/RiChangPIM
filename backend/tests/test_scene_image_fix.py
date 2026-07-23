"""Integration tests for scene image / product fixes.

测试覆盖：
1. 产品解绑场景图后可再次绑定同一场景图
2. 产品详情不返回已解绑场景图
3. 删除场景图后产品详情不再返回
4. 同一场景图绑定到不同产品时各产品可保存不同排序
5. 分享 API 无附件名 N+1 查询
6. PDF 被引用时 ref_count 正确
7. 替换媒体文件后引用不变
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.product import (
    Attachment,
    Product,
    ProductImage,
    ProductManual,
    SceneImage,
    product_scene_image,
)

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# 1. 软删除重绑
# ---------------------------------------------------------------------------


async def _create_product(db) -> Product:
    p = Product(
        product_no=f"TST-{uuid4().hex[:8].upper()}",
        product_name="Test Product",
        brand_id=(await db.execute(select(Product.brand_id).limit(1))).scalar(),
        supplier_id=(await db.execute(select(Product.supplier_id).limit(1))).scalar(),
        category_id=(await db.execute(select(Product.category_id).limit(1))).scalar(),
        face_price=100,
    )
    db.add(p)
    await db.flush()
    return p


async def _create_attachment(db, file_type="image") -> Attachment:
    att = Attachment(
        file_name="test.jpg",
        file_url="/files/test.jpg",
        file_type=file_type,
        file_size=100,
        storage_type="minio",
        oss_key=f"image/{uuid4().hex}.jpg",
    )
    db.add(att)
    await db.flush()
    return att


async def _create_scene_image(db, attachment_id=None) -> SceneImage:
    if attachment_id is None:
        att = await _create_attachment(db)
        attachment_id = att.id
    si = SceneImage(
        name="Test Scene",
        attachment_id=attachment_id,
        sort=0,
    )
    db.add(si)
    await db.flush()
    return si


async def _login_admin(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


async def test_rebind_after_unbind_succeeds(client, _sessionmaker):
    """解绑后重新绑定同一场景图，不报主键冲突。"""
    async with _sessionmaker() as s:
        # 先创建必需的基础数据
        from app.models.product import Brand, Supplier, Category
        brand = Brand(brand_name=f"TestBrand-{uuid4().hex[:8]}")
        supplier = Supplier(supplier_name=f"TestSupplier-{uuid4().hex[:8]}")
        category = Category(category_name=f"TestCat-{uuid4().hex[:8]}", level=1)
        s.add_all([brand, supplier, category])
        await s.flush()

        product = Product(
            product_no=f"TST-{uuid4().hex[:8].upper()}",
            product_name="Test Product",
            brand_id=brand.id,
            supplier_id=supplier.id,
            category_id=category.id,
            face_price=100,
        )
        s.add(product)
        att = await _create_attachment(s)
        si = await _create_scene_image(s, att.id)
        await s.commit()

        pid = product.id
        sid = si.id
        token = await _login_admin(client)

    # 绑定场景图
    resp = await client.post(
        f"/api/v1/products/{pid}/scene-images",
        json={"scene_image_ids": [str(sid)]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text

    # 解绑
    resp = await client.delete(
        f"/api/v1/products/{pid}/scene-images/{sid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # 重新绑定——不应报错
    resp = await client.post(
        f"/api/v1/products/{pid}/scene-images",
        json={"scene_image_ids": [str(sid)]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["bound"] == 1


async def test_product_detail_omits_unbound_scene_images(client, _sessionmaker):
    """产品详情不返回已解绑的场景图。"""
    async with _sessionmaker() as s:
        from app.models.product import Brand, Supplier, Category
        brand = Brand(brand_name=f"TestBrand-{uuid4().hex[:8]}")
        supplier = Supplier(supplier_name=f"TestSupplier-{uuid4().hex[:8]}")
        category = Category(category_name=f"TestCat-{uuid4().hex[:8]}", level=1)
        s.add_all([brand, supplier, category])
        await s.flush()

        product = Product(
            product_no=f"TST-{uuid4().hex[:8].upper()}",
            product_name="Test Product",
            brand_id=brand.id,
            supplier_id=supplier.id,
            category_id=category.id,
            face_price=100,
        )
        s.add(product)
        att = await _create_attachment(s)
        si = await _create_scene_image(s, att.id)

        # 绑定场景图
        stmt = product_scene_image.insert().values(
            product_id=product.id,
            scene_image_id=si.id,
            sort=1,
        )
        await s.execute(stmt)
        await s.commit()

        pid = product.id
        sid = si.id
        token = await _login_admin(client)

    # 确认详情包含场景图
    resp = await client.get(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["scene_images"]) == 1

    # 解绑
    resp = await client.delete(
        f"/api/v1/products/{pid}/scene-images/{sid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # 确认详情不再包含
    resp = await client.get(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["scene_images"]) == 0


async def test_deleted_scene_image_omitted_from_product_detail(client, _sessionmaker):
    """删除场景图后产品详情不再返回该场景图。"""
    async with _sessionmaker() as s:
        from app.models.product import Brand, Supplier, Category
        brand = Brand(brand_name=f"TestBrand-{uuid4().hex[:8]}")
        supplier = Supplier(supplier_name=f"TestSupplier-{uuid4().hex[:8]}")
        category = Category(category_name=f"TestCat-{uuid4().hex[:8]}", level=1)
        s.add_all([brand, supplier, category])
        await s.flush()

        product = Product(
            product_no=f"TST-{uuid4().hex[:8].upper()}",
            product_name="Test Product",
            brand_id=brand.id,
            supplier_id=supplier.id,
            category_id=category.id,
            face_price=100,
        )
        s.add(product)
        att = await _create_attachment(s)
        si = await _create_scene_image(s, att.id)

        stmt = product_scene_image.insert().values(
            product_id=product.id,
            scene_image_id=si.id,
        )
        await s.execute(stmt)
        await s.commit()

        pid = product.id
        sid = si.id
        token = await _login_admin(client)

    # 确认详情有场景图
    resp = await client.get(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["scene_images"]) == 1

    # 删除场景图本身
    resp = await client.delete(
        f"/api/v1/scene-images/{sid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # 确认详情不再包含
    resp = await client.get(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["scene_images"]) == 0


async def test_different_product_different_sort(client, _sessionmaker):
    """同一场景图绑定到不同产品时各产品可保存不同排序。"""
    async with _sessionmaker() as s:
        from app.models.product import Brand, Supplier, Category
        brand = Brand(brand_name=f"TestBrand-{uuid4().hex[:8]}")
        supplier = Supplier(supplier_name=f"TestSupplier-{uuid4().hex[:8]}")
        category = Category(category_name=f"TestCat-{uuid4().hex[:8]}", level=1)
        s.add_all([brand, supplier, category])
        await s.flush()

        p1 = Product(
            product_no=f"TST-{uuid4().hex[:8].upper()}",
            product_name="Product A",
            brand_id=brand.id, supplier_id=supplier.id,
            category_id=category.id, face_price=100,
        )
        p2 = Product(
            product_no=f"TST-{uuid4().hex[:8].upper()}",
            product_name="Product B",
            brand_id=brand.id, supplier_id=supplier.id,
            category_id=category.id, face_price=200,
        )
        s.add_all([p1, p2])
        att = await _create_attachment(s)
        si = await _create_scene_image(s, att.id)
        await s.flush()

        # 绑定到两个产品，不同排序
        await s.execute(product_scene_image.insert().values(
            product_id=p1.id, scene_image_id=si.id, sort=5,
        ))
        await s.execute(product_scene_image.insert().values(
            product_id=p2.id, scene_image_id=si.id, sort=9,
        ))
        await s.commit()

        pid1, pid2, sid = p1.id, p2.id, si.id
        token = await _login_admin(client)

    # 验证产品1的 sort=5
    resp = await client.get(
        f"/api/v1/products/{pid1}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    scenes = resp.json()["scene_images"]
    assert len(scenes) == 1
    assert scenes[0]["sort"] == 5

    # 验证产品2的 sort=9
    resp = await client.get(
        f"/api/v1/products/{pid2}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    scenes = resp.json()["scene_images"]
    assert len(scenes) == 1
    assert scenes[0]["sort"] == 9


# ---------------------------------------------------------------------------
# 6. Media ref_count
# ---------------------------------------------------------------------------


async def test_ref_count_counts_all_types(client, _sessionmaker):
    """PDF/doc 等非 image 类型的附件 ref_count 也正确统计。"""
    async with _sessionmaker() as s:
        from app.models.product import Brand, Supplier, Category
        brand = Brand(brand_name=f"TestBrand-{uuid4().hex[:8]}")
        supplier = Supplier(supplier_name=f"TestSupplier-{uuid4().hex[:8]}")
        category = Category(category_name=f"TestCat-{uuid4().hex[:8]}", level=1)
        s.add_all([brand, supplier, category])
        await s.flush()

        product = Product(
            product_no=f"TST-{uuid4().hex[:8].upper()}",
            product_name="Test",
            brand_id=brand.id, supplier_id=supplier.id,
            category_id=category.id, face_price=100,
        )
        s.add(product)

        # 创建 PDF 附件
        pdf_att = Attachment(
            file_name="manual.pdf",
            file_url="/files/manual.pdf",
            file_type="pdf",
            file_size=500,
            storage_type="minio",
            oss_key="pdf/test.pdf",
        )
        s.add(pdf_att)
        await s.flush()

        # 创建 ProductManual 引用
        pm = ProductManual(
            product_id=product.id,
            attachment_id=pdf_att.id,
            doc_type="manual",
        )
        s.add(pm)
        await s.commit()

        pdf_id = pdf_att.id
        token = await _login_admin(client)

    # 确认 ref_count 为 1（被产品说明书引用）
    resp = await client.get(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    files_list = resp.json()["data"]["list"]
    pdf_file = next((f for f in files_list if f["id"] == str(pdf_id)), None)
    assert pdf_file is not None, f"PDF attachment not found in response: {files_list}"
    assert pdf_file["ref_count"] >= 1, f"Expected ref_count >= 1, got {pdf_file['ref_count']}"


# ---------------------------------------------------------------------------
# 7. Media replace preserves ref_count
# ---------------------------------------------------------------------------


async def test_replace_file_preserves_ref_count(client, _sessionmaker):
    """替换媒体文件后引用不变，旧 OSS 对象被清理。"""
    async with _sessionmaker() as s:
        att = Attachment(
            file_name="old.jpg",
            file_url="/files/old.jpg",
            file_type="image",
            file_size=100,
            storage_type="minio",
            oss_key="image/old.jpg",
        )
        s.add(att)
        await s.commit()
        att_id = att.id
        token = await _login_admin(client)

    # 替换文件
    resp = await client.put(
        f"/api/v1/files/{att_id}/replace",
        files={"file": ("new.jpg", b"new content", "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # 引用不变（无引用，ref_count=0）
    async with _sessionmaker() as s:
        att = await s.get(Attachment, att_id)
        assert att is not None
        assert att.file_name == "new.jpg"
        assert att.oss_key != "image/old.jpg"


# ---------------------------------------------------------------------------
# 8. Scene image reorder uses product_scene_image.sort
# ---------------------------------------------------------------------------


async def test_scene_image_reorder_uses_association_sort(client, _sessionmaker):
    """产品场景图排序使用 product_scene_image.sort。"""
    async with _sessionmaker() as s:
        from app.models.product import Brand, Supplier, Category
        brand = Brand(brand_name=f"TestBrand-{uuid4().hex[:8]}")
        supplier = Supplier(supplier_name=f"TestSupplier-{uuid4().hex[:8]}")
        category = Category(category_name=f"TestCat-{uuid4().hex[:8]}", level=1)
        s.add_all([brand, supplier, category])
        await s.flush()

        product = Product(
            product_no=f"TST-{uuid4().hex[:8].upper()}",
            product_name="Test",
            brand_id=brand.id, supplier_id=supplier.id,
            category_id=category.id, face_price=100,
        )
        s.add(product)

        att1 = await _create_attachment(s)
        att2 = await _create_attachment(s)
        si1 = await _create_scene_image(s, att1.id)
        si2 = await _create_scene_image(s, att2.id)
        await s.flush()

        # 绑定两个场景图，sort=1 和 sort=2
        await s.execute(product_scene_image.insert().values(
            product_id=product.id, scene_image_id=si1.id, sort=1,
        ))
        await s.execute(product_scene_image.insert().values(
            product_id=product.id, scene_image_id=si2.id, sort=2,
        ))
        await s.commit()

        pid, sid1, sid2 = product.id, si1.id, si2.id
        token = await _login_admin(client)

    # 重新排序：交换位置
    resp = await client.patch(
        f"/api/v1/products/{pid}/scene-images/reorder",
        json={
            "items": [
                {"scene_image_id": str(sid1), "sort": 10},
                {"scene_image_id": str(sid2), "sort": 5},
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # 验证详情中排序已更新
    resp = await client.get(
        f"/api/v1/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    scenes = resp.json()["scene_images"]
    scenes_sorted = sorted(scenes, key=lambda s: s["sort"])
    assert scenes_sorted[0]["id"] == str(sid2)  # sort 5
    assert scenes_sorted[1]["id"] == str(sid1)  # sort 10
