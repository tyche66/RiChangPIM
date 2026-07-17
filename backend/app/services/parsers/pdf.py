from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO

from pypdf import PdfReader

from app.services.parsers.base import ParserError, ParseResult, ParserProtocol


class PdfTextParser(ParserProtocol):
    """Extract text from text-based PDFs. OCR is intentionally not performed."""

    name = "pypdf"
    version = "5.1.0"

    async def parse(self, file_bytes: bytes, *, file_name: str = "") -> ParseResult:
        return await asyncio.to_thread(self._parse_sync, file_bytes)

    def _parse_sync(self, file_bytes: bytes) -> ParseResult:
        try:
            reader = PdfReader(BytesIO(file_bytes))
            if reader.is_encrypted:
                raise ParserError("encrypted_pdf", "PDF 文件已加密，无法解析")
            page_texts = []
            for page in reader.pages:
                page_texts.append(page.extract_text() or "")
        except ParserError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep parser errors controlled
            raise ParserError("parse_failed", "PDF 文本解析失败") from exc

        text = "\n\n".join(t.strip() for t in page_texts if t.strip()).strip()
        if not text:
            raise ParserError("ocr_required", "PDF 未包含可提取文本，需要真实 OCR 引擎")
        return ParseResult(
            text=text,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            parser_name=self.name,
            parser_version=self.version,
            page_count=len(reader.pages),
        )
