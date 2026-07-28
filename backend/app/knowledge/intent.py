from __future__ import annotations

from enum import StrEnum


class KnowledgeIntent(StrEnum):
    PRODUCT_SEARCH = "product_search"
    PRODUCT_COMPARE = "product_compare"
    PRODUCT_DETAIL = "product_detail"
    QUALITY_SUMMARY = "quality_summary"
    QUALITY_LIST_ISSUES = "quality_list_issues"
    KNOWLEDGE_QUESTION = "knowledge_question"
    PROCUREMENT_COMPARE = "procurement_compare"
    PROPOSAL_DRAFT = "proposal_draft"
    UNSUPPORTED = "unsupported"
