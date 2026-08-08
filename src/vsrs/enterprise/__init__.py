"""Enterprise features for VSRS.

Provides authentication, role-based access control (RBAC), audit logging,
API key management, rate limiting, and multi-tenant project isolation
for production deployments.
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
from vsrs.enterprise.tenant import (
    Project,
    QuotaExceededError,
    ResourceQuota,
    Tenant,
    TenantManager,
    TenantNotFoundError,
    TenantStatus,
    UsageRecord,
)

__all__ = [
    "APIKey",
    "APIKeyManager",
    "AuditEvent",
    "AuditEventType",
    "AuditLogger",
    "AuthContext",
    "Permission",
    "Project",
    "QuotaExceededError",
    "RateLimitConfig",
    "RateLimitResult",
    "RateLimiter",
    "ResourceQuota",
    "Role",
    "RoleManager",
    "Tenant",
    "TenantManager",
    "TenantNotFoundError",
    "TenantStatus",
    "UsageRecord",
    "User",
    "has_permission",
]
