from typing import Any

SENSITIVE_FIELDS_BY_ROLE: dict[str, set[str]] = {
    "sales": {"cost_price", "supplier_id", "supplier_name", "margin", "profit"},
    "viewer": {"cost_price", "supplier_id", "supplier_name", "margin", "profit"},
}

ADMIN_ROLES: set[str] = {"admin", "super_admin", "finance", "product_manager"}


def filter_sensitive_fields(
    payload: Any,
    role_code: str | None = None,
    fields_to_hide: set[str] | None = None,
) -> Any:
    if role_code in ADMIN_ROLES:
        return payload
    if isinstance(role_code, str) and role_code.startswith("admin"):
        return payload

    if fields_to_hide is not None:
        hidden = fields_to_hide
    elif role_code in SENSITIVE_FIELDS_BY_ROLE:
        hidden = SENSITIVE_FIELDS_BY_ROLE[role_code]
    else:
        hidden = set()
        for v in SENSITIVE_FIELDS_BY_ROLE.values():
            hidden |= v

    if hidden is None:
        hidden = set()

    if isinstance(payload, list):
        return [filter_sensitive_fields(item, role_code, hidden) for item in payload]

    if isinstance(payload, dict):
        return {
            k: filter_sensitive_fields(v, role_code, hidden)
            for k, v in payload.items()
            if k not in hidden
        }

    return payload
