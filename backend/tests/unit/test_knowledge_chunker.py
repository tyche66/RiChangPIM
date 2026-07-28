from app.knowledge.indexing.chunker import chunk_text, estimate_tokens


def test_estimate_tokens_is_positive_for_nonempty_text():
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) >= 10


def test_chunk_text_splits_large_paragraphs():
    text = ("段落A " * 500) + "\n" + ("段落B " * 500)
    chunks = chunk_text(text, target_tokens=300, overlap_tokens=30)
    assert len(chunks) >= 2
    assert all(chunk.token_count >= 1 for chunk in chunks)
    assert all(chunk.chunk_text.strip() for chunk in chunks)


def test_chunk_text_returns_empty_for_blank_text():
    assert chunk_text("   \n\n   ") == []
