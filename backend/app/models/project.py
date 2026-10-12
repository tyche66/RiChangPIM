"""项目域模型（HLD §4.2 / §4.3 / §4.7）。

对应迁移 0018（projects / project_members）与 0019（project_assets）。
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.models.base import CommonBase


class Project(CommonBase):
    __tablename__ = "projects"

    customer_id = Column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    code = Column(String(32), nullable=True)  # 项目编号（可选）
    name = Column(String(255), nullable=False)
    project_type = Column(String(32), nullable=False, default="other")
    stage = Column(String(20), nullable=False, default="lead")
    status = Column(String(20), nullable=False, default="active")
    budget = Column(Float, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    customer = relationship("Customer", back_populates="projects")
    members = relationship("ProjectMember", back_populates="project")

    __table_args__ = (
        CheckConstraint(
            "stage IN ('lead','measuring','design','quoted','producing',"
            "'delivered','closed','cancelled')",
            name="ck_projects_stage",
        ),
        CheckConstraint(
            "status IN ('active','paused','done','cancelled')",
            name="ck_projects_status",
        ),
        CheckConstraint(
            "start_date IS NULL OR end_date IS NULL OR start_date <= end_date",
            name="ck_projects_dates",
        ),
        Index(
            "ix_projects_customer",
            "customer_id",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_projects_stage",
            "stage",
            "status",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_projects_activity",
            "last_activity_at",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_projects_code",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false AND code IS NOT NULL"),
        ),
    )


class ProjectMember(CommonBase):
    __tablename__ = "project_members"

    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    member_role = Column(String(20), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    project = relationship("Project", back_populates="members")

    __table_args__ = (
        CheckConstraint(
            "member_role IN ('sales','designer','pm','other')",
            name="ck_pm_role",
        ),
        Index(
            "uq_pm_project_user_role",
            "project_id",
            "user_id",
            "member_role",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_pm_primary",
            "project_id",
            "member_role",
            unique=True,
            postgresql_where=text("is_deleted = false AND is_primary = true"),
        ),
        Index(
            "ix_pm_user",
            "user_id",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class ProjectAsset(CommonBase):
    """图纸/设计稿版本（§4.7）。升版规则由服务层实现。"""

    __tablename__ = "project_assets"

    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    category = Column(String(20), nullable=False, default="other")
    name = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="draft")
    attachment_id = Column(
        PGUUID(as_uuid=True), ForeignKey("attachment.id", ondelete="RESTRICT"), nullable=False
    )
    remark = Column(Text, nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    project = relationship("Project")

    __table_args__ = (
        CheckConstraint(
            "category IN ('design_drawing','drawing','render','contract','photo','other')",
            name="ck_pa_category",
        ),
        CheckConstraint(
            "status IN ('draft','shared','approved','obsolete')",
            name="ck_pa_status",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_pa_version",
        ),
        Index(
            "uq_pa_pcnv",
            "project_id",
            "category",
            "name",
            "version",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_pa_current",
            "project_id",
            "category",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false AND is_current = true"),
        ),
        Index(
            "ix_pa_project",
            "project_id",
            postgresql_where=text("is_deleted = false"),
        ),
    )
