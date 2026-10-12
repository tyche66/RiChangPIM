"""客户域模型（HLD §4.1 / §4.4 / §4.5 / §4.6）。

对应迁移 0018（customers）与 0019（dialogues/requirements/follow_ups）。
所有新表继承 CommonBase（id/create_time/update_time/deleted_at/is_deleted），
另加 created_by/updated_by（§4.0）；外键一律 ON DELETE RESTRICT（软删体系）。
"""

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import CommonBase


class Customer(CommonBase):
    __tablename__ = "customers"

    name = Column(String(128), nullable=False)
    customer_no = Column(String(32), nullable=True)  # C+年+序号，服务层生成
    source = Column(String(32), nullable=False, default="other")
    level = Column(String(16), nullable=True)
    stage = Column(String(20), nullable=False, default="lead")
    owner_sales_id = Column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    phone = Column(String(64), nullable=True)  # PII（D3'：明文列，序列化脱敏）
    phone_norm = Column(String(32), nullable=True)  # 仅数字；查重/检索用；不出现在任何响应
    wechat = Column(String(128), nullable=True)  # PII
    address = Column(Text, nullable=True)  # PII
    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True)
    style_preference = Column(Text, nullable=True)
    remark = Column(Text, nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    projects = relationship("Project", back_populates="customer")

    __table_args__ = (
        CheckConstraint(
            "stage IN ('lead','contacted','needs','quoted','won','lost')",
            name="ck_customers_stage",
        ),
        CheckConstraint(
            "level IS NULL OR level IN ('A','B','C')",
            name="ck_customers_level",
        ),
        CheckConstraint(
            "source IN ('new_media','store','referral','exhibition','other')",
            name="ck_customers_source",
        ),
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
            name="ck_customers_budget",
        ),
        Index(
            "ix_customers_owner_stage",
            "owner_sales_id",
            "stage",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_customers_create_time",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_customers_phone_norm",
            "phone_norm",
            postgresql_where=text("is_deleted = false AND phone_norm IS NOT NULL"),
        ),
        Index(
            "ix_customers_activity",
            "last_activity_at",
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_customers_name", "name"),
        Index(
            "uq_customers_no",
            "customer_no",
            unique=True,
            postgresql_where=text("is_deleted = false AND customer_no IS NOT NULL"),
        ),
    )


class CustomerDialogue(CommonBase):
    __tablename__ = "customer_dialogues"

    customer_id = Column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    channel = Column(String(32), nullable=False, default="wechat")
    direction = Column(String(8), nullable=False, default="in")
    content = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "channel IN ('wechat','phone','visit','sms','other')",
            name="ck_dlg_channel",
        ),
        CheckConstraint(
            "direction IN ('in','out')",
            name="ck_dlg_direction",
        ),
        CheckConstraint(
            "char_length(content) <= 20000",
            name="ck_dlg_len",
        ),
        Index(
            "ix_dlg_customer_time",
            "customer_id",
            "occurred_at",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class CustomerDialogueAttachment(CommonBase):
    """对话 ↔ 附件 junction（§4.4，取代 v1 的 attachment_ids JSONB）。"""

    __tablename__ = "customer_dialogue_attachments"

    dialogue_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_dialogues.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attachment_id = Column(
        PGUUID(as_uuid=True), ForeignKey("attachment.id", ondelete="RESTRICT"), nullable=False
    )
    sort_no = Column(Integer, nullable=False, default=0)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        Index(
            "uq_dlg_att",
            "dialogue_id",
            "attachment_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )


class Requirement(CommonBase):
    __tablename__ = "requirements"

    customer_id = Column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    content = Column(Text, nullable=False)
    structured = Column(JSONB, nullable=True)
    source = Column(String(16), nullable=False, default="manual")
    confirmed = Column(Boolean, nullable=False, default=True)
    source_action_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("pending_action.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source IN ('manual','ai_extracted')",
            name="ck_req_source",
        ),
        Index(
            "ix_req_customer",
            "customer_id",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class FollowUp(CommonBase):
    __tablename__ = "follow_ups"

    customer_id = Column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    follower_id = Column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    method = Column(String(32), nullable=False, default="wechat")
    content = Column(Text, nullable=False)
    result = Column(String(32), nullable=True)
    next_follow_at = Column(DateTime(timezone=True), nullable=True)
    done_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    customer = relationship("Customer")

    __table_args__ = (
        CheckConstraint(
            "result IS NULL OR result IN ('connected','no_answer',"
            "'interested','rejected','scheduled','other')",
            name="ck_fu_result",
        ),
        Index(
            "ix_fu_customer_time",
            "customer_id",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_fu_follower_time",
            "follower_id",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_fu_next_pending",
            "next_follow_at",
            postgresql_where=text(
                "is_deleted = false AND done_at IS NULL AND next_follow_at IS NOT NULL"
            ),
        ),
    )


class EntityStageLog(CommonBase):
    """阶段变更日志（§5.1 / §5.2）。

    记录 customer/project 的状态迁移，含操作人、前后阶段、原因。
    """

    __tablename__ = 'entity_stage_logs'

    entity_type = Column(String(16), nullable=False)  # customer | project
    entity_id = Column(PGUUID(as_uuid=True), nullable=False)
    from_stage = Column(String(20), nullable=False)
    to_stage = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    operator_id = Column(
        PGUUID(as_uuid=True), ForeignKey('user.id', ondelete='RESTRICT'), nullable=True
    )
    created_by = Column(PGUUID(as_uuid=True), ForeignKey('user.id'), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey('user.id'), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('customer','project')",
            name='ck_esl_entity_type',
        ),
        Index(
            'ix_esl_entity',
            'entity_type',
            'entity_id',
            'create_time',
            postgresql_where=text('is_deleted = false'),
        ),
    )
