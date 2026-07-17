"""Tests for rag_index.split_text pure function.

Standalone - does not import conftest or app.main to avoid DB dependency.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.rag_index import split_text


def test_short_text_single_chunk():
    result = split_text("Hello world", chunk_size=600, overlap=80)
    assert len(result) == 1
    assert result[0]["chunk_text"] == "Hello world"
    assert result[0]["chunk_index"] == 0


def test_long_text_multiple_chunks():
    text = "a" * 2000
    result = split_text(text, chunk_size=600, overlap=20)
    assert len(result) >= 3
    for i in range(len(result) - 1):
        curr_end = result[i]["chunk_text"][-20:]
        next_start = result[i + 1]["chunk_text"][:20]
        assert curr_end == next_start, f"Overlap mismatch between chunk {i} and {i + 1}"


def test_chunk_length_within_limit():
    text = "x" * 1500
    result = split_text(text, chunk_size=600, overlap=80)
    for chunk in result:
        assert len(chunk["chunk_text"]) <= 600


def test_empty_text():
    assert split_text("", chunk_size=600) == []


def test_exact_chunk_size():
    text = "a" * 600
    result = split_text(text, chunk_size=600, overlap=80)
    assert len(result) == 1
    assert result[0]["chunk_text"] == text


def test_zero_chunk_size():
    result = split_text("hello", chunk_size=0, overlap=0)
    assert result == []
