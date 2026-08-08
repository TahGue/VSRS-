"""Role-based access control (RBAC).

Defines roles, permissions, and a role manager for checking access.
Supports hierarchical roles and custom permission definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vsrs.core.logging import get_logger

logger = get_logger("enterprise.rbac")


class Permission(str, Enum):
    """System permissions."""

    # Task permissions
    task_create = "task:create"
    task_read = "task:read"
    task_update = "task:update"
    task_delete = "task:delete"

    # Verification permissions
    verify_run = "verify:run"
    verify_read = "verify:read"

    # Repair permissions
    repair_run = "repair:run"
    repair_read = "repair:read"

    # Benchmark/eval permissions
    benchmark_run = "benchmark:run"
    benchmark_read = "benchmark:read"

    # Admin permissions
    admin_users = "admin:users"
    admin_keys = "admin:keys"
    admin_config = "admin:config"
    admin_all = "admin:all"


@dataclass
class Role:
    """A role with associated permissions.

    Attributes:
        name: Unique role name.
        description: Human-readable description.
        permissions: Set of permission strings.
        parent: Optional parent role for inheritance.
    """

    name: str
    description: str = ""
    permissions: set[str] = field(default_factory=set)
    parent: str | None = None

    def has(self, permission: str) -> bool:
        """Check if this role has a specific permission."""
        return permission in self.permissions

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": sorted(self.permissions),
            "parent": self.parent,
        }


class RoleManager:
    """Manages roles and permission checking.

    Provides role registration, inheritance resolution, and
    permission checking for users.
    """

    # Built-in roles with default permissions
    BUILTIN_ROLES: dict[str, set[str]] = {
        "viewer": {
            Permission.task_read.value,
            Permission.verify_read.value,
            Permission.repair_read.value,
            Permission.benchmark_read.value,
        },
        "developer": {
            Permission.task_create.value,
            Permission.task_read.value,
            Permission.task_update.value,
            Permission.verify_run.value,
            Permission.verify_read.value,
            Permission.repair_run.value,
            Permission.repair_read.value,
            Permission.benchmark_run.value,
            Permission.benchmark_read.value,
        },
        "admin": {
            Permission.task_create.value,
            Permission.task_read.value,
            Permission.task_update.value,
            Permission.task_delete.value,
            Permission.verify_run.value,
            Permission.verify_read.value,
            Permission.repair_run.value,
            Permission.repair_read.value,
            Permission.benchmark_run.value,
            Permission.benchmark_read.value,
            Permission.admin_users.value,
            Permission.admin_keys.value,
            Permission.admin_config.value,
            Permission.admin_all.value,
        },
    }

    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in roles."""
        for name, perms in self.BUILTIN_ROLES.items():
            descriptions = {
                "viewer": "Read-only access to tasks and results",
                "developer": "Create tasks, run verification and repair",
                "admin": "Full access including user and key management",
            }
            self._roles[name] = Role(
                name=name,
                description=descriptions.get(name, ""),
                permissions=set(perms),
            )

    def register(self, role: Role) -> None:
        """Register a custom role."""
        self._roles[role.name] = role
        logger.info(f"Registered role '{role.name}' with {len(role.permissions)} permissions")

    def get(self, name: str) -> Role | None:
        """Get a role by name."""
        return self._roles.get(name)

    def list_roles(self) -> list[Role]:
        """List all registered roles."""
        return list(self._roles.values())

    def resolve_permissions(self, role_name: str) -> set[str]:
        """Resolve all permissions for a role, including inherited.

        Args:
            role_name: Name of the role.

        Returns:
            Set of all permission strings (including inherited).
        """
        role = self._roles.get(role_name)
        if role is None:
            return set()

        permissions = set(role.permissions)

        # Resolve parent inheritance
        if role.parent:
            parent_perms = self.resolve_permissions(role.parent)
            permissions.update(parent_perms)

        return permissions

    def check(self, role_name: str, permission: str) -> bool:
        """Check if a role has a specific permission.

        Args:
            role_name: Name of the role to check.
            permission: Permission string to check.

        Returns:
            True if the role has the permission (including inherited).
        """
        permissions = self.resolve_permissions(role_name)
        return permission in permissions

    def count(self) -> int:
        """Get the number of registered roles."""
        return len(self._roles)


def has_permission(
    role_name: str,
    permission: str | Permission,
    manager: RoleManager | None = None,
) -> bool:
    """Convenience function to check a permission.

    Args:
        role_name: Role to check.
        permission: Permission to check (string or Permission enum).
        manager: Optional RoleManager (creates default if None).

    Returns:
        True if the role has the permission.
    """
    if manager is None:
        manager = RoleManager()
    perm_str = permission.value if isinstance(permission, Permission) else permission
    return manager.check(role_name, perm_str)
