"""受治理的产品属性模型（Track A：通用产品属性检索）。

设计目标：把"桌形/风格/材质/颜色/系列/规格数值"等从普通 Tag 与自由文本中
剥出来，成为可治理、可检索、可回溯的属性体系，而不是给某个 SKU 堆特例。

四张表：

* ``catalog_attribute_definition`` —— 属性定义（code 唯一，带数据类型与
  可检索/可硬过滤开关）。
* ``catalog_attribute_option`` —— 枚举型属性的取值（code/label）。
* ``catalog_attribute_alias`` —— 取值的同义词（中文无空格、异形字、口语说法）。
* ``product_attribute_value`` —— 产品 × 属性 的取值，支持 option / text /
  number 三种形态，并记录来源、是否人工确认与置信度。

``category`` 仍然复用现有 Category 树，不在这里重复建产品分类表。
"""


from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import CommonBase


class CatalogAttributeDefinition(CommonBase):
    __tablename__ = "catalog_attribute_definition"

    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    data_type = Column(String(16), nullable=False, default="option")
    multi_value = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    searchable = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    hard_filterable = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    description = Column(Text, nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    options = relationship(
        "CatalogAttributeOption", back_populates="definition", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "data_type IN ('option','text','number','range')", name="ck_cad_type"
        ),
        # code 唯一（软删后也不允许同 code 复活，保证词典稳定）
        Index(
            "uq_cad_code",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_cad_sort", "sort_order", postgresql_where=text("is_deleted = false")),
    )


class CatalogAttributeOption(CommonBase):
    __tablename__ = "catalog_attribute_option"

    attribute_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_attribute_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    code = Column(String(64), nullable=False)
    label = Column(String(128), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    extra = Column(JSONB, nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    definition = relationship("CatalogAttributeDefinition", back_populates="options")
    aliases = relationship(
        "CatalogAttributeAlias", back_populates="option", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "uq_cao_attribute_code",
            "attribute_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_cao_attribute_sort",
            "attribute_id",
            "sort_order",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class CatalogAttributeAlias(CommonBase):
    __tablename__ = "catalog_attribute_alias"

    option_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_attribute_option.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias = Column(String(128), nullable=False)
    normalized_alias = Column(String(128), nullable=False)
    source = Column(String(32), nullable=False, default="manual")
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    option = relationship("CatalogAttributeOption", back_populates="aliases")

    __table_args__ = (
        # 同一属性下同一归一化别名只归属一个 option，避免歧义
        UniqueConstraint("option_id", "normalized_alias", name="uq_caa_option_alias"),
        Index("ix_caa_norm", "normalized_alias"),
        Index(
            "ix_caa_option",
            "option_id",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class ProductAttributeValue(CommonBase):
    __tablename__ = "product_attribute_value"

    product_id = Column(
        PGUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    attribute_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_attribute_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    option_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_attribute_option.id", ondelete="RESTRICT"),
        nullable=True,
    )
    value_text = Column(String(255), nullable=True)
    value_num = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)
    source = Column(String(32), nullable=False, default="manual")
    verified = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    confidence = Column(Float, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    product = relationship("Product", back_populates="attribute_values")
    definition = relationship("CatalogAttributeDefinition")
    option = relationship("CatalogAttributeOption")

    __table_args__ = (
        # 同一产品同一属性同一取值只保留一行（未删除）
        Index(
            "uq_pav_product_option",
            "product_id",
            "attribute_id",
            "option_id",
            unique=True,
            postgresql_where=text("is_deleted = false AND option_id IS NOT NULL"),
        ),
        Index(
            "uq_pav_product_text",
            "product_id",
            "attribute_id",
            "value_text",
            unique=True,
            postgresql_where=text("is_deleted = false AND option_id IS NULL"),
        ),
        Index("ix_pav_product", "product_id", postgresql_where=text("is_deleted = false")),
        Index("ix_pav_attribute", "attribute_id"),
        Index("ix_pav_option", "option_id"),
        Index(
            "ix_pav_number",
            "attribute_id",
            "value_num",
            postgresql_where=text("is_deleted = false AND value_num IS NOT NULL"),
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_pav_confidence",
        ),
        CheckConstraint(
            "source IN ('manual','business_confirmed','import','ai_inferred','migrated')",
            name="ck_pav_source",
        ),
    )
