import pytest

from app.adapters.none import NoneAdapter
from app.adapters.openai import OpenAIConfig


def test_none_adapter_chat():
    adapter = NoneAdapter()
    import asyncio

    result = asyncio.run(adapter.chat(session_id="test", message="hello", history=[]))
    assert "AI 能力中心未配置" in result["answer"]


def test_none_adapter_parse_tool_calls():
    adapter = NoneAdapter()
    result = adapter.parse_tool_calls({"answer": ""})
    assert result == []


def test_openai_adapter_requires_api_key():
    with pytest.raises(ValueError, match="api_key"):
        OpenAIConfig(api_key="", api_url="https://api.openai.com/v1")
