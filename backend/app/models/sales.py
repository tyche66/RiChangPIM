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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import CommonBase


class ProjectSpace(CommonBase):
    """项目空间节点（Track C）：楼层 / 房间 / 区域。

    空间必须属于某个项目；没有选择项目时不可选择项目空间。
    """

    __tablename__ = "project_spaces"

    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    parent_id = Column(
        PGUUID(as_uuid=True), ForeignKey("project_spaces.id", ondelete="CASCADE"), nullable=True
    )
    space_type = Column(String(16), nullable=False, default="other")
    space_name = Column(String(128), nullable=False)
    level = Column(Integer, nullable=False, default=1)
    sort = Column(Integer, nullable=False, default=0)

    project = relationship("Project")
    parent = relationship("ProjectSpace", remote_side="ProjectSpace.id", backref="children")

    __table_args__ = (
        CheckConstraint("space_type IN ('floor','room','zone','other')", name="ck_ps_type"),
        CheckConstraint("level >= 1", name="ck_ps_level"),
        Index(
            "ix_ps_project",
            "project_id",
            "sort",
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_ps_parent", "parent_id", postgresql_where=text("is_deleted = false")),
    )


class Proposal(CommonBase):
    __tablename__ = "proposal"

    proposal_no = Column(String(64), nullable=False, unique=True)
    proposal_name = Column(String(255), nullable=False)
    creator_id = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    customer_name = Column(String(128))
    customer_id = Column(PGUUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    project_id = Column(PGUUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    status = Column(String(20), default="draft")
    ai_polished = Column(Boolean, default=False)
    total_face_value = Column(Float, default=0)

    ai_polish_content = Column(Text, nullable=True)
    ai_polish_at = Column(DateTime(timezone=True), nullable=True)
    ai_polish_model = Column(String(64), nullable=True)
    ai_generation_version = Column(String(32), nullable=True)
    ai_source_ids = Column(JSONB, nullable=True)
    ai_confirmed_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    creator = relationship("User", foreign_keys=[creator_id])
    ai_confirmer = relationship("User", foreign_keys=[ai_confirmed_by])
    items = relationship("ProposalItem", back_populates="proposal", cascade="all, delete-orphan")


class ProposalItem(CommonBase):
    __tablename__ = "proposal_item"

    proposal_id = Column(
        PGUUID(as_uuid=True), ForeignKey("proposal.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    sort = Column(Integer, default=0)
    remark = Column(Text)
    # Track C：与报价明细同构的空间字段与产品快照（可空，旧方案无需回填）
    project_space_id = Column(
        PGUUID(as_uuid=True), ForeignKey("project_spaces.id", ondelete="SET NULL"), nullable=True
    )
    floor_label = Column(String(128), nullable=True)
    space_label = Column(String(128), nullable=True)
    material_desc = Column(Text, nullable=True)
    product_snapshot = Column(JSONB, nullable=True)

    proposal = relationship("Proposal", back_populates="items")
    product = relationship("Product")
    space = relationship("ProjectSpace")


class ProposalFloorPlan(CommonBase):
    """方案平面图（Track D）：媒体库附件与方案的绑定关系。

    图片本身只存在媒体库（MinIO + attachment 行），本表只负责「属于哪个方案 /
    哪个项目、以什么名字展示、排第几」。删除本行即解除绑定，附件仍留在媒体库。

    楼层/空间名是冗余快照而不是外键：与 proposal_item 的 floor_label /
    space_label 同口径，项目空间树改名不会让已分享的平面图标题漂移。
    """

    __tablename__ = "proposal_floor_plan"

    proposal_id = Column(
        PGUUID(as_uuid=True), ForeignKey("proposal.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # 方案不强制关联项目，project_id 可空；绑定媒体库附件则不可为空且不可硬删
    attachment_id = Column(
        PGUUID(as_uuid=True), ForeignKey("attachment.id", ondelete="RESTRICT"), nullable=False
    )
    name = Column(String(128), nullable=False)
    floor_label = Column(String(128), nullable=True)
    space_label = Column(String(128), nullable=True)
    sort = Column(Integer, nullable=False, default=0)

    proposal = relationship("Proposal", backref="floor_plans")
    attachment = relationship("Attachment")

    __table_args__ = (
        CheckConstraint("char_length(name) > 0", name="ck_pfp_name"),
        Index(
            "ix_pfp_proposal",
            "proposal_id",
            "sort",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_pfp_project",
            "project_id",
            postgresql_where=text("is_deleted = false AND project_id IS NOT NULL"),
        ),
        Index(
            "ix_pfp_attachment",
            "attachment_id",
            postgresql_where=text("is_deleted = false"),
        ),
        # 同一方案不得重复绑定同一个附件；软删除后可重新绑定
        Index(
            "uq_pfp_proposal_attachment",
            "proposal_id",
            "attachment_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )


class Quotation(CommonBase):
    __tablename__ = "quotation"

    quotation_no = Column(String(64), nullable=False, unique=True)
    proposal_id = Column(PGUUID(as_uuid=True), ForeignKey("proposal.id"), nullable=False)
    creator_id = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    valid_until = Column(DateTime(timezone=True))
    total_amount = Column(Float, default=0)
    subtotal = Column(Float, default=0)
    tax_rate = Column(Float, default=0.13)
    discount = Column(Float, default=1.0)
    status = Column(String(20), default="draft")

    proposal = relationship("Proposal")
    creator = relationship("User")
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan")


class QuotationItem(CommonBase):
    __tablename__ = "quotation_item"

    quotation_id = Column(
        PGUUID(as_uuid=True), ForeignKey("quotation.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    tax_rate = Column(Float, default=0.13)
    subtotal = Column(Float, nullable=False)
    # Track C：与方案明细同构的空间字段与产品快照（可空，旧报价无需回填）
    project_space_id = Column(
        PGUUID(as_uuid=True), ForeignKey("project_spaces.id", ondelete="SET NULL"), nullable=True
    )
    floor_label = Column(String(128), nullable=True)
    space_label = Column(String(128), nullable=True)
    material_desc = Column(Text, nullable=True)
    product_snapshot = Column(JSONB, nullable=True)

    quotation = relationship("Quotation", back_populates="items")
    product = relationship("Product")
    space = relationship("ProjectSpace")
