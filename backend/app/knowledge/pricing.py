from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PricingProvider(Protocol):
    def estimate_cost(self, provider: str | None, model: str | None, capability: str, input_tokens: int, output_tokens: int) -> float | None: ...


class NullPricingProvider:
    def estimate_cost(self, provider: str | None, model: str | None, capability: str, input_tokens: int, output_tokens: int) -> float | None:
        return None
