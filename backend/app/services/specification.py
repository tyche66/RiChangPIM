"""规格字符串的结构化读取。

产品规格是自由文本，真实库里既有 ``1200*600*750``，也有 ``W2000*1000*750``、
``L1000``、``异形``。选品筛选要按「长度」聚合/过滤，解析规则必须只有一份，
否则菜单上的 1800 和过滤 SQL 里的 1800 不是同一个东西。

这里只做 Python 解析，不在 SQL 里拆字符串：长度既不是数据库既有列，格式又
不统一，SQL 侧强转会直接报 ``invalid input syntax``（真实库里 ``W2000`` 就有
十四条）。筛选改为「先解析出同长度的规格原值集合，再用 IN 精确匹配」，解析
函数与菜单聚合共用同一份实现。
"""

from __future__ import annotations

import re

SPEC_PREFIX_RE = re.compile(r"\bW\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
SPEC_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_spec_length_mm(specification: str | None) -> float | None:
    """从规格文本取长度（第一维度），优先认 ``W1200`` 这类带前缀写法。

    取不到正数时返回 ``None``：``异形`` / ``/`` 这类规格不参与长度筛选。
    """
    if not specification:
        return None
    match = SPEC_PREFIX_RE.search(specification) or SPEC_NUMBER_RE.search(specification)
    if match is None:
        return None
    value = float(match.group(1))
    return value if value > 0 else None


def format_spec_length(value: float) -> str:
    """长度展示：整数不带小数点（1800 而不是 1800.0）。"""
    return str(int(value)) if float(value).is_integer() else f"{float(value):g}"
