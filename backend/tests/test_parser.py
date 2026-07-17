"""Tests for the parser protocol and test adapter.

Pure unit tests — no DB, no network.
"""

import hashlib
from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfWriter

from app.services.parsers import DocxTextParser, PdfTextParser, get_parser
from app.services.parsers.base import ParserError, ParseResult, ParserProtocol
from app.services.parsers.test_adapter import TestParser


def _make_docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()


def _make_text_pdf_bytes(text: str) -> bytes:
    # Minimal one-page PDF with a simple text drawing operator. pypdf can extract it.
    content = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length " + str(len(content)).encode("ascii") + b" >> stream\n"
        + content
        + b"\nendstream endobj\n",
    ]
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj)
    xref_offset = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.write(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return out.getvalue()


def _make_blank_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestParseResult:
    def test_is_frozen(self):
        result = ParseResult(text="hello", content_hash="abc")
        with pytest.raises(AttributeError):
            result.text = "mutated"

    def test_hash_stable(self):
        text = "Hello world"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        result = ParseResult(text=text, content_hash=expected)
        assert result.content_hash == expected


class TestParserProtocol:
    def test_protocol_is_abstract(self):
        class NoImpl:
            pass

        with pytest.raises(TypeError):
            ParserProtocol()


class TestTestParser:
    @pytest.fixture
    def parser(self):
        return TestParser()

    @pytest.mark.anyio
    async def test_parse_ascii(self, parser):
        data = b"Hello world"
        result = await parser.parse(data, file_name="test.txt")
        assert result.text == "Hello world"
        assert result.content_hash == hashlib.sha256(data).hexdigest()

    @pytest.mark.anyio
    async def test_parse_utf8(self, parser):
        text = "你好世界 🌍"
        data = text.encode("utf-8")
        result = await parser.parse(data, file_name="test.txt")
        assert result.text == text
        assert result.content_hash == hashlib.sha256(data).hexdigest()

    @pytest.mark.anyio
    async def test_parse_binary_fallback(self, parser):
        data = b"\x80\x81\x82"
        result = await parser.parse(data, file_name="test.bin")
        assert isinstance(result.text, str)
        assert len(result.text) > 0
        assert result.content_hash == hashlib.sha256(
            result.text.encode("utf-8")
        ).hexdigest()

    @pytest.mark.anyio
    async def test_parse_empty(self, parser):
        result = await parser.parse(b"", file_name="empty.txt")
        assert result.text == ""
        assert result.content_hash == hashlib.sha256(b"").hexdigest()

    @pytest.mark.anyio
    async def test_file_name_ignored(self, parser):
        data = b"content"
        r1 = await parser.parse(data, file_name="a.pdf")
        r2 = await parser.parse(data, file_name="b.docx")
        assert r1.text == r2.text
        assert r1.content_hash == r2.content_hash


class TestParserRegistry:
    def test_selects_pdf_by_extension(self):
        assert isinstance(get_parser(file_name="manual.pdf"), PdfTextParser)

    def test_selects_docx_by_extension(self):
        assert isinstance(get_parser(file_name="manual.docx"), DocxTextParser)

    def test_rejects_legacy_doc(self):
        with pytest.raises(ParserError, match="DOC"):
            get_parser(file_name="manual.doc")


class TestRealParsers:
    @pytest.mark.anyio
    async def test_docx_extracts_real_text(self):
        parser = DocxTextParser()
        result = await parser.parse(_make_docx_bytes("RiChangPIM DOCX fixture"), file_name="a.docx")
        assert "RiChangPIM DOCX fixture" in result.text
        assert result.parser_name == "python-docx"
        assert result.content_hash == hashlib.sha256(result.text.encode("utf-8")).hexdigest()

    @pytest.mark.anyio
    async def test_pdf_extracts_real_text(self):
        parser = PdfTextParser()
        result = await parser.parse(
            _make_text_pdf_bytes("RiChangPIM PDF fixture"), file_name="a.pdf"
        )
        assert "RiChangPIM PDF fixture" in result.text
        assert result.page_count == 1
        assert result.parser_name == "pypdf"

    @pytest.mark.anyio
    async def test_blank_pdf_requires_ocr(self):
        parser = PdfTextParser()
        with pytest.raises(ParserError) as exc:
            await parser.parse(_make_blank_pdf_bytes(), file_name="scan.pdf")
        assert exc.value.code == "ocr_required"
