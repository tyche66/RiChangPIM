"""Attribute dictionary startup seed integration checks (safe test DB only)."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.knowledge.attributes import await_load_dictionary, build_product_query
from app.models.catalog_attribute import (
    CatalogAttributeAlias,
    CatalogAttributeDefinition,
    CatalogAttributeOption,
    ProductAttributeValue,
)
from app.models.product import Category


@pytest.mark.anyio
async def test_seed_is_idempotent_preserves_business_edits_and_does_not_backfill(
    _engine, _sessionmaker, monkeypatch
):
    import app.scripts.seed_attribute_dictionary as seed

    monkeypatch.setattr(seed, "AsyncSessionLocal", _sessionmaker)

    async with _sessionmaker() as db:
        empty_dictionary = await await_load_dictionary(db)
    assert build_product_query("弧形会议桌", empty_dictionary).hard_facets == []

    await seed.run(apply=True, include_categories=False)
    async with _sessionmaker() as db:
        dictionary = await await_load_dictionary(db)
        assert any(
            facet.attribute_code == "shape" and facet.values == ["arc"]
            for facet in build_product_query("弧形会议桌", dictionary).hard_facets
        )
        shape = (
            await db.execute(
                select(CatalogAttributeDefinition).where(
                    CatalogAttributeDefinition.code == "shape"
                )
            )
        ).scalar_one()
        arc = (
            await db.execute(
                select(CatalogAttributeOption).where(
                    CatalogAttributeOption.attribute_id == shape.id,
                    CatalogAttributeOption.code == "arc",
                )
            )
        ).scalar_one()
        shape.name = "业务自定义桌形"
        arc.label = "业务自定义弧形"
        retired_alias = (
            await db.execute(
                select(CatalogAttributeAlias).where(
                    CatalogAttributeAlias.option_id == arc.id,
                    CatalogAttributeAlias.normalized_alias == "圆弧",
                )
            )
        ).scalar_one()
        retired_alias.is_deleted = True
        await db.commit()

    await seed.run(apply=True, include_categories=False)
    async with _sessionmaker() as db:
        shape = (
            await db.execute(
                select(CatalogAttributeDefinition).where(
                    CatalogAttributeDefinition.code == "shape"
                )
            )
        ).scalar_one()
        arc = (
            await db.execute(
                select(CatalogAttributeOption).where(
                    CatalogAttributeOption.attribute_id == shape.id,
                    CatalogAttributeOption.code == "arc",
                )
            )
        ).scalar_one()
        value_count = (
            await db.execute(select(func.count()).select_from(ProductAttributeValue))
        ).scalar_one()

    assert shape.name == "业务自定义桌形"
    assert arc.label == "业务自定义弧形"
    assert retired_alias.is_deleted is True
    assert value_count == 0


@pytest.mark.anyio
async def test_category_seed_uses_category_name_as_option_code(_engine, _sessionmaker, monkeypatch):
    import app.scripts.seed_attribute_dictionary as seed

    monkeypatch.setattr(seed, "AsyncSessionLocal", _sessionmaker)

    async with _sessionmaker() as db:
        db.add(
            Category(
                id=uuid4(),
                category_name="会议桌",
                level=1,
                sort=0,
                is_deleted=False,
            )
        )
        await db.commit()

    await seed.run(apply=True, include_categories=True)

    async with _sessionmaker() as db:
        definition = (
            await db.execute(
                select(CatalogAttributeDefinition).where(
                    CatalogAttributeDefinition.code == "category"
                )
            )
        ).scalar_one()
        option = (
            await db.execute(
                select(CatalogAttributeOption).where(
                    CatalogAttributeOption.attribute_id == definition.id,
                    CatalogAttributeOption.label == "会议桌",
                )
            )
        ).scalar_one()

    assert option.code == "会议桌"
