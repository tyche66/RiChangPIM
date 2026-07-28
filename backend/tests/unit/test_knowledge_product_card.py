from types import SimpleNamespace
from uuid import uuid4

from app.knowledge.gateway import _model_safe
from app.knowledge.tools import product as product_tools


def test_product_card_includes_signed_cover_image_without_exposing_it_to_model(monkeypatch):
    attachment_id = uuid4()
    monkeypatch.setattr(product_tools, "create_access_token", lambda *_args, **_kwargs: "signed-token")
    product = SimpleNamespace(
        id=uuid4(),
        product_no="MEET-001",
        product_name="会议桌",
        brand_id=uuid4(),
        brand=SimpleNamespace(brand_name="日常"),
        category_id=uuid4(),
        category=SimpleNamespace(category_name="会议桌"),
        supplier_id=uuid4(),
        supplier=SimpleNamespace(supplier_name="供应商"),
        face_price=6800,
        cost_price=4200,
        material="木饰面",
        stock_status="in_stock",
        status="published",
        completeness_status="complete",
        specification="2400mm",
        colors=["胡桃木"],
        description="适合多人会议",
        cover_image=SimpleNamespace(
            attachment=SimpleNamespace(id=attachment_id, is_deleted=False),
        ),
    )

    card = product_tools._product_card(product, {"sub": "user-1"})

    assert card["cover_image_url"] == f"/api/v1/files/{attachment_id}/content?token=signed-token"
    assert "cover_image_url" not in _model_safe(card)
