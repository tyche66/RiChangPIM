"""AI 供应商配置模型（AI 配置中心）。

两行数据，按 ``scope`` 区分：

* ``knowledge`` —— 主 AI（AI 选品检索、产品知识库、润色/推荐等）；
* ``content``   —— 内容工坊/独立选题域。

``api_key`` 明文入库但读取时一律脱敏；密钥不进日志、不进审计详情、
不进 /health 探针。配置缺失或字段为空时，各消费方回落到环境变量，
因此本表是「覆盖层」而不是「唯一来源」，老部署不迁移也能继续跑。
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CommonBase


class AiProviderConfig(CommonBase):
    __tablename__ = "ai_provider_config"

    scope = mapped_column(String(32), nullable=False, unique=True)
    label = mapped_column(String(64), nullable=False, default="")
    api_url = mapped_column(String(512), nullable=True)
    # 明文密钥：与 .env 同等级的机密。读取侧只返回掩码，写入侧只整段替换。
    api_key = mapped_column(Text, nullable=True)
    chat_model = mapped_column(String(128), nullable=True)
    # 内容域：可选模型白名单（逗号分隔）；空表示不限制。
    chat_models = mapped_column(Text, nullable=True)
    embedding_model = mapped_column(String(128), nullable=True)
    embedding_api_url = mapped_column(String(512), nullable=True)
    embedding_api_key = mapped_column(Text, nullable=True)
    timeout_seconds = mapped_column(String(16), nullable=True)
    enabled = mapped_column(Boolean, nullable=False, default=True)
