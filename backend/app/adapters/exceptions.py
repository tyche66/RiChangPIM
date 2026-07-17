"""AI adapter exception hierarchy.

All messages are sanitized: no URLs, API keys, raw responses, or stack traces
are ever included.
"""

from __future__ import annotations


class AIAdapterError(Exception):
    """Base exception for all AI adapter failures."""


class AIAdapterTimeoutError(AIAdapterError):
    """Upstream did not respond within the configured timeout."""


class AIAdapterRateLimitError(AIAdapterError):
    """Upstream returned 429 Too Many Requests."""


class AIAdapterAuthenticationError(AIAdapterError):
    """Upstream returned 401 or 403."""


class AIAdapterBadRequestError(AIAdapterError):
    """Upstream returned 400."""


class AIAdapterServerError(AIAdapterError):
    """Upstream returned a 5xx status."""


class AIAdapterInvalidResponseError(AIAdapterError):
    """Upstream returned malformed / unparseable data."""


class AIAdapterDimensionMismatchError(AIAdapterError):
    """Embedding vector dimension does not match the expected dimension."""


class AIAdapterUnavailableError(AIAdapterError):
    """The adapter is intentionally unavailable (e.g. no AI configured)."""
