"""Track C 端到端：方案（楼层/空间/快照）→ 报价预填 → PDF → 客户分享页。

链路验收（任务要求"创建方案时选择楼层、空间，客户展示更完整"）::

    建项目 -> 建楼层/空间 -> 建产品 -> 建方案（明细带空间+快照）
      -> 方案详情展示空间
      -> 报价预填复制楼层/空间/材质说明/产品快照
      -> 报价详情展示空间
      -> 分享接口传递空间字段
      -> PDF HTML 含楼层/空间/材质说明/颜色列

需要可连的 Postgres 测试库（``TEST_DATABASE_URL``）；连不上时整文件 skip，
显示 skipped 而不是 passed，绝不把"环境缺失"当成"通过"。
"""

import base64
import json

import pytest

pytestmark = pytest.mark.anyio

ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}


async def _login_as_admin(client):
    resp = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return {"Authorization": f"Bearer {token}"}, str(claims["sub"])


@pytest.fixture
def prepare():
    """返回一个协程工厂：在**测试体自身的事件循环**里完成准备。

    不能在 async fixture 里发 HTTP：anyio/pytest-asyncio 可能让 fixture 与
    测试体跑在不同 loop 上，跨 loop 复用连接池会直接抛
    ``attached to a different loop``。
    """

    async def _prepare(client):
        headers, creator_id = await _login_as_admin(client)

        async def _post(path, payload):
            resp = await client.post(path, headers=headers, json=payload)
            assert resp.status_code in (200, 201), (path, resp.status_code, resp.text)
            return resp.json()

        brand = await _post("/api/v1/brands", {"brand_name": "TrackC 品牌"})
        supplier = await _post("/api/v1/suppliers", {"supplier_name": "TrackC 供应商"})
        category = await _post("/api/v1/categories", {"category_name": "会议桌"})

        customer = await _post(
            "/api/v1/customers", {"name": "TrackC 端到端客户", "source": "other"}
        )
        project = await _post(
            "/api/v1/projects",
            {
                "customer_id": customer["data"]["id"],
                "name": "TrackC 端到端项目",
                "remark": "TrackC 项目备注",
            },
        )
        project_id = project["data"]["id"]
        assert project["data"]["remark"] == "TrackC 项目备注"
        project_update = await client.put(
            f"/api/v1/projects/{project_id}",
            headers=headers,
            json={"remark": "TrackC 项目备注已更新"},
        )
        assert project_update.status_code == 200, project_update.text
        assert project_update.json()["data"]["remark"] == "TrackC 项目备注已更新"

        other_project = await _post(
            "/api/v1/projects",
            {"customer_id": customer["data"]["id"], "name": "TrackC 其他项目"},
        )

        floor = await _post(
            f"/api/v1/projects/{project_id}/spaces",
            {"space_name": "3F", "space_type": "floor"},
        )
        room = await _post(
            f"/api/v1/projects/{project_id}/spaces",
            {
                "space_name": "大会议室",
                "space_type": "room",
                "parent_id": floor["data"]["id"],
            },
        )
        other_space = await _post(
            f"/api/v1/projects/{other_project['data']['id']}/spaces",
            {"space_name": "外部会议室", "space_type": "room"},
        )
        product = await _post(
            "/api/v1/products",
            {
                "product_no": f"TRACKC-{room['data']['id'][-6:]}",
                "product_name": "弧形会议桌",
                "brand_id": brand["id"],
                "supplier_id": supplier["id"],
                "category_id": category["id"],
                "face_price": 6800,
                "material": "铝合金",
                "specification": "3200*1620*760",
                "colors": "胡桃木",
                "status": "active",
            },
        )
        return {
            "headers": headers,
            "project_id": project_id,
            "floor_id": floor["data"]["id"],
            "room_id": room["data"]["id"],
            "other_space_id": other_space["data"]["id"],
            "customer_id": customer["data"]["id"],
            # 产品创建接口返回裸产品对象（无 data 信封）
            "product_id": product["id"],
            "creator_id": creator_id,
        }

    return _prepare


