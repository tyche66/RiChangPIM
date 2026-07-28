from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.knowledge.permission_pool import PermissionPool


@runtime_checkable
class FieldProjectionStrategy(Protocol):
    def project(self, payload: Any, pool: PermissionPool) -> Any: ...


class LevelProjectionStrategy:
    def project(self, payload: Any, pool: PermissionPool) -> Any:
        if isinstance(payload, list):
            projected = [self.project(item, pool) for item in payload]
            return [item for item in projected if item is not None]
        if isinstance(payload, dict):
            field_name = payload.get("name")
            if isinstance(field_name, str) and field_name in pool.hidden_fields:
                return None
            out: dict[str, Any] = {}
            for key, value in payload.items():
                if key in pool.hidden_fields:
                    continue
                out[key] = self.project(value, pool)
            return out
        return payload


def get_field_projection_strategy() -> FieldProjectionStrategy:
    return LevelProjectionStrategy()
