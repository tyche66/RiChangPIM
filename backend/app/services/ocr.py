from dataclasses import dataclass

import httpx

from app.core.config import settings


class OcrError(Exception):
    pass


@dataclass(frozen=True)
class OcrResult:
    text: str
    content_hash: str
    page_count: int
    engine: str
    version: str


async def ocr_pdf(content: bytes, file_name: str) -> OcrResult:
    if settings.OCR_ADAPTER != "tesseract":
        raise OcrError("OCR 补偿引擎未启用")
    try:
        async with httpx.AsyncClient(timeout=settings.OCR_TIMEOUT) as client:
            response = await client.post(
                f"{settings.OCR_API_URL.rstrip('/')}/ocr/pdf",
                files={"file": (file_name, content, "application/pdf")},
            )
    except httpx.RequestError as exc:
        raise OcrError("OCR 服务不可用") from exc
    if response.status_code >= 400:
        raise OcrError(f"OCR 识别失败 ({response.status_code})")
    try:
        payload = response.json()
        return OcrResult(
            text=payload["text"],
            content_hash=payload["content_hash"],
            page_count=int(payload["page_count"]),
            engine=payload["engine"],
            version=payload["version"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OcrError("OCR 服务响应格式无效") from exc
