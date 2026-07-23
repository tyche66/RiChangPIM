"""v11_audit_workflow_ocr

Revision ID: 0008_v11_audit_workflow_ocr
Revises: 0007_add_manual_parse_metadata
Create Date: 2026-07-17
"""

from typing import Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "0008_v11_audit_workflow_ocr"
down_revision: Union[str, None] = "0007_add_manual_parse_metadata"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


PERMISSIONS = [
    ("audit:view", "审计日志查看", "audit", "view", "read"),
    ("user:disable", "用户停用", "user", "disable", "write"),
    ("proposal:confirm", "方案确认", "proposal", "confirm", "write"),
    ("quotation:confirm", "报价确认", "quotation", "confirm", "write"),
]


def upgrade() -> None:
    op.drop_constraint("check_product_manual_parse_status", "product_manual", type_="check")
    op.create_check_constraint(
        "check_product_manual_parse_status",
        "product_manual",
        "parse_status IN ('pending', 'processing', 'parsed', 'failed', 'ocr_required')",
    )

    conn = op.get_bind()
    for perm_code, perm_name, resource, action, perm_type in PERMISSIONS:
        conn.execute(
            sa.text(
                """
                INSERT INTO permission (id, perm_code, perm_name, resource, action, type, is_deleted)
                VALUES (:id, :perm_code, :perm_name, :resource, :action, :type, false)
                ON CONFLICT (perm_code) DO UPDATE
                SET is_deleted = false,
                    perm_name = EXCLUDED.perm_name,
                    resource = EXCLUDED.resource,
                    action = EXCLUDED.action,
                    type = EXCLUDED.type
                """
            ),
            {
                "id": str(uuid4()),
                "perm_code": perm_code,
                "perm_name": perm_name,
                "resource": resource,
                "action": action,
                "type": perm_type,
            },
        )

    rows = conn.execute(
        sa.text(
            """
            SELECT r.id AS role_id, p.id AS permission_id
            FROM role r
            JOIN permission p ON p.perm_code = ANY(:perm_codes) AND p.is_deleted = false
            WHERE r.role_code = 'admin' AND r.is_deleted = false
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id AND rp.is_deleted = false
              )
            """
        ),
        {"perm_codes": [p[0] for p in PERMISSIONS]},
    ).mappings()
    for row in rows:
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permission (id, role_id, permission_id, is_deleted)
                VALUES (:id, :role_id, :permission_id, false)
                """
            ),
            {"id": str(uuid4()), "role_id": row["role_id"], "permission_id": row["permission_id"]},
        )


def downgrade() -> None:
    op.drop_constraint("check_product_manual_parse_status", "product_manual", type_="check")
    op.create_check_constraint(
        "check_product_manual_parse_status",
        "product_manual",
        "parse_status IN ('pending', 'processing', 'parsed', 'failed')",
    )

    conn = op.get_bind()
    perm_codes = [p[0] for p in PERMISSIONS]
    conn.execute(
        sa.text(
            """
            UPDATE role_permission rp
            SET is_deleted = true
            FROM permission p
            WHERE rp.permission_id = p.id AND p.perm_code = ANY(:perm_codes)
            """
        ),
        {"perm_codes": perm_codes},
    )
    conn.execute(
        sa.text("UPDATE permission SET is_deleted = true WHERE perm_code = ANY(:perm_codes)"),
        {"perm_codes": perm_codes},
    )
