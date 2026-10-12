"""PII 脱敏纯函数（HLD §7 / D3' 明文列 + 全链路脱敏）。

约束：
- 列表 ``GET /customers`` 完全不返回 phone/wechat/address，只返回 ``has_phone``。
- 详情掩码：``138****1234`` / ``ab***`` / ``浙江省杭州市***``（保留到市）。
- 明文只经 ``GET /customers/{id}/pii``（需 customer:pii + 审计 + 限速）。
- 任何 logger 不得打印原文；日志与异常统一走本模块。
"""

from __future__ import annotations

import re

__all__ = ["mask_phone", "mask_wechat", "mask_address"]

# 地址保留到第一个「市」字符为止（浙江省杭州市…）
# 使用贪婪匹配确保匹配到最后一个「市」（处理「省市」等边界情况）
_CITY_PATTERN = re.compile(r"^.*?市")


def mask_phone(phone) -> str:
    """号码脱敏：按位数（数字个数）保留前 位数-8 位与后 4 位，中间 ``****``；
    位数 < 7 全掩 ``****``。

    >>> mask_phone("13812341234")
    '138****1234'
    >>> mask_phone("0571-88889999")
    '0571****9999'
    >>> mask_phone("12345")
    '****'
    >>> mask_phone(None)
    '****'
    """
    if not phone:
        return "****"
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) < 7:
        return "****"
    prefix_len = max(len(digits) - 8, 0)
    return digits[:prefix_len] + "****" + digits[-4:]


def mask_wechat(wechat) -> str:
    """微信号脱敏：保留前 2 位 + ``***``；长度 <= 2 全掩为 ``*``。

    >>> mask_wechat("abcdefg")
    'ab***'
    >>> mask_wechat("ab")
    '*'
    >>> mask_wechat(None)
    '*'
    """
    if not wechat:
        return "*"
    text = str(wechat)
    if len(text) <= 2:
        return "*"
    return text[:2] + "***"


def mask_address(address) -> str:
    """地址脱敏：保留到「市」为止 + ``***``；无「市」模式 → ``***``。

    特殊处理：地址恰好以「市」结尾（如「北京市」）→ ``***``（全掩）。

    >>> mask_address("浙江省杭州市余杭区文一西路969号")
    '浙江省杭州市***'
    >>> mask_address("北京市")
    '***'
    >>> mask_address("杭州")
    '***'
    >>> mask_address(None)
    '***'
    """
    if not address:
        return "***"
    text = str(address)
    m = _CITY_PATTERN.match(text)
    if not m:
        return "***"
    # 如果匹配到「市」后没有更多内容（地址恰好是城市名），全掩
    if m.end() == len(text):
        return "***"
    return m.group(0) + "***"