async def test_proposal_to_quotation_share_chain(client, prepare):
    prepared = await prepare(client)
    headers = prepared["headers"]

    # 1) 建方案：明细带楼层/空间/材质说明（快照由服务端生成）
    proposal = await client.post(
        "/api/v1/proposals",
        headers=headers,
        json={
            "proposal_name": "TrackC 方案",
            "creator_id": prepared["creator_id"],
            "customer_name": "TrackC 端到端客户",
            "customer_id": prepared["customer_id"],
            "project_id": prepared["project_id"],
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 2,
                    "project_space_id": prepared["room_id"],
                    "floor_label": "3F",
                    "space_label": "大会议室",
                    "material_desc": "铝合金台面 + 钢制桌腿",
                }
            ],
        },
    )
    assert proposal.status_code in (200, 201), proposal.text
    proposal_data = proposal.json()["data"]
    proposal_id = proposal_data["id"]
    assert proposal_data["customer_id"] == prepared["customer_id"]
    assert proposal_data["project_id"] == prepared["project_id"]

    cross_project_edit = await client.put(
        f"/api/v1/proposals/{proposal_id}",
        headers=headers,
        json={
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "project_space_id": prepared["other_space_id"],
                }
            ]
        },
    )
    assert cross_project_edit.status_code == 422, cross_project_edit.text

    proposal_update = await client.put(
        f"/api/v1/proposals/{proposal_id}",
        headers=headers,
        json={
            "customer_id": prepared["customer_id"],
            "project_id": prepared["project_id"],
        },
    )
    assert proposal_update.status_code == 200, proposal_update.text
    assert proposal_update.json()["data"]["customer_id"] == prepared["customer_id"]
    assert proposal_update.json()["data"]["project_id"] == prepared["project_id"]
    proposal_data = proposal_update.json()["data"]

    # 2) 方案详情必须展示空间与快照
    item = proposal_data["items"][0]
    assert item["project_space_id"] == prepared["room_id"]
    assert item["floor_label"] == "3F"
    assert item["space_label"] == "大会议室"
    assert item["material_desc"] == "铝合金台面 + 钢制桌腿"
    assert item["product_snapshot"], "方案明细必须带产品快照"
    assert item["product_snapshot"]["product_no"]

    # 3) 报价预填：从方案复制楼层/空间/材质说明/快照
    quotation = await client.post(
        "/api/v1/quotations",
        headers=headers,
        json={
            "proposal_id": proposal_id,
            "tax_rate": 0.13,
            "discount": 1.0,
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 2,
                    "unit_price": 6800,
                    "tax_rate": 0.13,
                    "project_space_id": prepared["room_id"],
                    "floor_label": "3F",
                    "space_label": "大会议室",
                    "material_desc": "铝合金台面 + 钢制桌腿",
                }
            ],
        },
    )
    assert quotation.status_code in (200, 201), quotation.text
    quotation_data = quotation.json()["data"]
    quotation_id = quotation_data["id"]

    q_item = quotation_data["items"][0]
    assert q_item["project_space_id"] == prepared["room_id"]
    assert q_item["floor_label"] == "3F"
    assert q_item["space_label"] == "大会议室"
    assert q_item["material_desc"] == "铝合金台面 + 钢制桌腿"
    # 快照口径与方案一致（同一份产品事实，不漂移）
    assert q_item["product_snapshot"]["product_no"] == item["product_snapshot"]["product_no"]

    # Spaces and product facts are inherited from matching proposal items when omitted.
    copied_quotation = await client.post(
        "/api/v1/quotations",
        headers=headers,
        json={
            "proposal_id": proposal_id,
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 2,
                    "unit_price": 6800,
                    "tax_rate": 0.13,
                }
            ],
        },
    )
    assert copied_quotation.status_code in (200, 201), copied_quotation.text
    copied_item = copied_quotation.json()["data"]["items"][0]
    assert copied_item["project_space_id"] == prepared["room_id"]
    assert copied_item["floor_label"] == item["floor_label"]
    assert copied_item["space_label"] == item["space_label"]
    assert copied_item["material_desc"] == item["material_desc"]
    assert copied_item["product_snapshot"] == item["product_snapshot"]

    cross_project_quotation = await client.post(
        "/api/v1/quotations",
        headers=headers,
        json={
            "proposal_id": proposal_id,
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 1,
                    "unit_price": 6800,
                    "project_space_id": prepared["other_space_id"],
                }
            ],
        },
    )
    assert cross_project_quotation.status_code == 422, cross_project_quotation.text

    # 4) 报价详情同样展示空间
    detail = await client.get(f"/api/v1/quotations/{quotation_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["items"][0]["space_label"] == "大会议室"

    # 5) 分享接口把空间字段带给客户页（报价需先确认才可分享）
    confirm = await client.post(
        f"/api/v1/quotations/{quotation_id}/confirm", headers=headers
    )
    assert confirm.status_code == 200, confirm.text

    share = await client.post(
        "/api/v1/shares",
        headers=headers,
        json={"share_type": "quotation", "target_id": quotation_id},
    )
    assert share.status_code in (200, 201), share.text
    share_token = share.json()["data"]["token"]

    portal = await client.get(f"/api/v1/share/{share_token}")
    assert portal.status_code == 200, portal.text
    portal_content = portal.json()["data"]["content"]
    portal_items = portal_content["items"]
    assert portal_items, "客户页必须拿到报价明细"
    assert portal_items[0]["floor_label"] == "3F"
    assert portal_items[0]["space_label"] == "大会议室"
    assert portal_items[0]["material_desc"] == "铝合金台面 + 钢制桌腿"
    assert portal_items[0]["product_snapshot"]

    # 6) PDF HTML 必须含楼层/空间/材质说明/颜色列
    from app.api.v1.quotations import _build_quotation_html
    from app.models.sales import Quotation, QuotationItem

    quotation_obj = Quotation(
        id=quotation_data["id"],
        quotation_no=quotation_data["quotation_no"],
        proposal_id=proposal_id,
        status="draft",
        discount=quotation_data.get("discount") or 1.0,
        tax_rate=quotation_data.get("tax_rate") or 0.13,
        total_amount=quotation_data.get("total_amount") or 0.0,
    )
    quotation_obj.items = [
        QuotationItem(
            product_id=prepared["product_id"],
            quantity=2,
            unit_price=6800,
            tax_rate=0.13,
            subtotal=13600,
            project_space_id=prepared["room_id"],
            floor_label="3F",
            space_label="大会议室",
            material_desc="铝合金台面 + 钢制桌腿",
            product_snapshot=q_item["product_snapshot"],
        )
    ]
    html = _build_quotation_html(quotation_obj, {})
    for column in ("楼层", "空间", "材质说明", "颜色"):
        assert column in html, f"PDF 缺少 {column} 列"
    assert "3F" in html and "大会议室" in html
    assert "铝合金台面 + 钢制桌腿" in html


async def test_quotation_without_space_fields_still_works(client, prepare):
    """旧口径（不带空间字段）的报价仍然可用，不回归。"""
    prepared = await prepare(client)
    headers = prepared["headers"]

    proposal = await client.post(
        "/api/v1/proposals",
        headers=headers,
        json={
            "proposal_name": "TrackC 无空间方案",
            "creator_id": prepared["creator_id"],
            "customer_name": "TrackC 端到端客户",
            "items": [
                {"product_id": prepared["product_id"], "quantity": 1}
            ],
        },
    )
    assert proposal.status_code in (200, 201), proposal.text
    proposal_id = proposal.json()["data"]["id"]

    quotation = await client.post(
        "/api/v1/quotations",
        headers=headers,
        json={
            "proposal_id": proposal_id,
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 1,
                    "unit_price": 6800,
                    "tax_rate": 0.13,
                }
            ],
        },
    )
    assert quotation.status_code in (200, 201), quotation.text
    item = quotation.json()["data"]["items"][0]
    assert item["project_space_id"] is None
    assert item["floor_label"] is None
    # 快照仍由服务端生成（从方案明细继承）
    assert item["product_snapshot"]


