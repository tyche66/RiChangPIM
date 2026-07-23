from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.quotations import export_quotation_pdf, router
from app.core.permission import PermissionChecker
from app.models import doc_chunk as _doc_chunk  # noqa: F401 - registers SQLAlchemy relationships
from app.models.sales import Quotation, QuotationItem


class _ScalarResult:
    def __init__(self, quotation):
        self._quotation = quotation

    def scalar_one_or_none(self):
        return self._quotation

    def scalars(self):
        return self

    def all(self):
        return [self._quotation]


class _DB:
    def __init__(self, quotation):
        self._quotation = quotation

    async def execute(self, _stmt):
        return _ScalarResult(self._quotation)


class _GotenbergResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content


class _GotenbergClient:
    next_response = _GotenbergResponse(200, b"%PDF-1.7\n")
    posted_url = ""
    posted_files = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, files):
        type(self).posted_url = url
        type(self).posted_files = files
        return type(self).next_response


def _quotation():
    quotation = Quotation(
        id=uuid4(),
        quotation_no="QT-TEST-001",
        proposal_id=uuid4(),
        creator_id=uuid4(),
        valid_until=datetime(2026, 8, 1, tzinfo=UTC),
        total_amount=226.0,
        subtotal=200.0,
        tax_rate=0.13,
        discount=1.0,
        status="draft",
        is_deleted=False,
    )
    quotation.items = [
        QuotationItem(
            id=uuid4(),
            quotation_id=quotation.id,
            product_id=uuid4(),
            quantity=2,
            unit_price=100.0,
            tax_rate=0.13,
            subtotal=200.0,
            is_deleted=False,
        )
    ]
    return quotation


def test_quotation_pdf_route_keeps_view_permission():
    route = next(r for r in router.routes if getattr(r, "path", None) == "/{quotation_id}/pdf")
    permissions = [
        dep.call.required_permission
        for dep in route.dependant.dependencies
        if isinstance(dep.call, PermissionChecker)
    ]
    assert permissions == ["quotation:view"]


@pytest.mark.anyio
async def test_export_quotation_pdf_returns_gotenberg_pdf(monkeypatch):
    quotation = _quotation()
    monkeypatch.setattr("app.api.v1.quotations.settings.GOTENBERG_URL", "http://pdf:3000")
    monkeypatch.setattr("app.api.v1.quotations.httpx.AsyncClient", _GotenbergClient)
    _GotenbergClient.next_response = _GotenbergResponse(200, b"%PDF-1.7\ncontent")

    response = await export_quotation_pdf.__wrapped__(
        request=None, quotation_id=quotation.id, db=_DB(quotation)
    )

    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-1.7\ncontent"
    assert _GotenbergClient.posted_url == "http://pdf:3000/forms/chromium/convert/html"
    assert _GotenbergClient.posted_files["files"][0] == "index.html"


@pytest.mark.anyio
async def test_export_quotation_pdf_returns_502_on_gotenberg_error(monkeypatch):
    quotation = _quotation()
    monkeypatch.setattr("app.api.v1.quotations.settings.GOTENBERG_URL", "http://pdf:3000")
    monkeypatch.setattr("app.api.v1.quotations.httpx.AsyncClient", _GotenbergClient)
    _GotenbergClient.next_response = _GotenbergResponse(500, b"failed")

    with pytest.raises(HTTPException) as exc_info:
        await export_quotation_pdf.__wrapped__(
            request=None, quotation_id=quotation.id, db=_DB(quotation)
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["code"] == 50201
