"""Enterprise API routes for VSRS.

Exposes tenant management, SSO, and worker pool functionality
through the REST API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from vsrs.api.auth import require_api_key, require_scope, get_key_manager, get_auditor
from vsrs.enterprise import TenantManager, TenantNotFoundError, ResourceQuota
from vsrs.enterprise.sso import SSOManager

router = APIRouter()


# --- Request/Response models ---


class TenantCreateRequest(BaseModel):
    tenant_id: str = Field(..., description="Unique tenant ID")
    name: str = Field(..., description="Tenant display name")
    slug: str = Field("", description="URL-friendly slug")
    max_projects: int = Field(10, description="Max projects")
    max_runs_per_day: int = Field(100, description="Max runs per day")
    max_concurrent_runs: int = Field(5, description="Max concurrent runs")
    max_storage_mb: int = Field(1024, description="Max storage in MB")
    max_api_keys: int = Field(10, description="Max API keys")


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    created_at: str
    quota: dict[str, Any]


class TenantListResponse(BaseModel):
    tenants: list[TenantResponse]
    count: int


class TenantUsageResponse(BaseModel):
    tenant_id: str
    project_count: int
    runs_today: int
    concurrent_runs: int
    storage_used_mb: float
    api_key_count: int


class ProjectCreateRequest(BaseModel):
    project_id: str = Field(..., description="Unique project ID")
    name: str = Field(..., description="Project display name")
    repo_root: str = Field("", description="Repository root path")


class ProjectResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    repo_root: str
    created_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    count: int


class SSOProviderResponse(BaseModel):
    id: str
    name: str
    protocol: str


class SSOProviderListResponse(BaseModel):
    providers: list[SSOProviderResponse]
    count: int


class SSOSessionResponse(BaseModel):
    id: str
    user_id: str
    provider_id: str
    protocol: str
    expires_at: str | None


class SSOSessionListResponse(BaseModel):
    sessions: list[SSOSessionResponse]
    count: int


class SSOUserResponse(BaseModel):
    id: str
    email: str
    role: str
    active: bool


class SSOUserListResponse(BaseModel):
    users: list[SSOUserResponse]
    count: int


class SSOCleanupResponse(BaseModel):
    removed: int


class PoolStatsResponse(BaseModel):
    worker_count: int
    idle_count: int
    busy_count: int
    unhealthy_count: int
    queue_size: int
    total_capacity: dict[str, Any]
    total_available: dict[str, Any]


# --- Cached managers ---


_tenant_mgr: TenantManager | None = None
_sso_mgr: SSOManager | None = None


def get_tenant_manager() -> TenantManager:
    global _tenant_mgr
    if _tenant_mgr is None:
        _tenant_mgr = TenantManager()
    return _tenant_mgr


def get_sso_manager() -> SSOManager:
    global _sso_mgr
    if _sso_mgr is None:
        _sso_mgr = SSOManager()
    return _sso_mgr


# --- Tenant endpoints ---


@router.post("/tenants", response_model=TenantResponse, dependencies=[Depends(require_scope("tenant:admin"))])
def create_tenant(req: TenantCreateRequest) -> TenantResponse:
    """Create a new tenant with resource quotas."""
    mgr = get_tenant_manager()
    quota = ResourceQuota(
        max_projects=req.max_projects,
        max_runs_per_day=req.max_runs_per_day,
        max_concurrent_runs=req.max_concurrent_runs,
        max_storage_mb=req.max_storage_mb,
        max_api_keys=req.max_api_keys,
    )
    tenant = mgr.create_tenant(req.tenant_id, req.name, req.slug or req.tenant_id, quota=quota)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at.isoformat(),
        quota=quota.to_dict(),
    )


@router.get("/tenants", response_model=TenantListResponse, dependencies=[Depends(require_api_key)])
def list_tenants() -> TenantListResponse:
    """List all tenants."""
    mgr = get_tenant_manager()
    tenants = mgr.list_tenants()
    return TenantListResponse(
        tenants=[
            TenantResponse(
                id=t.id,
                name=t.name,
                slug=t.slug,
                status=t.status.value,
                created_at=t.created_at.isoformat(),
                quota=t.quota.to_dict(),
            )
            for t in tenants
        ],
        count=len(tenants),
    )


@router.get("/tenants/{tenant_id}", response_model=TenantResponse, dependencies=[Depends(require_api_key)])
def get_tenant(tenant_id: str) -> TenantResponse:
    """Get tenant details."""
    mgr = get_tenant_manager()
    try:
        tenant = mgr.get_tenant(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at.isoformat(),
        quota=tenant.quota.to_dict(),
    )


@router.get("/tenants/{tenant_id}/usage", response_model=TenantUsageResponse, dependencies=[Depends(require_api_key)])
def get_tenant_usage(tenant_id: str) -> TenantUsageResponse:
    """Get tenant resource usage."""
    mgr = get_tenant_manager()
    try:
        mgr.get_tenant(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    usage = mgr.get_usage(tenant_id)
    return TenantUsageResponse(
        tenant_id=tenant_id,
        project_count=usage.project_count,
        runs_today=usage.runs_today,
        concurrent_runs=usage.concurrent_runs,
        storage_used_mb=usage.storage_used_mb,
        api_key_count=usage.api_key_count,
    )


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantResponse, dependencies=[Depends(require_scope("tenant:admin"))])
def suspend_tenant(tenant_id: str) -> TenantResponse:
    """Suspend a tenant."""
    mgr = get_tenant_manager()
    try:
        tenant = mgr.suspend_tenant(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at.isoformat(),
        quota=tenant.quota.to_dict(),
    )


@router.post("/tenants/{tenant_id}/reactivate", response_model=TenantResponse, dependencies=[Depends(require_scope("tenant:admin"))])
def reactivate_tenant(tenant_id: str) -> TenantResponse:
    """Reactivate a suspended tenant."""
    mgr = get_tenant_manager()
    try:
        tenant = mgr.reactivate_tenant(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at.isoformat(),
        quota=tenant.quota.to_dict(),
    )


@router.delete("/tenants/{tenant_id}", dependencies=[Depends(require_scope("tenant:admin"))])
def delete_tenant(tenant_id: str) -> dict[str, str]:
    """Delete a tenant and all its projects."""
    mgr = get_tenant_manager()
    try:
        mgr.delete_tenant(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    return {"status": "deleted", "tenant_id": tenant_id}


# --- Project endpoints ---


@router.post("/tenants/{tenant_id}/projects", response_model=ProjectResponse, dependencies=[Depends(require_scope("tenant:admin"))])
def create_project(tenant_id: str, req: ProjectCreateRequest) -> ProjectResponse:
    """Create a project within a tenant."""
    mgr = get_tenant_manager()
    try:
        project = mgr.create_project(req.project_id, tenant_id, req.name, req.repo_root)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ProjectResponse(
        id=project.id,
        tenant_id=project.tenant_id,
        name=project.name,
        repo_root=project.repo_root,
        created_at=project.created_at.isoformat(),
    )


@router.get("/tenants/{tenant_id}/projects", response_model=ProjectListResponse, dependencies=[Depends(require_api_key)])
def list_projects(tenant_id: str) -> ProjectListResponse:
    """List all projects for a tenant."""
    mgr = get_tenant_manager()
    try:
        mgr.get_tenant(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    projects = mgr.list_projects(tenant_id)
    return ProjectListResponse(
        projects=[
            ProjectResponse(
                id=p.id,
                tenant_id=p.tenant_id,
                name=p.name,
                repo_root=p.repo_root,
                created_at=p.created_at.isoformat(),
            )
            for p in projects
        ],
        count=len(projects),
    )


@router.delete("/tenants/{tenant_id}/projects/{project_id}", dependencies=[Depends(require_scope("tenant:admin"))])
def delete_project(tenant_id: str, project_id: str) -> dict[str, str]:
    """Delete a project from a tenant."""
    mgr = get_tenant_manager()
    try:
        mgr.get_tenant(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    mgr.delete_project(project_id)
    return {"status": "deleted", "project_id": project_id}


# --- SSO endpoints ---


@router.get("/sso/providers", response_model=SSOProviderListResponse, dependencies=[Depends(require_api_key)])
def list_sso_providers() -> SSOProviderListResponse:
    """List configured SSO providers."""
    mgr = get_sso_manager()
    providers = mgr.list_providers()
    return SSOProviderListResponse(
        providers=[
            SSOProviderResponse(id=p["id"], name=p["name"], protocol=p["protocol"])
            for p in providers
        ],
        count=len(providers),
    )


@router.get("/sso/sessions", response_model=SSOSessionListResponse, dependencies=[Depends(require_api_key)])
def list_sso_sessions() -> SSOSessionListResponse:
    """List active SSO sessions."""
    mgr = get_sso_manager()
    sessions = mgr.list_active_sessions()
    return SSOSessionListResponse(
        sessions=[
            SSOSessionResponse(
                id=s.id,
                user_id=s.user_id,
                provider_id=s.provider_id,
                protocol=s.protocol.value,
                expires_at=s.expires_at.isoformat() if s.expires_at else None,
            )
            for s in sessions
        ],
        count=len(sessions),
    )


@router.get("/sso/users", response_model=SSOUserListResponse, dependencies=[Depends(require_api_key)])
def list_sso_users() -> SSOUserListResponse:
    """List SSO-provisioned users."""
    mgr = get_sso_manager()
    users = mgr.list_users()
    return SSOUserListResponse(
        users=[
            SSOUserResponse(id=u.id, email=u.email, role=u.role, active=u.active)
            for u in users
        ],
        count=len(users),
    )


@router.post("/sso/cleanup", response_model=SSOCleanupResponse, dependencies=[Depends(require_scope("sso:admin"))])
def cleanup_sso_sessions() -> SSOCleanupResponse:
    """Remove expired SSO sessions."""
    mgr = get_sso_manager()
    removed = mgr.cleanup_expired_sessions()
    return SSOCleanupResponse(removed=removed)


# --- Pool endpoints ---


@router.get("/pool/stats", response_model=PoolStatsResponse, dependencies=[Depends(require_api_key)])
def get_pool_stats() -> PoolStatsResponse:
    """Get worker pool statistics.

    Returns current pool state if a pool is active, or zeros otherwise.
    """
    from vsrs.distributed import WorkerPool

    # In a real deployment, the pool would be a shared singleton.
    # For now, return a default empty stats response.
    return PoolStatsResponse(
        worker_count=0,
        idle_count=0,
        busy_count=0,
        unhealthy_count=0,
        queue_size=0,
        total_capacity={"cpu": 0.0, "memory_mb": 0, "gpu": 0, "disk_mb": 0},
        total_available={"cpu": 0.0, "memory_mb": 0, "gpu": 0, "disk_mb": 0},
    )


# --- API Key Management endpoints ---


class APIKeyCreateRequest(BaseModel):
    user_id: str = Field(..., description="User ID for this key")
    name: str = Field("", description="Human-readable key name")
    scopes: list[str] = Field(default_factory=list, description="Permission scopes")


class APIKeyResponse(BaseModel):
    id: str
    user_id: str
    name: str
    scopes: list[str]
    valid: bool
    created_at: str
    expires_at: str | None = None


class APIKeyCreateResponse(BaseModel):
    key: APIKeyResponse
    raw_key: str


class APIKeyListResponse(BaseModel):
    keys: list[APIKeyResponse]
    count: int


class APIKeyCountResponse(BaseModel):
    count: int


class APIKeyRevokeResponse(BaseModel):
    revoked: bool
    key_id: str


@router.post("/keys", response_model=APIKeyCreateResponse, dependencies=[Depends(require_scope("key:admin"))])
def create_api_key(req: APIKeyCreateRequest) -> APIKeyCreateResponse:
    """Create a new API key. Requires key:admin scope."""
    mgr = get_key_manager()
    raw_key, api_key = mgr.create_key(user_id=req.user_id, name=req.name, scopes=req.scopes)
    return APIKeyCreateResponse(
        key=APIKeyResponse(
            id=api_key.id,
            user_id=api_key.user_id,
            name=api_key.name,
            scopes=api_key.scopes,
            valid=api_key.is_valid,
            created_at=api_key.created_at.isoformat(),
            expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
        ),
        raw_key=raw_key,
    )


@router.get("/keys", response_model=APIKeyListResponse, dependencies=[Depends(require_api_key)])
def list_api_keys(user_id: str | None = None) -> APIKeyListResponse:
    """List API keys, optionally filtered by user. Requires valid API key."""
    mgr = get_key_manager()
    keys = mgr.list_keys(user_id=user_id)
    return APIKeyListResponse(
        keys=[
            APIKeyResponse(
                id=k.id,
                user_id=k.user_id,
                name=k.name,
                scopes=k.scopes,
                valid=k.is_valid,
                created_at=k.created_at.isoformat(),
                expires_at=k.expires_at.isoformat() if k.expires_at else None,
            )
            for k in keys
        ],
        count=len(keys),
    )


@router.get("/keys/count", response_model=APIKeyCountResponse, dependencies=[Depends(require_api_key)])
def count_api_keys() -> APIKeyCountResponse:
    """Count total API keys. Requires valid API key."""
    mgr = get_key_manager()
    return APIKeyCountResponse(count=mgr.count())


@router.delete("/keys/{key_id}", response_model=APIKeyRevokeResponse, dependencies=[Depends(require_scope("key:admin"))])
def revoke_api_key(key_id: str) -> APIKeyRevokeResponse:
    """Revoke an API key. Requires key:admin scope."""
    mgr = get_key_manager()
    revoked = mgr.revoke(key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"API key not found: {key_id}")
    return APIKeyRevokeResponse(revoked=True, key_id=key_id)


# --- Audit Log endpoints ---


class AuditEventResponse(BaseModel):
    event_type: str
    user_id: str
    resource: str
    action: str
    success: bool
    timestamp: str
    details: dict[str, Any]
    ip_address: str
    request_id: str


class AuditListResponse(BaseModel):
    events: list[AuditEventResponse]
    count: int


class AuditCountResponse(BaseModel):
    count: int


@router.get("/audit", response_model=AuditListResponse, dependencies=[Depends(require_api_key)])
def list_audit_events(
    event_type: str | None = None,
    user_id: str | None = None,
    resource: str | None = None,
    limit: int = 100,
) -> AuditListResponse:
    """Query audit events with filters. Requires valid API key."""
    auditor = get_auditor()
    events = auditor.query(
        event_type=event_type,
        user_id=user_id,
        resource=resource,
        limit=limit,
    )
    return AuditListResponse(
        events=[
            AuditEventResponse(
                event_type=e.event_type,
                user_id=e.user_id,
                resource=e.resource,
                action=e.action,
                success=e.success,
                timestamp=e.timestamp.isoformat(),
                details=e.details,
                ip_address=e.ip_address,
                request_id=e.request_id,
            )
            for e in events
        ],
        count=len(events),
    )


@router.get("/audit/count", response_model=AuditCountResponse, dependencies=[Depends(require_api_key)])
def count_audit_events() -> AuditCountResponse:
    """Count total audit events. Requires valid API key."""
    auditor = get_auditor()
    return AuditCountResponse(count=auditor.count())
