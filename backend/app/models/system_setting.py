"""全局设置模型（FR-3 全局设置）。

单行表：全库只允许一行（迁移 0039 用部分唯一索引兜底），
``data`` JSONB 保存全部设置项（brand / share / business 三个分组）。

行缺失时由服务层按 Schema 默认值幂等创建，本表因此是「覆盖层」：
代码内 Schema 默认值始终是最终兜底，读写都经过 app/schemas/system_setting.py。
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column

from app.models.base import CommonBase


class SystemSetting(CommonBase):
    __tablename__ = "system_setting"

    # 嵌套结构 {"brand": {...}, "share": {...}, "business": {...}}；
    # 允许只存被显式改过的键，读取侧与默认值合并。
    data = mapped_column(JSONB, nullable=False, default=dict)
