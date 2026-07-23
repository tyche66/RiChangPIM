from uuid import uuid4

import pytest

from app.models.product import (
    Attachment,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductManual,
    SceneImage,
    Supplier,
    product_scene_image,
)

pytestmark = pytest.mark.anyio


async def _auth_headers(client):
    response = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _create_product(session):
    suffix = uuid4().hex[:8]
    brand = Brand(brand_name=f"detail-brand-{suffix}")
    supplier = Supplier(supplier_name=f"detail-supplier-{suffix}")
    category = Category(category_name=f"detail-category-{suffix}", level=1)
    session.add_all([brand, supplier, category])
    await session.flush()
    product = Product(
        product_no=f"DETAIL-{suffix.upper()}",
        product_name="Detail test product",
        brand_id=brand.id,
        supplier_id=supplier.id,
        category_id=category.id,
        face_price=100,
    )
    session.add(product)
    await session.flush()
    return product


async def _create_attachment(session, file_type="image", name="detail.jpg"):
    attachment = Attachment(
        file_name=name,
        file_url=f"/files/{name}",
        file_type=file_type,
        file_size=100,
        storage_type="minio",
        oss_key=f"test/{uuid4().hex}/{name}",
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def _get_detail(client, product_id, headers):
    return await client.get(f"/api/v1/products/{product_id}", headers=headers)


async def test_get_product_detail_without_images(client, _sessionmaker):
    headers = await _auth_headers(client)
    async with _sessionmaker() as session:
        product = await _create_product(session)
        await session.commit()
        product_id = product.id

    response = await _get_detail(client, product_id, headers)
    assert response.status_code == 200, response.text
    assert response.json()["images"] == []
    assert response.json()["scene_images"] == []


async def test_get_product_detail_with_product_images(client, _sessionmaker):
    headers = await _auth_headers(client)
    async with _sessionmaker() as session:
        product = await _create_product(session)
        attachment = await _create_attachment(session)
        session.add(
            ProductImage(
                product_id=product.id,
                attachment_id=attachment.id,
                sort=2,
                is_cover=True,
            )
        )
        await session.commit()
        product_id = product.id

    response = await _get_detail(client, product_id, headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["images"][0]["id"]
    assert data["images"][0]["attachment_id"]
    assert data["images"][0]["is_cover"] is True
    assert data["images"][0]["file_url"].startswith(
        f"/api/v1/files/{data['images'][0]['attachment_id']}/content?token="
    )
    assert data["cover_image_id"] == data["images"][0]["id"]
    assert data["cover_image_url"] == data["images"][0]["file_url"]


async def test_get_product_detail_with_scene_images(client, _sessionmaker):
    headers = await _auth_headers(client)
    async with _sessionmaker() as session:
        product = await _create_product(session)
        attachment = await _create_attachment(session, name="scene.jpg")
        scene = SceneImage(name="Detail scene", attachment_id=attachment.id, sort=0)
        session.add(scene)
        await session.flush()
        await session.execute(
            product_scene_image.insert().values(
                product_id=product.id, scene_image_id=scene.id, sort=3
            )
        )
        await session.commit()
        product_id = product.id

    response = await _get_detail(client, product_id, headers)
    assert response.status_code == 200, response.text
    scene_data = response.json()["scene_images"][0]
    assert scene_data["file_url"].startswith(
        f"/api/v1/files/{scene_data['attachment_id']}/content?token="
    )
    assert scene_data["sort"] == 3


async def test_get_product_detail_with_manual(client, _sessionmaker):
    headers = await _auth_headers(client)
    async with _sessionmaker() as session:
        product = await _create_product(session)
        attachment = await _create_attachment(session, file_type="pdf", name="manual.pdf")
        session.add(
            ProductManual(
                product_id=product.id,
                attachment_id=attachment.id,
                doc_type="manual",
            )
        )
        await session.commit()
        product_id = product.id

    response = await _get_detail(client, product_id, headers)
    assert response.status_code == 200, response.text


async def test_get_product_detail_not_found(client):
    response = await _get_detail(client, uuid4(), await _auth_headers(client))
    assert response.status_code == 404
    assert response.json()["detail"]["msg"] == "产品不存在"


async def test_get_product_detail_invalid_id(client):
    response = await _get_detail(client, "not-a-uuid", await _auth_headers(client))
    assert response.status_code == 422


async def test_get_product_detail_requires_authentication(client):
    response = await client.get(f"/api/v1/products/{uuid4()}")
    assert response.status_code in (401, 403)
