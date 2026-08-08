"""Enterprise features for VSRS.

Provides authentication, role-based access control (RBAC), audit logging,
API key management, and rate limiting for production deployments.
"""

from __future__ import annotations

from vsrs.enterprise.auth import (
    APIKey,
    APIKeyManager,
    AuthContext,
    User,
)
from vsrs.enterprise.rbac import (
    Permission,
    Role,
    RoleManager,
    has_permission,
)
from vsrs.enterprise.audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
)
from vsrs.enterprise.ratelimit import (
    RateLimitConfig,
    RateLimiter,
    RateLimitResult,
)

__all__ = [
    "APIKey",
    "APIKeyManager",
    "AuditEvent",
    "AuditEventType",
    "AuditLogger",
    "AuthContext",
    "Permission",
    "RateLimitConfig",
    "RateLimitResult",
    "RateLimiter",
    "Role",
    "RoleManager",
    "User",
    "has_permission",
]
