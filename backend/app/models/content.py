"""新媒体内容工坊模型（HLD §4.11 / §4.12）。

对应迁移 0021（content_batches / content_items / content_publications /
content_metric_snapshots）。item.status 仅 draft/adopted/rejected/produced/
published（裁决 R7：tracking/closed 为派生展示态，不落状态列）。
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
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

from app.models.base import CommonBase


class ContentBatch(CommonBase):
    __tablename__ = "content_batches"

    title = Column(String(255), nullable=False)
    customer_id = Column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    product_ids = Column(JSONB, nullable=False, default=list)
    topic = Column(Text, nullable=False)
    platform = Column(String(32), nullable=False)
    tone = Column(String(32), nullable=True)  # 种草/测评/干货/故事
    requested_count = Column(Integer, nullable=False, default=3)
    status = Column(String(16), nullable=False, default="running")
    error_msg = Column(Text, nullable=True)
    model_provider = Column(String(32), nullable=True)
    model_name = Column(String(64), nullable=True)
    prompt_version = Column(String(16), nullable=False, default="v1")
    latency_ms = Column(Integer, nullable=True)
    # Track B：生成批次使用的 Skill（可为空 = 默认模板）
    source_skill_code = Column(String(64), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "platform IN ('xhs','douyin','moments','seo','other')",
            name="ck_cb_platform",
        ),
        CheckConstraint(
            "status IN ('pending','running','done','failed')",
            name="ck_cb_status",
        ),
        CheckConstraint(
            "requested_count BETWEEN 1 AND 5",
            name="ck_cb_count",
        ),
        Index(
            "ix_cb_created",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class ContentItem(CommonBase):
    __tablename__ = "content_items"

    batch_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("content_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_type = Column(String(16), nullable=False, default="copy")
    platform = Column(String(32), nullable=False)
    title = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    hashtags = Column(JSONB, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="draft")
    adopted_by = Column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    adopted_at = Column(DateTime(timezone=True), nullable=True)
    rejected_reason = Column(String(255), nullable=True)
    produced_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)  # 派生 close 首次满足时的展示缓存
    edited = Column(Boolean, nullable=False, default=False)
    verified_payload = Column(JSONB, nullable=True)
    warnings = Column(JSONB, nullable=False, default=list)  # 合规/事实守卫命中项（§9.3）
    verification_gaps = Column(JSONB, nullable=False, default=list)
    external_ref = Column(String(128), nullable=True)
    model_provider = Column(String(32), nullable=True)
    model_name = Column(String(64), nullable=True)
    generation_version = Column(String(16), nullable=False, default="v1")
    # Track B：内容条目使用的 Skill（可为空 = 默认模板）
    source_skill_code = Column(String(64), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "item_type IN ('copy','video_script')",
            name="ck_ci_type",
        ),
        CheckConstraint(
            "status IN ('draft','adopted','rejected','produced','published')",
            name="ck_ci_status",
        ),
        CheckConstraint(
            "char_length(body) <= 20000",
            name="ck_ci_len",
        ),
        Index(
            "ix_ci_batch",
            "batch_id",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_ci_status",
            "status",
            "create_time",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class ContentPublication(CommonBase):
    __tablename__ = "content_publications"

    content_item_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    platform = Column(String(32), nullable=False)
    account_name = Column(String(128), nullable=True)
    publish_url = Column(String(1024), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    video_attachment_id = Column(
        PGUUID(as_uuid=True), ForeignKey("attachment.id", ondelete="SET NULL"), nullable=True
    )
    external_ref = Column(String(128), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        Index(
            "uq_pub_item_url",
            "content_item_id",
            "publish_url",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_pub_published",
            "published_at",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class ContentMetricSnapshot(CommonBase):
    """曝光快照（累计值；同日重复录入按 uq_cms_pub_date upsert，§4.12）。"""

    __tablename__ = "content_metric_snapshots"

    publication_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("content_publications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    views = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    shares = Column(Integer, nullable=True)
    favorites = Column(Integer, nullable=True)
    leads = Column(Integer, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    captured_date = Column(Date, nullable=False)  # 服务层按 Asia/Shanghai 取日期
    source = Column(String(8), nullable=False, default="manual")
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source IN ('manual','import')",
            name="ck_cms_source",
        ),
        CheckConstraint(
            "coalesce(views,0)>=0 AND coalesce(likes,0)>=0 AND coalesce(comments,0)>=0 "
            "AND coalesce(shares,0)>=0 AND coalesce(favorites,0)>=0 AND coalesce(leads,0)>=0",
            name="ck_cms_nonneg",
        ),
        Index(
            "uq_cms_pub_date",
            "publication_id",
            "captured_date",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_cms_pub_time",
            "publication_id",
            "captured_at",
            postgresql_where=text("is_deleted = false"),
        ),
    )
