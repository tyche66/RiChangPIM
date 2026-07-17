from .base import AIServiceAdapter
from .exceptions import (
    AIAdapterAuthenticationError,
    AIAdapterBadRequestError,
    AIAdapterDimensionMismatchError,
    AIAdapterError,
    AIAdapterInvalidResponseError,
    AIAdapterRateLimitError,
    AIAdapterServerError,
    AIAdapterTimeoutError,
    AIAdapterUnavailableError,
)
from .factory import build_adapter, get_ai_adapter
from .none import NoneAdapter
from .openai import OpenAIAdapter, OpenAIConfig, register_vector_dim

__all__ = [
    "AIServiceAdapter",
    "AIAdapterError",
    "AIAdapterTimeoutError",
    "AIAdapterRateLimitError",
    "AIAdapterAuthenticationError",
    "AIAdapterBadRequestError",
    "AIAdapterServerError",
    "AIAdapterInvalidResponseError",
    "AIAdapterDimensionMismatchError",
    "AIAdapterUnavailableError",
    "OpenAIAdapter",
    "OpenAIConfig",
    "register_vector_dim",
    "NoneAdapter",
    "build_adapter",
    "get_ai_adapter",
]
