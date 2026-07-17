from __future__ import annotations

import hashlib

from app.services.parsers.base import ParseResult, ParserProtocol


class TestParser(ParserProtocol):  # noqa: N801
    __test__ = False
    """Deterministic test parser.

    Returns the raw bytes decoded as UTF-8 (fallback to repr) without any
    format-specific extraction. Used in unit/integration tests where a real
    PDF/DOC parser is unavailable or undesirable. Never performs OCR.
    """

    async def parse(self, file_bytes: bytes, *, file_name: str = "") -> ParseResult:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1", errors="replace")

        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ParseResult(text=text, content_hash=content_hash)
