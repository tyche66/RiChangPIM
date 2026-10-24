from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import postgresql

from app.knowledge.tools.product import (
    ProductSearchInput,
    ProductSearchTool,
    _apply_product_facets,
)
from app.models.product import Product


@pytest.mark.parametrize(
    ("category", "shape", "included"),
    [
        (["会议桌"], ["弧形"], ("会议桌", "圆弧", "tag.tag_type in ('shape')")),
        (["会议桌"], ["矩形"], ("会议桌", "长方形", "tag.tag_type in ('shape')")),
        (["洽谈桌"], ["弧形"], ("洽谈桌", "圆弧", "tag.tag_type in ('shape')")),
    ],
)
@pytest.mark.asyncio
async def test_product_search_applies_exact_category_tree_and_shape_tag(
    category, shape, included
):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    context = SimpleNamespace(db=db, current_user={})

    await ProductSearchTool().run(
        ProductSearchInput(facets={"category": category, "shape": shape}), context
    )

    statement = db.execute.await_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).casefold()
    assert "with recursive category_tree" in sql
    assert "category.parent_id = category_tree.id" in sql
    assert "product_tag.is_deleted is false" in sql
    assert "tag.is_deleted is false" in sql
    for fragment in included:
        assert fragment.casefold() in sql
    assert "tag.tag_type in ('style')" not in sql
    assert "product.description ilike" not in sql


def test_product_facets_normalize_aliases_and_reject_unknown_dimensions():
    facets = ProductSearchInput(facets={"category": ["会议台"], "shape": ["弧型"]})

    assert facets.facets.category == ["会议桌"]
    assert facets.facets.shape == ["弧形"]

    with pytest.raises(ValueError):
        ProductSearchInput(facets={"curve": ["弧形"]})


def test_product_search_facet_predicates_exclude_description_and_style_false_positives():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE category (id TEXT PRIMARY KEY, parent_id TEXT, "
            "category_name TEXT, is_deleted BOOLEAN NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE product (id TEXT PRIMARY KEY, category_id TEXT, "
            "description TEXT, is_deleted BOOLEAN NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE tag (id TEXT PRIMARY KEY, tag_name TEXT, tag_type TEXT, "
            "is_deleted BOOLEAN NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE product_tag (product_id TEXT, tag_id TEXT, is_deleted BOOLEAN NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO category VALUES "
            "('meeting', NULL, '会议桌', 0), ('meeting-leaf', 'meeting', '经理会议桌', 0), "
            "('talk', NULL, '洽谈桌', 0)"
        ))
        connection.execute(text(
            "INSERT INTO product VALUES "
            "('00000000-0000-0000-0000-000000000001', 'meeting-leaf', '', 0), "
            "('00000000-0000-0000-0000-000000000002', 'meeting-leaf', '弧形桌边描述', 0), "
            "('00000000-0000-0000-0000-000000000003', 'talk', '', 0), "
            "('00000000-0000-0000-0000-000000000004', 'meeting-leaf', '弧形', 0), "
            "('00000000-0000-0000-0000-000000000005', 'meeting-leaf', '', 0), "
            "('00000000-0000-0000-0000-000000000006', 'meeting-leaf', '', 1), "
            "('00000000-0000-0000-0000-000000000007', 'meeting-leaf', '', 0), "
            "('00000000-0000-0000-0000-000000000008', 'meeting-leaf', '', 0)"
        ))
        connection.execute(text(
            "INSERT INTO tag VALUES "
            "('arc', '圆弧', 'shape', 0), ('rect', '长方形', 'shape', 0), "
            "('style-arc', '弧形', 'style', 0), ('deleted-arc', '弧形', 'shape', 1)"
        ))
        connection.execute(text(
            "INSERT INTO product_tag VALUES "
            "('00000000-0000-0000-0000-000000000001', 'arc', 0), "
            "('00000000-0000-0000-0000-000000000002', 'rect', 0), "
            "('00000000-0000-0000-0000-000000000003', 'arc', 0), "
            "('00000000-0000-0000-0000-000000000005', 'style-arc', 0), "
            "('00000000-0000-0000-0000-000000000006', 'arc', 0), "
            "('00000000-0000-0000-0000-000000000007', 'arc', 1), "
            "('00000000-0000-0000-0000-000000000008', 'deleted-arc', 0)"
        ))

        def matches(category: str, shape: str) -> set[str]:
            facets = ProductSearchInput(
                facets={"category": [category], "shape": [shape]}
            ).facets
            statement = select(Product.id).where(Product.is_deleted.is_(False))
            statement = _apply_product_facets(statement, facets)
            ids = connection.execute(statement).scalars()
            return {str(product_id) for product_id in ids}

        assert matches("会议桌", "弧形") == {"00000000-0000-0000-0000-000000000001"}
        assert matches("会议桌", "矩形") == {"00000000-0000-0000-0000-000000000002"}
        assert matches("洽谈桌", "弧形") == {"00000000-0000-0000-0000-000000000003"}

    engine.dispose()
