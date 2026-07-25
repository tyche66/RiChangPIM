from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

KnowledgeEventName = Literal[
    "meta",
    "phase",
    "answer_delta",
    "source",
    "products",
    "done",
    "error",
]


class KnowledgeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: KnowledgeEventName
    data: dict[str, Any]

    def encode(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {self.event}\ndata: {payload}\n\n"


def sse_event(event: KnowledgeEventName, data: dict[str, Any]) -> str:
    return KnowledgeEvent(event=event, data=data).encode()
