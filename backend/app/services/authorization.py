from enum import StrEnum

from app.core.errors import ForbiddenError


class Permission(StrEnum):
    BUSINESS_READ = "business:read"
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    CATALOG_READ = "catalog:read"
    CATALOG_WRITE = "catalog:write"
    INVENTORY_READ = "inventory:read"
    INVENTORY_WRITE = "inventory:write"
    SALES_READ = "sales:read"
    SALES_WRITE = "sales:write"
    PROCUREMENT_READ = "procurement:read"
    PROCUREMENT_WRITE = "procurement:write"
    FINANCE_READ = "finance:read"
    FINANCE_WRITE = "finance:write"
    INSIGHTS_READ = "insights:read"
    INSIGHTS_WRITE = "insights:write"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": frozenset(Permission),
    "manager": frozenset(Permission),
    "staff": frozenset(
        {
            Permission.BUSINESS_READ,
            Permission.CATALOG_READ,
            Permission.INVENTORY_READ,
            Permission.INVENTORY_WRITE,
            Permission.SALES_READ,
            Permission.SALES_WRITE,
        }
    ),
    "analyst": frozenset(
        {
            Permission.BUSINESS_READ,
            Permission.CATALOG_READ,
            Permission.INVENTORY_READ,
            Permission.SALES_READ,
            Permission.FINANCE_READ,
            Permission.PROCUREMENT_READ,
            Permission.INSIGHTS_READ,
        }
    ),
}


def ensure_permission(role: str, permission: Permission) -> None:
    if permission not in ROLE_PERMISSIONS.get(role, frozenset()):
        raise ForbiddenError("Your role does not allow this action")
