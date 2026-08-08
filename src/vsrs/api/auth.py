"""API authentication middleware for VSRS.

Provides FastAPI dependency for API key validation, RBAC permission
checking, and rate limiting on protected endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from vsrs.enterprise import (
    APIKeyManager,
    AuditEventType,
    AuditLogger,
    Permission,
    RateLimitConfig,
    RateLimiter,
    RoleManager,
)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_key_mgr: APIKeyManager | None = None
_role_mgr: RoleManager | None = None
_rate_limiter: RateLimiter | None = None
_auditor: AuditLogger | None = None


def get_key_manager() -> APIKeyManager:
    global _key_mgr
    if _key_mgr is None:
        _key_mgr = APIKeyManager()
    return _key_mgr


def get_role_manager() -> RoleManager:
    global _role_mgr
    if _role_mgr is None:
        _role_mgr = RoleManager()
    return _role_mgr


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(RateLimitConfig())
    return _rate_limiter


def get_auditor() -> AuditLogger:
    global _auditor
    if _auditor is None:
        _auditor = AuditLogger()
    return _auditor


def reset_managers() -> None:
    """Reset all cached managers (for testing)."""
    global _key_mgr, _role_mgr, _rate_limiter, _auditor
    _key_mgr = None
    _role_mgr = None
    _rate_limiter = None
    _auditor = None


def require_api_key(
    api_key: str | None = Depends(_api_key_header),
) -> dict[str, Any]:
    """Dependency that requires a valid API key.

    Returns a dict with key_id, user_id, and scopes.
    Raises 401 if no key or invalid key.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )

    mgr = get_key_manager()
    key = mgr.validate(api_key)
    if key is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key.",
        )

    # Rate limit check
    limiter = get_rate_limiter()
    result = limiter.check(key.id)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {result.retry_after:.1f}s.",
            headers={"Retry-After": str(int(result.retry_after) + 1)},
        )

    # Audit the validation
    auditor = get_auditor()
    auditor.log_event(
        event_type=AuditEventType.auth_key_validate,
        user_id=key.user_id,
        resource=f"api-key/{key.id}",
        success=True,
    )

    return {
        "key_id": key.id,
        "user_id": key.user_id,
        "scopes": key.scopes,
    }


def require_permission(permission: str):
    """Dependency factory that requires a specific permission.

    Usage:
        @router.get("/protected", dependencies=[Depends(require_permission("task:read"))])
    """
    def _check(auth: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
        role_mgr = get_role_manager()
        # For API key auth, we don't have a role directly.
        # The scopes on the API key act as permissions.
        if permission in auth["scopes"] or "admin:all" in auth["scopes"]:
            return auth

        # Check if any built-in role grants this permission
        # (API keys may not have explicit scopes but the user's role might)
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied. Required: {permission}",
        )

    return _check


def require_scope(scope: str):
    """Dependency factory that requires a specific API key scope.

    Usage:
        @router.post("/tenant", dependencies=[Depends(require_scope("tenant:admin"))])
    """
    def _check(auth: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
        if scope in auth["scopes"] or "admin:all" in auth["scopes"]:
            return auth
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient scope. Required: {scope}",
        )

    return _check
