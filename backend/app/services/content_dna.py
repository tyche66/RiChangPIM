"""Local, curated summaries of the two approved content DNA packages.

The source ZIPs are never executed or copied into the repository.  These
assets describe writing structure and evidence boundaries only.  Business
facts must be supplied by PIM records or user-provided material at runtime.
"""

from __future__ import annotations

from typing import Any

DNA_SOURCES: dict[str, dict[str, str]] = {
    "yuc": {
        "label": "禹橙 DNA",
        "description": "Hook、单一主张、证据层级与办公场景 CTA",
    },
    "yanye": {
        "label": "言也 DNA",
        "description": "证据边界、待核验清单与克制的转化结构",
    },
}

DEFAULT_DNA_CODE = "yuc"
OPERATIONAL_SKILL_CODES = frozenset(
    {"yuc-topic", "yuc-content", "yanye-topic", "yanye-content"}
)
LEGACY_COMPAT_CODES = frozenset({"content-default", "topic-basic"})

PILLAR_CODES = ("A", "B", "C", "D", "E")
PILLAR_LABELS = {
    "A": "办公空间解决方案",
    "B": "真实项目与安装案例",
    "C": "产品知识与选型避坑",
    "D": "交付安装与协同",
    "E": "本地服务与客户沟通",
}

CONTENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": [
                    "title",
                    "body",
                    "hashtags",
                    "mentioned_products",
                    "verification_gaps",
                    "warnings",
                ],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "maxLength": 60},
                    "body": {"type": "string", "minLength": 30, "maxLength": 2000},
                    "hashtags": {
                        "type": "array",
                        "maxItems": 10,
                        "items": {"type": "string", "maxLength": 20},
                    },
                    "mentioned_products": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 120},
                    },
                    "verification_gaps": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 240},
                    },
                    "warnings": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 240},
                    },
                },
            },
        }
    },
}

TOPIC_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "required": ["title", "angle", "audience", "reason", "suggested_platform",
                             "related_product_ids", "pillar_code", "verification_gaps"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "maxLength": 60},
                    "angle": {"type": "string", "maxLength": 300},
                    "audience": {"type": "string", "maxLength": 120},
                    "reason": {"type": "string", "maxLength": 300},
                    "suggested_platform": {"type": "string", "maxLength": 32},
                    "related_product_ids": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 64},
                    },
                    "pillar_code": {"type": "string", "enum": list(PILLAR_CODES)},
                    "verification_gaps": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 240},
                    },
                },
            },
        }
    },
}

YUC_CONTENT_PROMPT = """你是禹橙 DNA 内容助手。
品牌表达务实、具体、可信、办公场景导向、审美克制、服务导向，不过度承诺。
只使用给出的 PIM 产品/项目事实，不把 DNA 样例、人物、数字、案例或效果当作公司事实。
用 Hook -> 单一主张 -> 为什么 -> 证据 -> 办公场景行动建议 -> 克制 CTA 组织内容；
前几句直接进入具体场景，避免空泛开场。
事实缺口必须写入 verification_gaps，不能用模型常识补齐。
禁止绝对化、虚构客户背书、参数、认证、效果、价格、库存、交期和未核验承诺。

主题：{topic}
平台：{platform}
语气：{tone}
产品事实：{product_facts}
项目/用户提供素材：{project_facts}
输出 JSON：{output_schema}
"""

YANYE_CONTENT_PROMPT = """你是言也 DNA 内容助手。
品牌表达务实、具体、可信、办公场景导向、审美克制、服务导向，不过度承诺。
证据优先、表达务实克制，输出可执行的办公场景内容，不模仿任何原文句子。
每条只保留一个可核验主张；按 Hook、场景问题、判断框架、证据边界、下一步 CTA 编排。
没有数据、客户采访或项目记录时明确写 verification_gaps。
禁止把素材中的样例数字、人物、案例、成绩、认证或效果移植为本公司事实；
禁止绝对化、虚构背书、价格/库存/交付承诺。

主题：{topic}
平台：{platform}
语气：{tone}
产品事实：{product_facts}
项目/用户提供素材：{project_facts}
输出 JSON：{output_schema}
"""

YUC_TOPIC_PROMPT = """你是禹橙 DNA 选题助手。
品牌表达务实、具体、可信、办公场景导向、审美克制、服务导向，不过度承诺。
围绕办公空间解决方案动态生成选题，不使用固定选题表。
每条选题只聚焦一个办公场景问题，给出 Hook 方向、受众、理由、建议平台、
关联产品、pillar_code 和 verification_gaps。
优先具体的空间、选型、安装协同问题；真实项目/客户/参数只能来自给出的事实，缺少资料要列入核验清单。
禁止绝对化、虚构客户背书、案例、参数、认证、效果和未核验承诺。
主题：{topic}
平台：{platform}
语气：{tone}
目标支柱配额：{pillar_quota}
产品事实：{product_facts}
输出 JSON：{output_schema}
"""

YANYE_TOPIC_PROMPT = """你是言也 DNA 选题助手。
品牌表达务实、具体、可信、办公场景导向、审美克制、服务导向，不过度承诺。
以证据边界和客户决策为中心，生成办公场景导向的可执行选题。
每条只提出一个主张，必须给出 title、angle、audience、reason、suggested_platform、
related_product_ids、pillar_code、verification_gaps。
没有真实项目/客户资料时，不得写成已发生的案例；用待核验清单标明需要补充的来源。
主题：{topic}
平台：{platform}
语气：{tone}
目标支柱配额：{pillar_quota}
产品事实：{product_facts}
输出 JSON：{output_schema}
"""

OPERATIONAL_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "code": "yuc-content",
        "source_dna": "yuc",
        "name": "禹橙 DNA · 内容工坊",
        "skill_type": "content",
        "description": DNA_SOURCES["yuc"]["description"],
        "prompt_template": YUC_CONTENT_PROMPT,
        "output_schema": CONTENT_OUTPUT_SCHEMA,
        "sort_order": 10,
    },
    {
        "code": "yanye-content",
        "source_dna": "yanye",
        "name": "言也 DNA · 内容工坊",
        "skill_type": "content",
        "description": DNA_SOURCES["yanye"]["description"],
        "prompt_template": YANYE_CONTENT_PROMPT,
        "output_schema": CONTENT_OUTPUT_SCHEMA,
        "sort_order": 20,
    },
    {
        "code": "yuc-topic",
        "source_dna": "yuc",
        "name": "禹橙 DNA · 独立选题",
        "skill_type": "topic",
        "description": DNA_SOURCES["yuc"]["description"],
        "prompt_template": YUC_TOPIC_PROMPT,
        "output_schema": TOPIC_OUTPUT_SCHEMA,
        "sort_order": 10,
    },
    {
        "code": "yanye-topic",
        "source_dna": "yanye",
        "name": "言也 DNA · 独立选题",
        "skill_type": "topic",
        "description": DNA_SOURCES["yanye"]["description"],
        "prompt_template": YANYE_TOPIC_PROMPT,
        "output_schema": TOPIC_OUTPUT_SCHEMA,
        "sort_order": 20,
    },
)

SKILL_SPECS_BY_CODE = {item["code"]: item for item in OPERATIONAL_SKILLS}


def source_dna_label(source_dna: str | None) -> str | None:
    return DNA_SOURCES.get(source_dna or "", {}).get("label")


def is_operational_skill_code(code: str | None, skill_type: str | None = None) -> bool:
    spec = SKILL_SPECS_BY_CODE.get(code or "")
    return bool(spec and (skill_type is None or spec["skill_type"] == skill_type))
