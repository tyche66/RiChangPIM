from __future__ import annotations

from pathlib import Path

from app.services.parsers.base import ParserError, ParserProtocol
from app.services.parsers.docx import DocxTextParser
from app.services.parsers.pdf import PdfTextParser

PDF_MIME_TYPES = {"application/pdf"}
DOCX_MIME_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
DOC_MIME_TYPES = {"application/msword"}


def get_parser(
    *,
    file_name: str = "",
    content_type: str | None = None,
    file_type: str | None = None,
) -> ParserProtocol:
    suffix = Path(file_name or "").suffix.lower()
    normalized_type = (content_type or "").lower()
    if normalized_type in PDF_MIME_TYPES or suffix == ".pdf" or file_type == "pdf":
        return PdfTextParser()
    if normalized_type in DOCX_MIME_TYPES or suffix == ".docx":
        return DocxTextParser()
    if normalized_type in DOC_MIME_TYPES or suffix == ".doc":
        raise ParserError("unsupported", "暂不支持旧版 DOC 格式，请转换为 DOCX")
    raise ParserError("unsupported", "不支持的文档格式")
