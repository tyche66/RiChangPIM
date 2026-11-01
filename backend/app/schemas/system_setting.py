"""全局设置 schemas（FR-3）。

三个分组（brand / share / business）各一个嵌套模型，``extra="forbid"``：
未知 key 一律 422 拒绝，不允许客户端悄悄塞新字段。

* ``SystemSettingRead``     —— 读取契约，带全部默认值；DB 缺行/缺键时读取侧回落到这里。
* ``SystemSettingUpdate``   —— PUT 局部更新契约：未出现的字段保持原值；显式 ``null``
  除 ``brand.logo_attachment_id``（清除 Logo）外一律按「保持原值」处理。
* ``PublicSettings``        —— 匿名 ``GET /settings/public`` 的响应体，只含品牌字段，
  绝不携带分享/业务配置（验收标准）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_SITE_NAME = "RiChangPIM"
DEFAULT_PORTAL_TITLE = "RiChangPIM Portal"
DEFAULT_PORTAL_SUBTITLE = (
    "内部只读 AI 工作台。产品、资料和质量记录统一走 Knowledge Gateway，答案都带引用来源。"
)
DEFAULT_FOOTER_TEXT = "由 RiChangPIM 提供"
DEFAULT_SHARE_EXPIRE_HOURS = 24
DEFAULT_SHARE_MAX_ACCESS_COUNT = 100
DEFAULT_TAX_RATE = 0.13
DEFAULT_AMOUNT_DECIMAL_PLACES = 2
DEFAULT_CURRENCY_SYMBOL = "¥"


def _strip_str(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class BrandSettings(BaseModel):
    """品牌分组：门户标题、页脚、Logo。"""

    model_config = ConfigDict(extra="forbid")

    site_name: str = Field(DEFAULT_SITE_NAME, min_length=1, max_length=64)
    portal_title: str = Field(DEFAULT_PORTAL_TITLE, min_length=1, max_length=128)
    portal_subtitle: str = Field(DEFAULT_PORTAL_SUBTITLE, max_length=500)
    footer_text: str = Field(DEFAULT_FOOTER_TEXT, max_length=128)
    # 只存附件 ID；URL 由读取侧按「ID + 更新时间」生成带版本号的 /settings/logo?v=<hash>。
    logo_attachment_id: UUID | None = None

    _strip = field_validator(
        "site_name", "portal_title", "portal_subtitle", "footer_text", mode="before"
    )(_strip_str)

    @field_validator("site_name", "portal_title")
    @classmethod
    def _title_not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("不能为空")
        return value


class ShareSettings(BaseModel):
    """分享分组：方案/报价分享弹窗与后端缺省值的统一来源。

    范围与 shares.py 的上限保持一致（720 小时 / 10000 次）；
    前端输入框上限 1000 是另一层 UI 约束，不在这里放松。
    """

    model_config = ConfigDict(extra="forbid")

    share_default_expire_hours: int = Field(DEFAULT_SHARE_EXPIRE_HOURS, ge=1, le=720)
    share_default_max_access_count: int = Field(DEFAULT_SHARE_MAX_ACCESS_COUNT, ge=1, le=10000)
    share_default_require_password: bool = False


class BusinessSettings(BaseModel):
    """业务分组：报价默认税率与金额展示格式。"""

    model_config = ConfigDict(extra="forbid")

    quotation_default_tax_rate: float = Field(DEFAULT_TAX_RATE, ge=0, le=1)
    amount_decimal_places: int = Field(DEFAULT_AMOUNT_DECIMAL_PLACES, ge=0, le=4)
    currency_symbol: str = Field(DEFAULT_CURRENCY_SYMBOL, min_length=1, max_length=8)

    _strip = field_validator("currency_symbol", mode="before")(_strip_str)


class SystemSettingRead(BaseModel):
    """GET /settings 的 data：三个分组的生效值（已与默认值合并）。"""

    model_config = ConfigDict(extra="forbid")

    brand: BrandSettings = Field(default_factory=BrandSettings)
    share: ShareSettings = Field(default_factory=ShareSettings)
    business: BusinessSettings = Field(default_factory=BusinessSettings)


class BrandSettingsUpdate(BaseModel):
    """品牌分组局部更新。``logo_attachment_id: null`` = 清除 Logo。"""

    model_config = ConfigDict(extra="forbid")

    site_name: str | None = Field(None, min_length=1, max_length=64)
    portal_title: str | None = Field(None, min_length=1, max_length=128)
    portal_subtitle: str | None = Field(None, max_length=500)
    footer_text: str | None = Field(None, max_length=128)
    logo_attachment_id: UUID | None = None

    _strip = field_validator(
        "site_name", "portal_title", "portal_subtitle", "footer_text", mode="before"
    )(_strip_str)

    @field_validator("site_name", "portal_title")
    @classmethod
    def _title_not_empty(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("不能为空")
        return value


class ShareSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_default_expire_hours: int | None = Field(None, ge=1, le=720)
    share_default_max_access_count: int | None = Field(None, ge=1, le=10000)
    share_default_require_password: bool | None = None


class BusinessSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quotation_default_tax_rate: float | None = Field(None, ge=0, le=1)
    amount_decimal_places: int | None = Field(None, ge=0, le=4)
    currency_symbol: str | None = Field(None, min_length=1, max_length=8)

    _strip = field_validator("currency_symbol", mode="before")(_strip_str)


class SystemSettingUpdate(BaseModel):
    """PUT /settings 的请求体：嵌套局部更新，分组缺省即不动该分组。"""

    model_config = ConfigDict(extra="forbid")

    brand: BrandSettingsUpdate | None = None
    share: ShareSettingsUpdate | None = None
    business: BusinessSettingsUpdate | None = None


class PublicSettings(BaseModel):
    """GET /settings/public 的 data：只回品牌字段 + 带版本号的 Logo URL。"""

    site_name: str
    portal_title: str
    portal_subtitle: str
    footer_text: str
    logo_url: str | None = None
