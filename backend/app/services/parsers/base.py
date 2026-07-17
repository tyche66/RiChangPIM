from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ParserError(Exception):
    """Controlled parser error safe to expose to API clients."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParseResult:
    """Result of parsing a document.

    Attributes:
        text: Extracted plain text. Empty string when nothing could be parsed.
        content_hash: SHA-256 hex digest of the raw text. Used for idempotent
            re-indexing — if the hash matches the manual's stored ``content_hash``,
            the indexer skips re-chunking.
    """

    text: str
    content_hash: str
    parser_name: str = "unknown"
    parser_version: str = "unknown"
    page_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ParserProtocol(Protocol):
    """Document parser contract.

    Concrete parsers extract plain text from an attachment. Implementations
    MUST NOT perform OCR — text extraction only. Parsers that cannot extract
    text (unsupported format, corrupted file, encrypted PDF) return an empty
    ``ParseResult.text`` so the caller can record the failure on the manual.
    """

    async def parse(self, file_bytes: bytes, *, file_name: str = "") -> ParseResult:
        """Parse document bytes into plain text.

        :param file_bytes: Raw file content (e.g. downloaded from MinIO).
        :param file_name: Original filename, used for format detection.
        :return: ``ParseResult`` with extracted text and its SHA-256 hash.
        """
        ...
