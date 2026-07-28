from app.knowledge.documents.base import normalize_text, stable_content_hash
from app.knowledge.documents.product_card import DatabaseProductFactProvider


def test_product_card_render_includes_only_expected_labels():
    text = DatabaseProductFactProvider._render_card_text(
        {
            "product_name": "测试桌",
            "product_no": "A100",
            "brand": "圣奥",
            "tags": ["人体工学", "办公"],
            "description": "适用于办公室。",
        }
    )

    assert "产品名称: 测试桌" in text
    assert "产品编号: A100" in text
    assert "品牌: 圣奥" in text
    assert "标签: 人体工学、办公" in text
    assert "面价" not in text
    assert "成本" not in text
    assert "供应商" not in text


def test_normalize_text_collapses_whitespace():
    assert normalize_text(" A\n\tB   C ") == "A B C"


def test_stable_content_hash_is_order_insensitive_for_dict_keys():
    left = stable_content_hash({"b": 1, "a": [1, 2]})
    right = stable_content_hash({"a": [1, 2], "b": 1})
    assert left == right
