"""user_token_version

管理员重设密码后需要让该用户已签发的 JWT 立即失效。这里在 ``user`` 上增加
``token_version``，登录时写入 JWT 的 ``tv`` 声明，鉴权时与库中值比对；
重设密码自增该列即可让旧 token 全部失效。

历史 token（无 ``tv`` 声明）保持兼容，按部署前的行为自然过期。

Revision ID: 0034_user_token_version
Revises: 0033_sales_media_permissions
Create Date: 2026-10-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_user_token_version"
down_revision: Union[str, None] = "0033_sales_media_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "token_version")
