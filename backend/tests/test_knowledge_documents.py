from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.knowledge.documents.backfill import backfill_product_manual, upsert_product_card
from app.knowledge.documents.product_card import DatabaseProductFactProvider
from app.knowledge.tools.base import ToolContext
from app.knowledge.tools.product import ProductSearchInput, ProductSearchTool
from app.models.catalog_attribute import (
    CatalogAttributeDefinition,
    CatalogAttributeOption,
    ProductAttributeValue,
)
from app.models.doc_chunk import ProductManualChunk
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.product import Attachment, Brand, Category, Product, ProductManual, Supplier, Tag


async def _create_product_graph(db):
    brand = Brand(brand_name=f"brand-{uuid4().hex[:8]}")
    category = Category(category_name=f"category-{uuid4().hex[:8]}", level=1, sort=0)
    supplier = Supplier(
        supplier_name=f"supplier-{uuid4().hex[:8]}",
        cooperation_status="active",
    )
    tag_a = Tag(tag_name=f"tag-{uuid4().hex[:4]}")
    tag_b = Tag(tag_name=f"tag-{uuid4().hex[:4]}")
    product = Product(
        product_no=f"P-{uuid4().hex[:8]}",
        product_name="测试办公椅",
        brand=brand,
        supplier=supplier,
        category=category,
        face_price=1999,
        cost_price=888,
        material="网布",
        stock_status="unknown",
        status="active",
        description="适用于标准办公位。",
        specification="680x680x980mm",
        colors="黑色/灰色",
        completeness_status="complete",
        tags=[tag_b, tag_a],
    )
    db.add_all([brand, category, supplier, tag_a, tag_b, product])
    await db.flush()
    return product


async def _create_manual(db, product: Product, *, parsed_content: str | None = None):
    attachment = Attachment(
        file_name=f"manual-{uuid4().hex[:8]}.pdf",
        file_url="https://example.invalid/manual.pdf",
        file_type="pdf",
        file_size=1234,
        storage_type="minio",
        oss_key=f"manuals/{uuid4().hex}.pdf",
    )
    manual = ProductManual(
        product_id=product.id,
        attachment=attachment,
        doc_type="manual",
        parsed_content=parsed_content,
        parse_status="parsed" if parsed_content else "pending",
        index_status="indexed" if parsed_content else "pending",
    )
    db.add_all([attachment, manual])
    await db.flush()
    return manual


@pytest.mark.anyio
async def test_product_card_provider_excludes_sensitive_fields(db, integration_setup_db):
    product = await _create_product_graph(db)
    payload = await DatabaseProductFactProvider(db).build_product_card(product.id)

    assert payload.source_type == "product_card"
    assert payload.product_id == product.id
    assert len(payload.chunks) == 1
    text = payload.chunks[0].chunk_text
    assert "产品名称: 测试办公椅" in text
    assert "产品编号:" in text
    assert "网布" in text
    assert "680x680x980mm" in text
    assert "1999" not in text
    assert "888" not in text
    assert "supplier" not in text.lower()
    assert "unknown" not in text.lower()


async def _add_shape_attribute(db, product: Product):
    attribute_code = f"test_shape_{uuid4().hex}"
    definition = CatalogAttributeDefinition(
        code=attribute_code,
        name="桌形",
        data_type="option",
        multi_value=False,
        searchable=True,
        hard_filterable=True,
        enabled=True,
        sort_order=10,
        is_deleted=False,
    )
    option = CatalogAttributeOption(
        definition=definition,
        code="arc",
        label="弧形",
        enabled=True,
        sort_order=0,
        is_deleted=False,
    )
    db.add_all(
        [
            definition,
            ProductAttributeValue(
                product_id=product.id,
                definition=definition,
                option=option,
                source="manual",
                verified=True,
                is_deleted=False,
            ),
        ]
    )
    await db.commit()
    return attribute_code


@pytest.mark.anyio
async def test_product_search_serializes_attributes_with_async_postgres(
    db, _sessionmaker, integration_setup_db
):
    product = await _create_product_graph(db)
    product.product_name = "弧形会议桌"
    product.description = "异步召回校验"
    await db.flush()
    product_id = product.id
    attribute_code = await _add_shape_attribute(db, product)

    # A new session ensures no relationships from fixture construction can hide lazy loads.
    async with _sessionmaker() as search_db:
        context = ToolContext(
            db=search_db,
            current_user={"sub": "integration-test"},
            permission_pool=None,
            trace_id="product-attribute-search-test",
        )
        result = await ProductSearchTool().run(
            ProductSearchInput(
                product_ids=[product_id],
                hard_facets=[{"attribute_code": attribute_code, "values": ["arc"]}],
            ),
            context,
        )

    assert len(result["products"]) == 1
    assert result["products"][0]["attributes"][attribute_code][0]["label"] == "弧形"
    assert result["products"][0]["attributes"][attribute_code][0]["option_code"] == "arc"
    assert result["products"][0]["matched_facets"] == [attribute_code]

    # Text-recall products are serialized through _product_card as well.
    async with _sessionmaker() as search_db:
        context = ToolContext(
            db=search_db,
            current_user={"sub": "integration-test"},
            permission_pool=None,
            trace_id="product-attribute-text-recall-test",
        )
        text_result = await ProductSearchTool().run(
            ProductSearchInput(
                product_ids=[uuid4()],
                soft_terms=["异步召回校验"],
            ),
            context,
        )
    assert text_result["text_candidates"][0]["id"] == str(product_id)


