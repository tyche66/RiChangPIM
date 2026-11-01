from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, String, Text

from app.models.base import CommonBase


class Announcement(CommonBase):
    """后台公告（FR-4）。

    受众与级别由 CheckConstraint 兜底；已读状态只存浏览器 localStorage，
    服务端不建已读表。删除为软删除，管理列表可追溯。
    """

    __tablename__ = "announcement"

    title = Column(String(200), nullable=False)
    content_md = Column(Text, nullable=False)
    # admin=仅后台 / portal=仅门户 / all=两端
    audience = Column(String(20), nullable=False, default="all")
    # info=普通 / important=重要
    level = Column(String(20), nullable=False, default="info")
    enabled = Column(Boolean, nullable=False, default=True)
    # 空 = 立即发布；expire_at 空 = 不过期
    publish_at = Column(DateTime(timezone=True), nullable=True)
    expire_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "audience IN ('admin', 'portal', 'all')",
            name="check_announcement_audience",
        ),
        CheckConstraint(
            "level IN ('info', 'important')",
            name="check_announcement_level",
        ),
        Index("idx_announcement_audience_enabled", "audience", "enabled"),
    )
