"""Integration tests for media library, product images, scene images, and share features.

Covers all acceptance criteria for permissions, security, and functionality.
"""

import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.audit import Share, ShareToken
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IMAGE_JPEG_CONTENT = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
_IMAGE_PNG_CONTENT = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
_PDF_CONTENT = b"%PDF-1.4\r\n%\xe2\xe3\xcf\xd3\r\n"


async def _auth_header(client: AsyncClient) -> dict:
    """Login as admin and get auth header."""
    resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_test_product(db: AsyncSession) -> Product:
    """Create a minimal product with brand/supplier/category."""
    brand = Brand(brand_name=f"brand_{uuid4().hex[:8]}", description="test")
    supplier = Supplier(supplier_name=f"supplier_{uuid4().hex[:8]}", contact="t", phone="123")
    category = Category(category_name=f"cat_{uuid4().hex[:8]}", level=1, sort=0)
    db.add_all([brand, supplier, category])
    await db.flush()

    product = Product(
        product_no=f"PN{uuid4().hex[:8].upper()}",
        product_name=f"Test Product {uuid4().hex[:8]}",
        brand_id=brand.id,
        supplier_id=supplier.id,
        category_id=category.id,
        face_price=99.99,
        status="draft",
    )
    db.add(product)
    await db.flush()
    return product


async def _upload_file(client: AsyncClient, headers: dict, content: bytes, filename: str, content_type: str) -> dict:
    """Upload a file and return the response data."""
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": (filename, content, content_type)},
        headers=headers,
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    return resp.json()["data"]


async def _create_share_token(client: AsyncClient, headers: dict, target_id: str, expire_hours: int | None = None) -> dict:
    """Create a share and return its token info."""
    resp = await client.post(
        "/api/v1/shares",
        json={"target_id": target_id, "share_type": "proposal", "expire_hours": expire_hours},
        headers=headers,
    )
    assert resp.status_code == 200, f"Share create failed: {resp.text}"
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 1. Media: single file upload
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_upload_single_file(client: AsyncClient):
    headers = await _auth_header(client)
    data = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "test.jpg", "image/jpeg")

    assert data["file_name"] == "test.jpg"
    assert data["file_type"] == "image"
    assert data["file_size"] == len(_IMAGE_JPEG_CONTENT)
    assert UUID(data["attachment_id"])


# ---------------------------------------------------------------------------
# 2. Media: batch upload (multiple sequential uploads)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_upload_batch(client: AsyncClient):
    headers = await _auth_header(client)
    files = [
        (_IMAGE_JPEG_CONTENT, "a.jpg", "image/jpeg"),
        (_IMAGE_PNG_CONTENT, "b.png", "image/png"),
        (_PDF_CONTENT, "c.pdf", "application/pdf"),
    ]
    for content, name, ctype in files:
        data = await _upload_file(client, headers, content, name, ctype)
        assert data["file_name"] == name
        assert data["file_type"] == ("pdf" if ctype == "application/pdf" else "image")


# ---------------------------------------------------------------------------
# 3. Media: exceeds 50MB upload failure
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_upload_exceeds_50mb_fails(client: AsyncClient):
    headers = await _auth_header(client)
    oversized = b"x" * (51 * 1024 * 1024)
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("big.jpg", oversized, "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == 42203


# ---------------------------------------------------------------------------
# 4. Media: non-whitelist MIME upload failure
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_upload_invalid_mime_fails(client: AsyncClient):
    headers = await _auth_header(client)
    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("hack.exe", b"fake", "application/x-msdownload")},
        headers=headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == 42202


# ---------------------------------------------------------------------------
# 5. PNG upload keeps type image/png
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_upload_png_keeps_type(client: AsyncClient):
    headers = await _auth_header(client)
    data = await _upload_file(client, headers, _IMAGE_PNG_CONTENT, "transparent.png", "image/png")

    assert data["file_type"] == "image"


