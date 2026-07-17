from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ocr import OcrError, ocr_pdf


@pytest.mark.anyio
async def test_ocr_is_fail_closed_when_disabled(monkeypatch):
    monkeypatch.setattr("app.services.ocr.settings.OCR_ADAPTER", "none")
    with pytest.raises(OcrError, match="未启用"):
        await ocr_pdf(b"pdf", "scan.pdf")


@pytest.mark.anyio
async def test_ocr_rejects_invalid_response(monkeypatch):
    monkeypatch.setattr("app.services.ocr.settings.OCR_ADAPTER", "tesseract")
    response = MagicMock(status_code=200)
    response.json.return_value = {"text": "missing metadata"}
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    with patch("app.services.ocr.httpx.AsyncClient", return_value=context):
        with pytest.raises(OcrError, match="格式无效"):
            await ocr_pdf(b"pdf", "scan.pdf")
