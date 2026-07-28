from app.knowledge.tools.product import PRODUCT_SEARCH_ALIASES


def test_office_desk_search_expands_to_existing_desk_categories():
    assert PRODUCT_SEARCH_ALIASES["办公桌"] == (
        "办公桌",
        "班台",
        "总裁桌",
        "独立主管桌",
        "洽谈桌",
        "会议桌",
    )