async def test_proposal_rejects_space_from_another_project(client, prepare):
    prepared = await prepare(client)
    response = await client.post(
        "/api/v1/proposals",
        headers=prepared["headers"],
        json={
            "proposal_name": "Cross-project space validation",
            "creator_id": prepared["creator_id"],
            "project_id": prepared["project_id"],
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "project_space_id": prepared["other_space_id"],
                }
            ],
        },
    )
    assert response.status_code == 422, response.text


async def test_proposal_accepts_free_form_labels_and_preserves_them_on_edit(client, prepare):
    """Labels can create a project binding, and editing echoes the snapshots."""
    prepared = await prepare(client)
    headers = prepared["headers"]
    response = await client.post(
        "/api/v1/proposals",
        headers=headers,
        json={
            "proposal_name": "自由输入空间方案",
            "creator_id": prepared["creator_id"],
            "project_id": prepared["project_id"],
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 1,
                    "floor_label": " 4F ",
                    "space_label": " 新会议室 ",
                    "material_desc": "铝合金台面",
                }
            ],
        },
    )
    assert response.status_code in (200, 201), response.text
    proposal = response.json()["data"]
    item = proposal["items"][0]
    assert item["floor_label"] == "4F"
    assert item["space_label"] == "新会议室"
    assert item["project_space_id"]
    assert item["material_desc"] == "铝合金台面"
    assert item["product_snapshot"]

    edited = await client.put(
        f"/api/v1/proposals/{proposal['id']}",
        headers=headers,
        json={
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 2,
                    "floor_label": "5F",
                    "space_label": "新洽谈室",
                    "material_desc": "实木台面",
                }
            ]
        },
    )
    assert edited.status_code == 200, edited.text
    edited_item = edited.json()["data"]["items"][0]
    assert edited_item["floor_label"] == "5F"
    assert edited_item["space_label"] == "新洽谈室"
    assert edited_item["project_space_id"]
    assert edited_item["material_desc"] == "实木台面"
    assert edited_item["product_snapshot"]


async def test_proposal_without_project_keeps_labels_without_binding(client, prepare):
    """No project must not block a proposal that only has label snapshots."""
    prepared = await prepare(client)
    response = await client.post(
        "/api/v1/proposals",
        headers=prepared["headers"],
        json={
            "proposal_name": "无项目自由输入空间方案",
            "creator_id": prepared["creator_id"],
            "items": [
                {
                    "product_id": prepared["product_id"],
                    "quantity": 1,
                    "floor_label": "待确认楼层",
                    "space_label": "待确认空间",
                }
            ],
        },
    )
    assert response.status_code in (200, 201), response.text
    item = response.json()["data"]["items"][0]
    assert item["project_space_id"] is None
    assert item["floor_label"] == "待确认楼层"
    assert item["space_label"] == "待确认空间"
