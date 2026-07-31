"""AI 选品接口的敏感字段不变量（cost_price / supplier_id 不得外泄）。

这两条断言原来只存在于 admin 端的 e2e（`frontend/tests/e2e/ai-features.spec.ts`）里，
靠「页面上看不到 cost_price」来证明。T02 把 AI 选品改成 iframe 嵌 portal 之后，被测的
admin 端 UI 整体搬走了，那两条 DOM 断言连同 UI 一起失效，不变量就此失守、没有任何东西接手。

DOM 断言本来也不该是这条不变量的唯一防线：它只能证明「这个页面没把字段画出来」，接口
一旦多返回一个字段，页面不显示照样是泄露。所以这里把它下沉到真正的执行点——
`RecommendService` 拼完 product dict 之后调的 `filter_sensitive_fields`
（`app/services/recommend.py:147`）。

顺带把「AI 不可用 / 解析失败」两个状态也锁在这一层：前端的降级横幅是按 status 字段渲染的，
锁 status 比锁横幅文案更耐改版。
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.serializers import filter_sensitive_fields
from app.schemas.ai import AIStatus
from app.services.recommend import RecommendService

SENSITIVE = ("cost_price", "supplier_id", "supplier_name", "margin", "profit")


class _FakeAdapter:
    """只回一段固定 JSON 的假适配器；raises 非空时改为抛异常，用来走降级分支。"""

    def __init__(self, answer: str = "", raises: Exception | None = None):
        self._answer = answer
        self._raises = raises

    async def chat(self, **_kwargs):
        if self._raises is not None:
            raise self._raises
        return {"answer": self._answer}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _FakeDB:
    """execute() 忽略传进来的 statement，直接吐固定行——本用例不测 SQL，只测出参裁剪。"""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def _fake_product():
    return SimpleNamespace(
        id=uuid4(),
        product_no="P-0001",
        product_name="测试沙发",
        brand_id=uuid4(),
        category_id=uuid4(),
        face_price=9999,
        cost_price=1234,
        supplier_id=uuid4(),
        material="布艺",
        stock_status="in_stock",
        description="用于不变量测试的假产品",
    )


def _ok_answer() -> str:
    return json.dumps(
        {
            "category_id": None,
            "max_face_price": None,
            "tag_ids": [],
            "keywords": [],
            "stock_status": None,
            "rationale": "按预算与风格筛选",
        }
    )


async def _run(role_code):
    service = RecommendService(
        _FakeAdapter(answer=_ok_answer()),
        _FakeDB([_fake_product()]),
        model="fake-model",
    )
    return await service.recommend(
        "给我几款布艺沙发", {"role_code": role_code}, role_code=role_code
    )


# role_code=None 是最关键的一档：令牌里没带 role_code、或角色表新增了一个谁都没登记过的
# 角色时都会落到这里。filter_sensitive_fields 对未知角色取所有敏感字段的并集（fail-closed），
# 这条用例就是防止有人把它改成 fail-open。
@pytest.mark.parametrize("role_code", ["sales", "viewer", "unknown_role_code", None])
async def test_recommend_hides_sensitive_fields_for_non_privileged_roles(role_code):
    result = await _run(role_code)

    assert result["status"] == AIStatus.success.value
    assert result["products"], "假 db 给了一行，products 不该是空的（空列表会让下面的断言全部空转）"
    for product in result["products"]:
        for field in SENSITIVE:
            assert field not in product, f"role_code={role_code!r} 泄露了 {field}"
        # 反向确认裁剪没有把整条记录削掉——否则「字段不存在」会是假阳性。
        assert product["product_name"] == "测试沙发"
        assert product["face_price"] == 9999


# 特权角色必须还能看到成本价，否则「裁剪」就变成了「功能坏了」——只测「看不到」会让
# 一个 return {} 的实现也通过。
@pytest.mark.parametrize("role_code", ["admin", "super_admin", "finance", "product_manager"])
async def test_recommend_keeps_sensitive_fields_for_privileged_roles(role_code):
    result = await _run(role_code)

    product = result["products"][0]
    assert product["cost_price"] == 1234
    assert product["supplier_id"]


async def test_recommend_marks_products_as_verified():
    """原 e2e 的「已验证」标记：数据侧的来源标注仍在，UI 换壳不影响这条契约。"""
    product = (await _run("sales"))["products"][0]

    assert product["_verified"] is True
    assert product["_verified_by"] == "business_api"


async def test_recommend_degrades_when_adapter_unavailable():
    """AI 适配器抛异常 → status=degraded 且不返回任何产品；前端据此渲染降级横幅。"""
    service = RecommendService(
        _FakeAdapter(raises=RuntimeError("adapter down")),
        _FakeDB([_fake_product()]),
        model="fake-model",
    )

    result = await service.recommend("随便", {"role_code": "sales"}, role_code="sales")

    assert result["status"] == AIStatus.degraded.value
    assert result["products"] == []


@pytest.mark.parametrize(
    ("answer", "case"),
    [("", "空回答"), ("这不是 JSON", "非 JSON"), ('{"max_face_price": -1}', "字段校验失败")],
)
async def test_recommend_reports_parse_failure(answer, case):
    """三种「AI 回了但没法用」的输入都必须落到 parse_failed，且不得漏出产品数据。"""
    service = RecommendService(
        _FakeAdapter(answer=answer), _FakeDB([_fake_product()]), model="fake-model"
    )

    result = await service.recommend("随便", {"role_code": "sales"}, role_code="sales")

    expected = AIStatus.parse_failed.value
    assert result["status"] == expected, case
    assert result["products"] == [], case


def test_filter_sensitive_fields_recurses_into_nested_structures():
    """裁剪必须能穿透 list/dict 嵌套——AI 相关接口的载荷不止「一层产品数组」这一种形状。"""
    payload = {
        "products": [{"product_name": "A", "cost_price": 1, "supplier_id": "s"}],
        "grouped": {"hot": [{"cost_price": 2, "margin": 0.3, "face_price": 10}]},
    }

    cleaned = filter_sensitive_fields(payload, "sales")

    assert cleaned["products"][0] == {"product_name": "A"}
    assert cleaned["grouped"]["hot"][0] == {"face_price": 10}
