from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PermissionPool:
    name: str
    ai_permissions: frozenset[str]
    allowed_tools: frozenset[str]
    hidden_fields: frozenset[str]
    debug: bool = False


POOL_ADMIN = PermissionPool(
    name="pool_admin",
    ai_permissions=frozenset(
        {
            "ai:access",
            "ai:product",
            "ai:knowledge",
            "ai:quality",
            "ai:procurement",
            "knowledge:manage",
            "knowledge:debug",
            "ai:use",
        }
    ),
    allowed_tools=frozenset(
        {
            "product.search",
            "product.get_many",
            "product.compare",
            "quality.summary",
            "quality.list_issues",
            "supplier.compare",
        }
    ),
    hidden_fields=frozenset(),
    debug=True,
)
POOL_PURCHASER = PermissionPool(
    name="pool_purchaser",
    ai_permissions=frozenset(
        {"ai:access", "ai:product", "ai:knowledge", "ai:quality", "ai:procurement"}
    ),
    allowed_tools=frozenset(
        {
            "product.search",
            "product.get_many",
            "product.compare",
            "quality.summary",
            "quality.list_issues",
            "supplier.compare",
        }
    ),
    hidden_fields=frozenset(
        {"customer_name", "quotation_item_unit_price", "proposal_cost_details"}
    ),
)
POOL_SALES = PermissionPool(
    name="pool_sales",
    ai_permissions=frozenset({"ai:access", "ai:product", "ai:knowledge", "ai:use"}),
    allowed_tools=frozenset({"product.search", "product.get_many"}),
    hidden_fields=frozenset(
        {
            "cost_price",
            "supplier_id",
            "supplier_name",
            "margin",
            "profit",
            "quotation_item_cost",
            "proposal_cost_details",
        }
    ),
)
POOL_KNOWLEDGE = PermissionPool(
    name="pool_knowledge",
    ai_permissions=frozenset({"ai:access", "ai:knowledge", "ai:product", "product:view"}),
    allowed_tools=frozenset({"product.search", "product.get_many"}),
    hidden_fields=frozenset(
        {
            "cost_price",
            "supplier_id",
            "supplier_name",
            "margin",
            "profit",
            "material",
            "specification",
            "specification_length_mm",
            "colors",
            "data_source",
            "completeness_status",
            "stock_status",
        }
    ),
)

ROLE_POOL_MAP = {
    "admin": POOL_ADMIN,
    "super_admin": POOL_ADMIN,
    "purchaser": POOL_PURCHASER,
    "sales": POOL_SALES,
    "viewer": POOL_KNOWLEDGE,
}


@runtime_checkable
class PermissionPoolResolver(Protocol):
    def resolve(self, current_user: dict) -> PermissionPool: ...


class RoleBasedPoolResolver:
    def resolve(self, current_user: dict) -> PermissionPool:
        role_code = current_user.get("role_code")
        pool = ROLE_POOL_MAP.get(role_code)
        if not pool:
            return PermissionPool(
                name="pool_denied",
                ai_permissions=frozenset(),
                allowed_tools=frozenset(),
                hidden_fields=POOL_KNOWLEDGE.hidden_fields,
            )
        perms = set(current_user.get("perms") or [])
        if role_code == "admin":
            return pool
        if "ai:use" in perms:
            perms |= {"ai:access", "ai:product", "ai:knowledge"}
        # JWT permissions remain authoritative; role pools only cap the maximum.
        return PermissionPool(
            name=pool.name,
            ai_permissions=frozenset(pool.ai_permissions & (perms | {"ai:use"})),
            allowed_tools=pool.allowed_tools,
            hidden_fields=pool.hidden_fields,
            debug=pool.debug and "knowledge:debug" in perms,
        )


def get_permission_pool_resolver() -> PermissionPoolResolver:
    return RoleBasedPoolResolver()
