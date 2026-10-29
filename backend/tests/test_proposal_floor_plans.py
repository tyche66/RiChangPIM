"""Track D：方案平面图 —— 媒体库绑定、分享页透出、媒体删除保护。

覆盖链路：
    媒体库附件 + 方案 -> 绑定平面图（改名/排序/解绑）
      -> 方案详情返回（带短时展示地址）
      -> 公开分享 payload 透出 floor_plans
      -> 媒体库删除被引用附件时给出「方案平面图」引用明细
      -> 方案换项目时平面图的 project_id 跟随

需要可连的 Postgres 测试库（``TEST_DATABASE_URL``）；连不上时整文件 skip。
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.audit import Share, ShareToken
from app.models.customer import Customer
from app.models.product import Attachment
from app.models.project import Project
from app.models.sales import Proposal, ProposalFloorPlan
from app.models.user import User

pytestmark = pytest.mark.anyio

ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}


async def _login(client) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _admin_id(session) -> uuid.UUID:
    user = (await session.execute(select(User).where(User.username == "admin"))).scalar_one()
    return user.id


async def _seed_attachment(session, *, file_type: str = "image", name: str = "一层平面图.png"):
    attachment = Attachment(
        file_name=name,
        file_url=f"/files/image/{uuid.uuid4().hex}.png",
        file_type=file_type,
        file_size=2048,
        storage_type="minio",
        oss_key=f"image/{uuid.uuid4().hex}.png",
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def _seed_proposal(session, *, project_id=None) -> Proposal:
    proposal = Proposal(
        proposal_no=f"PR-TEST-{uuid.uuid4().hex[:8].upper()}",
        proposal_name="平面图测试方案",
        creator_id=await _admin_id(session),
        project_id=project_id,
        status="draft",
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def _seed_project(session, name: str) -> Project:
    admin_id = await _admin_id(session)
    customer = Customer(name=f"平面图客户-{uuid.uuid4().hex[:6]}", owner_sales_id=admin_id)
    session.add(customer)
    await session.flush()
    project = Project(customer_id=customer.id, name=name)
    session.add(project)
    await session.flush()
    return project


async def test_create_list_update_delete_floor_plan(client, _sessionmaker):
    headers = await _login(client)
    async with _sessionmaker() as session:
        proposal = await _seed_proposal(session)
        attachment = await _seed_attachment(session)
        await session.commit()
        proposal_id, attachment_id = proposal.id, attachment.id

    created = await client.post(
        f"/api/v1/proposals/{proposal_id}/floor-plans",
        headers=headers,
        json={"attachment_id": str(attachment_id), "name": "江韵方案一层平面图"},
    )
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["name"] == "江韵方案一层平面图"
    assert data["attachment_id"] == str(attachment_id)
    assert data["image_url"].startswith(f"/api/v1/files/{attachment_id}/content?token=")
    assert "minio" not in data["image_url"]
    floor_plan_id = data["id"]

    listing = await client.get(f"/api/v1/proposals/{proposal_id}/floor-plans", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 1
    assert listing.json()["data"]["list"][0]["name"] == "江韵方案一层平面图"

    renamed = await client.put(
        f"/api/v1/proposals/{proposal_id}/floor-plans/{floor_plan_id}",
        headers=headers,
        json={"name": "江韵方案二层平面图", "sort": 5},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["name"] == "江韵方案二层平面图"
    assert renamed.json()["data"]["sort"] == 5

    deleted = await client.delete(
        f"/api/v1/proposals/{proposal_id}/floor-plans/{floor_plan_id}", headers=headers
    )
    assert deleted.status_code == 200, deleted.text

    listing = await client.get(f"/api/v1/proposals/{proposal_id}/floor-plans", headers=headers)
    assert listing.json()["data"]["total"] == 0

    # 解绑不删除媒体库文件
    async with _sessionmaker() as session:
        still_there = (
            await session.execute(
                select(Attachment).where(Attachment.id == attachment_id)
            )
        ).scalar_one()
        assert still_there.is_deleted is False


async def test_create_rejects_non_image_and_duplicate(client, _sessionmaker):
    headers = await _login(client)
    async with _sessionmaker() as session:
        proposal = await _seed_proposal(session)
        image = await _seed_attachment(session)
        pdf = await _seed_attachment(session, file_type="pdf", name="方案.pdf")
        await session.commit()
        proposal_id, image_id, pdf_id = proposal.id, image.id, pdf.id

    rejected = await client.post(
        f"/api/v1/proposals/{proposal_id}/floor-plans",
        headers=headers,
        json={"attachment_id": str(pdf_id), "name": "PDF 平面图"},
    )
    assert rejected.status_code == 422, rejected.text
    assert "image" in rejected.text

    first = await client.post(
        f"/api/v1/proposals/{proposal_id}/floor-plans",
        headers=headers,
        json={"attachment_id": str(image_id), "name": "一层平面图"},
    )
    assert first.status_code == 201, first.text

    duplicate = await client.post(
        f"/api/v1/proposals/{proposal_id}/floor-plans",
        headers=headers,
        json={"attachment_id": str(image_id), "name": "一层平面图（重复）"},
    )
    assert duplicate.status_code == 422, duplicate.text


async def test_proposal_detail_returns_floor_plans(client, _sessionmaker):
    headers = await _login(client)
    async with _sessionmaker() as session:
        proposal = await _seed_proposal(session)
        attachment = await _seed_attachment(session)
        await session.commit()
        proposal_id, attachment_id = proposal.id, attachment.id

    created = await client.post(
        f"/api/v1/proposals/{proposal_id}/floor-plans",
        headers=headers,
        json={"attachment_id": str(attachment_id), "name": "一层平面图"},
    )
    assert created.status_code == 201, created.text

    detail = await client.get(f"/api/v1/proposals/{proposal_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    floor_plans = detail.json()["data"]["floor_plans"]
    assert len(floor_plans) == 1
    assert floor_plans[0]["name"] == "一层平面图"
    assert floor_plans[0]["image_url"].startswith("/api/v1/files/")


async def test_share_payload_exposes_floor_plans(client, _sessionmaker):
    async with _sessionmaker() as session:
        proposal = await _seed_proposal(session)
        attachment = await _seed_attachment(session)
        share = Share(
            share_type="proposal",
            target_id=proposal.id,
            creator_id=await _admin_id(session),
            status="active",
        )
        session.add(share)
        await session.flush()
        token = f"tk_{uuid.uuid4().hex[:12]}"
        session.add(
            ShareToken(share_id=share.id, token=token, status="active", current_access_count=0)
        )
        session.add(
            ProposalFloorPlan(
                proposal_id=proposal.id,
                attachment_id=attachment.id,
                name="江韵方案一层平面图",
                sort=0,
            )
        )
        await session.commit()

    resp = await client.get(f"/api/v1/share/{token}")
    assert resp.status_code == 200, resp.text
    content = resp.json()["data"]["content"]
    assert content["floor_plans"]
    plan = content["floor_plans"][0]
    assert plan["name"] == "江韵方案一层平面图"
    assert plan["image_url"].startswith("/api/v1/files/")
    assert "minio" not in plan["image_url"]


async def test_media_library_blocks_delete_of_bound_floor_plan(client, _sessionmaker):
    headers = await _login(client)
    async with _sessionmaker() as session:
        proposal = await _seed_proposal(session)
        attachment = await _seed_attachment(session)
        await session.commit()
        proposal_id, attachment_id = proposal.id, attachment.id

    created = await client.post(
        f"/api/v1/proposals/{proposal_id}/floor-plans",
        headers=headers,
        json={"attachment_id": str(attachment_id), "name": "一层平面图"},
    )
    assert created.status_code == 201, created.text

    detail = await client.get(
        f"/api/v1/files/{attachment_id}", headers=headers, params={"with_references": "true"}
    )
    assert detail.status_code == 200, detail.text
    refs = detail.json()["data"]["references"]
    assert len(refs["proposal_floor_plans"]) == 1
    assert refs["proposal_floor_plans"][0]["floor_plan_name"] == "一层平面图"

    blocked = await client.delete(f"/api/v1/files/{attachment_id}", headers=headers)
    assert blocked.status_code == 422, blocked.text
    assert "方案平面图" in blocked.text


async def test_floor_plan_project_follows_proposal_project(client, _sessionmaker):
    headers = await _login(client)
    async with _sessionmaker() as session:
        project_a = await _seed_project(session, "平面图项目 A")
        project_b = await _seed_project(session, "平面图项目 B")
        proposal = await _seed_proposal(session, project_id=project_a.id)
        attachment = await _seed_attachment(session)
        await session.commit()
        proposal_id, attachment_id = proposal.id, attachment.id
        a_id, b_id = project_a.id, project_b.id

    created = await client.post(
        f"/api/v1/proposals/{proposal_id}/floor-plans",
        headers=headers,
        json={"attachment_id": str(attachment_id), "name": "一层平面图"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["project_id"] == str(a_id)

    moved = await client.put(
        f"/api/v1/proposals/{proposal_id}", headers=headers, json={"project_id": str(b_id)}
    )
    assert moved.status_code == 200, moved.text

    async with _sessionmaker() as session:
        row = (
            await session.execute(
                select(ProposalFloorPlan).where(ProposalFloorPlan.proposal_id == proposal_id)
            )
        ).scalar_one()
        assert row.project_id == b_id
