from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from app.core.database import Vector
from app.models.base import CommonBase


class Category(CommonBase):
    __tablename__ = "category"

    parent_id = Column(PGUUID(as_uuid=True), ForeignKey("category.id"))
    level = Column(Integer, nullable=False)
    category_name = Column(String(128), nullable=False)
    sort = Column(Integer, nullable=False, default=0)

    parent = relationship(
        "Category",
        primaryjoin="Category.parent_id == Category.id",
        remote_side="Category.id",
        backref="children",
    )


class Brand(CommonBase):
    __tablename__ = "brand"

    brand_name = Column(String(128), nullable=False, unique=True)
    logo_url = Column(String(512))
    description = Column(Text)


class Supplier(CommonBase):
    __tablename__ = "supplier"

    supplier_name = Column(String(128), nullable=False, unique=True)
    contact = Column(String(64))
    phone = Column(String(20))
    cooperation_status = Column(String(20), default="active")

    __table_args__ = (
        CheckConstraint(
            "cooperation_status IN ('active', 'suspended', 'terminated')",
            name="check_supplier_cooperation_status",
        ),
    )


class Tag(CommonBase):
    __tablename__ = "tag"

    tag_name = Column(String(64), nullable=False)
    tag_type = Column(String(32))


class Product(CommonBase):
    __tablename__ = "product"

    product_no = Column(String(64), nullable=False)
    product_name = Column(String(255), nullable=False)
    brand_id = Column(PGUUID(as_uuid=True), ForeignKey("brand.id"), nullable=False)
    supplier_id = Column(PGUUID(as_uuid=True), ForeignKey("supplier.id"), nullable=False)
    category_id = Column(PGUUID(as_uuid=True), ForeignKey("category.id"), nullable=False)
    face_price = Column(Float, nullable=False)
    cost_price = Column(Float)
    material = Column(String(128))
    stock_status = Column(String(20), default="in_stock")
    status = Column(String(20), default="draft")
    description = Column(Text)
    specification = Column(String(255))
    colors = Column(Text)
    data_source = Column(String(512))
    completeness_status = Column(String(20), nullable=False, default="complete")
    vector = Column(Vector(1536), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'draft')", name="check_product_status"
        ),
        CheckConstraint(
            "stock_status IN ('in_stock', 'out_of_stock', 'preorder', 'unknown')",
            name="check_product_stock_status",
        ),
        CheckConstraint(
            "completeness_status IN ('complete', 'pending', 'unknown')",
            name="check_product_completeness_status",
        ),
        CheckConstraint(
            "face_price <> 99999 OR completeness_status = 'pending'",
            name="check_product_placeholder_price",
        ),
        # 软删除语义：仅对未删除行保证 product_no 唯一，删除后编号可被复用。
        Index(
            "idx_product_no_active",
            "product_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    brand = relationship("Brand")
    supplier = relationship("Supplier")
    category = relationship("Category")
    tags = relationship("Tag", secondary="product_tag", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    manuals = relationship("ProductManual", back_populates="product", cascade="all, delete-orphan")
    chunks = relationship(
        "ProductManualChunk",
        back_populates="product",
        cascade="all, delete-orphan",
        primaryjoin="ProductManualChunk.product_id==Product.id",
    )


class ProductTag(CommonBase):
    __tablename__ = "product_tag"

    product_id = Column(
        PGUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    tag_id = Column(PGUUID(as_uuid=True), ForeignKey("tag.id"), nullable=False)


Tag.products = relationship("Product", secondary="product_tag", back_populates="tags")


class Attachment(CommonBase):
    __tablename__ = "attachment"

    file_name = Column(String(255), nullable=False)
    file_url = Column(String(512), nullable=False)
    file_type = Column(String(32), nullable=False)
    file_size = Column(Integer, nullable=False)
    storage_type = Column(String(20), default="minio")
    oss_key = Column(String(512), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "file_type IN ('image', 'video', 'pdf', 'doc', 'other')",
            name="check_attachment_file_type",
        ),
    )


class ProductImage(CommonBase):
    __tablename__ = "product_image"

    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    attachment_id = Column(PGUUID(as_uuid=True), ForeignKey("attachment.id"), nullable=False)
    sort = Column(Integer, default=0)
    is_cover = Column(Boolean, default=False)

    product = relationship("Product", back_populates="images")
    attachment = relationship("Attachment")


class ProductManual(CommonBase):
    __tablename__ = "product_manual"

    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    attachment_id = Column(PGUUID(as_uuid=True), ForeignKey("attachment.id"), nullable=False)
    doc_type = Column(String(32), nullable=False)
    parsed_content = Column(Text)
    parse_status = Column(String(20), nullable=False, default="pending")
    parse_error = Column(Text, nullable=True)
    parser_name = Column(String(64), nullable=True)
    parser_version = Column(String(32), nullable=True)
    page_count = Column(Integer, nullable=True)
    index_status = Column(String(20), nullable=False, default="pending")
    index_error = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('manual', 'spec', 'datasheet', 'certificate', 'other')",
            name="check_product_manual_doc_type",
        ),
        CheckConstraint(
            "index_status IN ('pending', 'processing', 'indexed', 'failed')",
            name="check_product_manual_index_status",
        ),
        CheckConstraint(
            "parse_status IN ('pending', 'processing', 'parsed', 'failed', 'ocr_required')",
            name="check_product_manual_parse_status",
        ),
    )

    product = relationship("Product", back_populates="manuals")
    attachment = relationship("Attachment")
    chunks = relationship(
        "ProductManualChunk",
        back_populates="manual",
        cascade="all, delete-orphan",
    )
