"""内容 Skill 与独立选题模型（Track B）。

* ``content_skills`` —— Skill 定义（topic 选题 / content 内容生成）。
* ``content_topic_runs`` / ``content_topic_items`` —— 独立选题模块。

启用开关语义：只有 ``enabled=true`` 且未软删的 Skill 才允许被选用；
后端在每个写入口重新校验，绝不信任前端传来的开关状态。
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import CommonBase


class ContentSkill(CommonBase):
    __tablename__ = "content_skills"

    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    skill_type = Column(String(16), nullable=False, default="content")
    description = Column(Text, nullable=True)
    # UI-facing DNA source. Legacy rows may remain NULL for compatibility.
    source_dna = Column(String(32), nullable=True)
    prompt_template = Column(Text, nullable=True)
    output_schema = Column(JSONB, nullable=True)
    prompt_version = Column(String(16), nullable=False, default="v1")
    supported_platforms = Column(JSONB, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("skill_type IN ('topic','content')", name="ck_cs_type"),
        Index("uq_cs_code", "code", unique=True, postgresql_where=text("is_deleted = false")),
        Index(
            "ix_cs_type_enabled",
            "skill_type",
            "enabled",
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_cs_sort", "sort_order", postgresql_where=text("is_deleted = false")),
    )


class ContentTopicRun(CommonBase):
    __tablename__ = "content_topic_runs"

    skill_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("content_skills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    skill_code = Column(String(64), nullable=False)
    topic = Column(Text, nullable=False)
    platform = Column(String(32), nullable=True)
    tone = Column(String(32), nullable=True)
    product_ids = Column(JSONB, nullable=False, default=list)
    requested_count = Column(Integer, nullable=False, default=3)
    status = Column(String(16), nullable=False, default="running")
    error_msg = Column(Text, nullable=True)
    model_provider = Column(String(32), nullable=True)
    model_name = Column(String(64), nullable=True)
    prompt_version = Column(String(16), nullable=False, default="v1")
    latency_ms = Column(Integer, nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending','running','done','failed')", name="ck_ctr_status"),
        CheckConstraint("requested_count BETWEEN 1 AND 10", name="ck_ctr_count"),
        Index("ix_ctr_created", "create_time", postgresql_where=text("is_deleted = false")),
        Index("ix_ctr_skill", "skill_id", postgresql_where=text("is_deleted = false")),
    )


class ContentTopicItem(CommonBase):
    __tablename__ = "content_topic_items"

    run_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("content_topic_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title = Column(String(255), nullable=False)
    angle = Column(Text, nullable=True)
    audience = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    suggested_platform = Column(String(32), nullable=True)
    related_product_ids = Column(JSONB, nullable=False, default=list)
    pillar_code = Column(String(1), nullable=True)
    verification_gaps = Column(JSONB, nullable=False, default=list)
    source_skill_code = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="draft")
    adopted_by = Column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    adopted_at = Column(DateTime(timezone=True), nullable=True)
    rejected_reason = Column(String(255), nullable=True)
    content_batch_id = Column(
        PGUUID(as_uuid=True), ForeignKey("content_batches.id", ondelete="SET NULL"), nullable=True
    )
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('draft','adopted','rejected','used')", name="ck_cti_status"),
        Index("ix_cti_run", "run_id", postgresql_where=text("is_deleted = false")),
        Index(
            "ix_cti_status",
            "status",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
    )