# ---------------------------------------------------------------------------
# 6. Media list search and type filter
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_list_search_and_filter(client: AsyncClient):
    headers = await _auth_header(client)
    await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "alpha.jpg", "image/jpeg")
    await _upload_file(client, headers, _IMAGE_PNG_CONTENT, "beta.png", "image/png")
    await _upload_file(client, headers, _PDF_CONTENT, "gamma.pdf", "application/pdf")

    resp = await client.get("/api/v1/files?file_type=image&keyword=beta", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    for item in data["list"]:
        assert item["file_type"] == "image"
        assert "beta" in item["file_name"].lower()

    resp = await client.get("/api/v1/files?file_type=pdf", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    for item in data["list"]:
        assert item["file_type"] == "pdf"


# ---------------------------------------------------------------------------
# 7. Unreferenced media can be deleted
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_delete_unreferenced_succeeds(client: AsyncClient):
    headers = await _auth_header(client)
    data = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "del.jpg", "image/jpeg")

    resp = await client.delete(f"/api/v1/files/{data['attachment_id']}", headers=headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. Referenced media deletion fails
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_delete_referenced_fails(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    data = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "ref.jpg", "image/jpeg")

    att_id = UUID(data["attachment_id"])
    product = await _create_test_product(db)

    pi = ProductImage(product_id=product.id, attachment_id=att_id, is_cover=True)
    db.add(pi)
    await db.commit()

    resp = await client.delete(f"/api/v1/files/{att_id}", headers=headers)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "产品图片" in detail["msg"]

    att = await db.get(Attachment, att_id)
    assert att.is_deleted is False


# ---------------------------------------------------------------------------
# 9. Media replace keeps references intact
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_replace_keeps_references(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    data = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "orig.jpg", "image/jpeg")
    att_id = UUID(data["attachment_id"])

    product = await _create_test_product(db)
    pi = ProductImage(product_id=product.id, attachment_id=att_id, is_cover=True)
    db.add(pi)
    await db.commit()

    new_content = _IMAGE_JPEG_CONTENT + b"extra"
    resp = await client.put(
        f"/api/v1/files/{att_id}/replace",
        files={"file": ("replaced.jpg", new_content, "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 200

    pi_check = await db.execute(
        select(ProductImage).where(
            ProductImage.attachment_id == att_id,
            ProductImage.is_deleted.is_(False),
        )
    )
    assert pi_check.scalar_one_or_none() is not None

    att = await db.get(Attachment, att_id)
    assert att.file_size == len(new_content)


# ---------------------------------------------------------------------------
# 10. Product add images success
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_product_add_images_success(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    img1 = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "p1.jpg", "image/jpeg")
    img2 = await _upload_file(client, headers, _IMAGE_PNG_CONTENT, "p2.png", "image/png")

    product = await _create_test_product(db)
    await db.commit()

    resp = await client.post(
        f"/api/v1/products/{product.id}/images",
        json={"attachment_ids": [img1["attachment_id"], img2["attachment_id"]]},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["total"] == 2


# ---------------------------------------------------------------------------
# 11. Product images exceeds 10 fails
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_product_images_exceeds_10_fails(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    product = await _create_test_product(db)

    for i in range(10):
        data = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, f"img{i}.jpg", "image/jpeg")
        pi = ProductImage(product_id=product.id, attachment_id=UUID(data["attachment_id"]), sort=i)
        db.add(pi)
    await db.commit()

    extra = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "extra.jpg", "image/jpeg")
    resp = await client.post(
        f"/api/v1/products/{product.id}/images",
        json={"attachment_ids": [extra["attachment_id"]]},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "上限" in resp.json()["detail"]["msg"]


# ---------------------------------------------------------------------------
# 12. Setting product primary removes other primaries
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_set_product_cover_removes_other_covers(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    img1 = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "c1.jpg", "image/jpeg")
    img2 = await _upload_file(client, headers, _IMAGE_PNG_CONTENT, "c2.png", "image/png")

    product = await _create_test_product(db)
    pi1 = ProductImage(product_id=product.id, attachment_id=UUID(img1["attachment_id"]), is_cover=False)
    pi2 = ProductImage(product_id=product.id, attachment_id=UUID(img2["attachment_id"]), is_cover=True)
    db.add_all([pi1, pi2])
    await db.commit()

    resp = await client.patch(
        f"/api/v1/products/{product.id}/images/{pi1.id}/cover",
        headers=headers,
    )
    assert resp.status_code == 200

    await db.refresh(pi1)
    await db.refresh(pi2)
    assert pi1.is_cover is True
    assert pi2.is_cover is False


# ---------------------------------------------------------------------------
# 13. Product bind scene image success
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_product_bind_scene_image_success(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "scene.jpg", "image/jpeg")

    resp = await client.post(
        "/api/v1/scene-images",
        json={"name": "Nice Scene", "attachment_id": img["attachment_id"]},
        headers=headers,
    )
    assert resp.status_code == 201
    si_id = resp.json()["data"]["id"]

    product = await _create_test_product(db)
    await db.commit()
    resp = await client.post(
        f"/api/v1/products/{product.id}/scene-images",
        json={"scene_image_ids": [si_id]},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["bound"] == 1


# ---------------------------------------------------------------------------
# 14. Product scene images exceeds 30 fails
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_product_scene_images_exceeds_30_fails(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    product = await _create_test_product(db)

    si_ids = []
    for i in range(30):
        img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, f"si{i}.jpg", "image/jpeg")
        si = SceneImage(name=f"SI{i}", attachment_id=UUID(img["attachment_id"]))
        db.add(si)
        await db.flush()
        stmt = product_scene_image.insert().values(product_id=product.id, scene_image_id=si.id)
        await db.execute(stmt)
        si_ids.append(si.id)
    await db.commit()

    extra_img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "extra_scene.jpg", "image/jpeg")
    resp = await client.post(
        "/api/v1/scene-images",
        json={"name": "Extra SI", "attachment_id": extra_img["attachment_id"]},
        headers=headers,
    )
    assert resp.status_code == 201
    extra_si_id = resp.json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/products/{product.id}/scene-images",
        json={"scene_image_ids": [extra_si_id]},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "上限" in resp.json()["detail"]["msg"]


# ---------------------------------------------------------------------------
# 15. Scene image binds to multiple products
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scene_image_bind_multiple_products(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "multi.jpg", "image/jpeg")

    resp = await client.post(
        "/api/v1/scene-images",
        json={"name": "Multi Scene", "attachment_id": img["attachment_id"]},
        headers=headers,
    )
    assert resp.status_code == 201
    si_id = UUID(resp.json()["data"]["id"])

    prod1 = await _create_test_product(db)
    prod2 = await _create_test_product(db)
    await db.commit()

    resp = await client.post(
        f"/api/v1/scene-images/{si_id}/bind",
        json={"product_ids": [str(prod1.id), str(prod2.id)]},
        headers=headers,
    )
    assert resp.status_code == 200

    from sqlalchemy.orm import selectinload

    si = await db.scalar(
        select(SceneImage)
        .where(SceneImage.id == si_id)
        .options(selectinload(SceneImage.products))
    )
    assert len(si.products) == 2


# ---------------------------------------------------------------------------
# 16. Product unbind scene image does not delete media
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_product_unbind_scene_image_keeps_media(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "unbind.jpg", "image/jpeg")
    att_id = UUID(img["attachment_id"])

    resp = await client.post(
        "/api/v1/scene-images",
        json={"name": "Unbind Scene", "attachment_id": img["attachment_id"]},
        headers=headers,
    )
    assert resp.status_code == 201
    si_id = resp.json()["data"]["id"]

    product = await _create_test_product(db)
    await db.commit()
    await client.post(
        f"/api/v1/products/{product.id}/scene-images",
        json={"scene_image_ids": [si_id]},
        headers=headers,
    )

    resp = await client.delete(
        f"/api/v1/products/{product.id}/scene-images/{si_id}",
        headers=headers,
    )
    assert resp.status_code == 200

    att = await db.get(Attachment, att_id)
    assert att is not None
    assert att.is_deleted is False


# ---------------------------------------------------------------------------
# 17. Share API returns cover_image_url
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_share_api_returns_cover_image_url(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "cover.jpg", "image/jpeg")

    product = await _create_test_product(db)
    pi = ProductImage(product_id=product.id, attachment_id=UUID(img["attachment_id"]), is_cover=True)
    db.add(pi)
    await db.commit()

    from app.models.sales import Proposal, ProposalItem
    proposal = Proposal(
        proposal_no=f"PROPOSAL{uuid4().hex[:8].upper()}",
        proposal_name="Test Share Cover",
        creator_id=(await _get_admin_user_id(db)),
    )
    db.add(proposal)
    await db.flush()
    pi_item = ProposalItem(proposal_id=proposal.id, product_id=product.id)
    db.add(pi_item)
    await db.commit()

    share_info = await _create_share_token(client, headers, str(proposal.id), expire_hours=24)

    resp = await client.get(f"/api/v1/share/{share_info['token']}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["content"]["items"][0]["cover_image_url"] is not None


# ---------------------------------------------------------------------------
# 18. Share API returns scene_images
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_share_api_returns_scene_images(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    si_img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "si_share.jpg", "image/jpeg")

    resp = await client.post(
        "/api/v1/scene-images",
        json={"name": "Share SI", "attachment_id": si_img["attachment_id"]},
        headers=headers,
    )
    si_id = resp.json()["data"]["id"]

    product = await _create_test_product(db)
    await db.commit()
    await client.post(
        f"/api/v1/products/{product.id}/scene-images",
        json={"scene_image_ids": [si_id]},
        headers=headers,
    )

    from app.models.sales import Proposal, ProposalItem
    proposal = Proposal(
        proposal_no=f"PROPOSAL{uuid4().hex[:8].upper()}",
        proposal_name="Test Share SI",
        creator_id=(await _get_admin_user_id(db)),
    )
    db.add(proposal)
    await db.flush()
    pi_item = ProposalItem(proposal_id=proposal.id, product_id=product.id)
    db.add(pi_item)
    await db.commit()

    share_info = await _create_share_token(client, headers, str(proposal.id), expire_hours=24)

    resp = await client.get(f"/api/v1/share/{share_info['token']}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    item = data["content"]["items"][0]
    assert len(item["scene_images"]) >= 1
    assert item["scene_images"][0]["image_url"] is not None


# ---------------------------------------------------------------------------
# 19. Share token expired -> cannot get data and new image URLs
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_share_token_expired_cannot_access(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    product = await _create_test_product(db)

    from app.models.sales import Proposal, ProposalItem
    proposal = Proposal(
        proposal_no=f"PROPOSAL{uuid4().hex[:8].upper()}",
        proposal_name="Expired Share",
        creator_id=(await _get_admin_user_id(db)),
    )
    db.add(proposal)
    await db.flush()
    pi_item = ProposalItem(proposal_id=proposal.id, product_id=product.id)
    db.add(pi_item)
    await db.commit()

    share_info = await _create_share_token(client, headers, str(proposal.id), expire_hours=1)

    # 将 token 的过期时间改为过去，模拟过期场景
    from app.models.audit import ShareToken
    result = await db.execute(
        select(ShareToken).where(ShareToken.token == share_info["token"], ShareToken.is_deleted.is_(False))
    )
    token_obj = result.scalar_one_or_none()
    assert token_obj is not None, "ShareToken not found"
    token_obj.expire_time = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()

    resp = await client.get(f"/api/v1/share/{share_info['token']}")
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert "过期" in detail["msg"]


# ---------------------------------------------------------------------------
# Helper: get admin user ID
# ---------------------------------------------------------------------------

async def _get_admin_user_id(db: AsyncSession) -> UUID:
    from app.models.user import User
    result = await db.execute(select(User.id).where(User.username == "admin"))
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Permission tests for new codes
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_permissions_required(client: AsyncClient):
    resp = await client.get("/api/v1/files")
    assert resp.status_code == 401

    resp = await client.post("/api/v1/files/upload", files={"file": ("x.jpg", b"x", "image/jpeg")})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_scene_image_permissions_required(client: AsyncClient):
    resp = await client.get("/api/v1/scene-images")
    assert resp.status_code == 401

    resp = await client.post("/api/v1/scene-images", json={"name": "x", "attachment_id": str(uuid4())})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Replace endpoint: type mismatch
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_media_replace_type_mismatch_fails(client: AsyncClient):
    headers = await _auth_header(client)
    data = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "img.jpg", "image/jpeg")

    resp = await client.put(
        f"/api/v1/files/{data['attachment_id']}/replace",
        files={"file": ("doc.pdf", _PDF_CONTENT, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "类型不匹配" in resp.json()["detail"]["msg"]


# ---------------------------------------------------------------------------
# Scene image delete also unbinds products
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scene_image_delete_unbinds_products(client: AsyncClient, db: AsyncSession):
    headers = await _auth_header(client)
    img = await _upload_file(client, headers, _IMAGE_JPEG_CONTENT, "si_del.jpg", "image/jpeg")

    resp = await client.post(
        "/api/v1/scene-images",
        json={"name": "Delete SI", "attachment_id": img["attachment_id"]},
        headers=headers,
    )
    si_id = UUID(resp.json()["data"]["id"])

    product = await _create_test_product(db)
    await db.commit()
    await client.post(
        f"/api/v1/products/{product.id}/scene-images",
        json={"scene_image_ids": [str(si_id)]},
        headers=headers,
    )

    await client.delete(f"/api/v1/scene-images/{si_id}", headers=headers)

    result = await db.execute(
        select(product_scene_image).where(
            product_scene_image.c.scene_image_id == si_id,
            product_scene_image.c.is_deleted.is_(False),
        )
    )
    assert result.scalar_one_or_none() is None