@pytest.mark.anyio
async def test_product_card_provider_loads_attributes_with_async_postgres(
    db, _sessionmaker, integration_setup_db
):
    product = await _create_product_graph(db)
    product_id = product.id
    await _add_shape_attribute(db, product)

    # Re-query from a clean identity map to exercise selectin eager loading.
    async with _sessionmaker() as card_db:
        payload = await DatabaseProductFactProvider(card_db).build_product_card(product_id)

    assert "attributes" in payload.metadata["fact_keys"]
    assert "属性: 桌形: 弧形" in payload.chunks[0].chunk_text


@pytest.mark.anyio
async def test_product_card_upsert_is_idempotent_and_soft_deletes_replaced_chunks(
    db,
    integration_setup_db,
):
    product = await _create_product_graph(db)

    first = await upsert_product_card(db, product.id)
    await db.commit()
    second = await upsert_product_card(db, product.id)
    await db.commit()

    assert first.id == second.id
    doc_count = await db.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(
            KnowledgeDocument.source_type == "product_card",
            KnowledgeDocument.source_id == product.id,
        )
    )
    assert doc_count == 1

    result = await db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == first.id)
    )
    chunks = result.scalars().all()
    assert len(chunks) == 1
    assert chunks[0].is_deleted is False

    product.description = "适用于标准办公位和会议室。"
    await db.flush()
    third = await upsert_product_card(db, product.id)
    await db.commit()

    assert third.id == first.id
    result = await db.execute(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == first.id)
        .order_by(KnowledgeChunk.create_time.asc())
    )
    chunks = result.scalars().all()
    assert len(chunks) == 2
    assert sum(1 for chunk in chunks if not chunk.is_deleted) == 1
    assert sum(1 for chunk in chunks if chunk.is_deleted) == 1


@pytest.mark.anyio
async def test_manual_backfill_prefers_legacy_chunks(db, integration_setup_db):
    product = await _create_product_graph(db)
    manual = await _create_manual(db, product, parsed_content="这是完整正文")
    legacy_chunk = ProductManualChunk(
        product_manual_id=manual.id,
        product_id=product.id,
        chunk_index=0,
        chunk_text="章节一：安装步骤",
        chunk_tokens=8,
        chunk_hash="legacyhash1",
    )
    db.add(legacy_chunk)
    await db.flush()

    document = await backfill_product_manual(db, manual.id)
    await db.commit()

    assert document.source_type == "product_manual"
    assert document.source_id == manual.id
    result = await db.execute(
        select(KnowledgeChunk).where(
            KnowledgeChunk.document_id == document.id,
            KnowledgeChunk.is_deleted.is_(False),
        )
    )
    chunks = result.scalars().all()
    assert len(chunks) == 1
    assert chunks[0].chunk_text == "章节一：安装步骤"
    assert chunks[0].metadata_json["legacy_manual_chunk_id"] == str(legacy_chunk.id)


@pytest.mark.anyio
async def test_manual_backfill_falls_back_to_parsed_content(db, integration_setup_db):
    product = await _create_product_graph(db)
    manual = await _create_manual(db, product, parsed_content="手册正文")

    document = await backfill_product_manual(db, manual.id)
    await db.commit()

    result = await db.execute(
        select(KnowledgeChunk).where(
            KnowledgeChunk.document_id == document.id,
            KnowledgeChunk.is_deleted.is_(False),
        )
    )
    chunk = result.scalar_one()
    assert chunk.chunk_text == "手册正文"
    assert chunk.metadata_json["backfill_mode"] == "parsed_content"


@pytest.mark.anyio
async def test_manual_backfill_rejects_missing_body(db, integration_setup_db):
    product = await _create_product_graph(db)
    manual = await _create_manual(db, product, parsed_content=None)

    with pytest.raises(ValueError, match="has no parsed content"):
        await backfill_product_manual(db, manual.id)
