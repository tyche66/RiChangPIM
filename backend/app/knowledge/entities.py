from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QueryEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(default_factory=list)
    product_nos: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    status_terms: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    price_sort: str | None = None
    specification_sort: str | None = None
