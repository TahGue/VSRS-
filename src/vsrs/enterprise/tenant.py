"""Multi-tenant project isolation for VSRS.

Provides tenant management, project scoping, and resource quotas so that
multiple teams can share a single VSRS instance with isolated data and
configurable limits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from vsrs.core.logging import get_logger

logger = get_logger("enterprise.tenant")


class TenantStatus(str, Enum):
    """Status of a tenant."""

    active = "active"
    suspended = "suspended"
    deleted = "deleted"


@dataclass
class ResourceQuota:
    """Resource limits for a tenant.

    Attributes:
        max_projects: Maximum number of projects.
        max_runs_per_day: Maximum runs per day.
        max_concurrent_runs: Maximum concurrent runs.
        max_storage_mb: Maximum storage in MB.
        max_api_keys: Maximum API keys per tenant.
    """

    max_projects: int = 10
    max_runs_per_day: int = 100
    max_concurrent_runs: int = 5
    max_storage_mb: int = 1024
    max_api_keys: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_projects": self.max_projects,
            "max_runs_per_day": self.max_runs_per_day,
            "max_concurrent_runs": self.max_concurrent_runs,
            "max_storage_mb": self.max_storage_mb,
            "max_api_keys": self.max_api_keys,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceQuota:
        return cls(
            max_projects=data.get("max_projects", 10),
            max_runs_per_day=data.get("max_runs_per_day", 100),
            max_concurrent_runs=data.get("max_concurrent_runs", 5),
            max_storage_mb=data.get("max_storage_mb", 1024),
            max_api_keys=data.get("max_api_keys", 10),
        )

    @classmethod
    def unlimited(cls) -> ResourceQuota:
        """Create a quota with no limits."""
        return cls(
            max_projects=-1,
            max_runs_per_day=-1,
            max_concurrent_runs=-1,
            max_storage_mb=-1,
            max_api_keys=-1,
        )


@dataclass
class Tenant:
    """A tenant in the multi-tenant system.

    Each tenant has isolated projects, users, and resources.

    Attributes:
        id: Unique tenant identifier.
        name: Display name.
        slug: URL-friendly identifier.
        status: Current status.
        quota: Resource limits.
        created_at: Creation timestamp.
        metadata: Additional tenant metadata.
    """

    id: str
    name: str
    slug: str
    status: TenantStatus = TenantStatus.active
    quota: ResourceQuota = field(default_factory=ResourceQuota)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status.value,
            "quota": self.quota.to_dict(),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tenant:
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            status=TenantStatus(data.get("status", "active")),
            quota=ResourceQuota.from_dict(data.get("quota", {})),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.active


@dataclass
class Project:
    """A project within a tenant.

    Projects provide isolation within a tenant — each has its own
    repository, tasks, and runs.

    Attributes:
        id: Unique project identifier.
        tenant_id: Owning tenant.
        name: Display name.
        repo_root: Repository root path.
        created_at: Creation timestamp.
        metadata: Additional project metadata.
    """

    id: str
    tenant_id: str
    name: str
    repo_root: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "repo_root": self.repo_root,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        return cls(
            id=data["id"],
            tenant_id=data["tenant_id"],
            name=data["name"],
            repo_root=data.get("repo_root", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )


@dataclass
class UsageRecord:
    """Tracks resource usage for a tenant.

    Attributes:
        tenant_id: The tenant this usage belongs to.
        date: Date string (YYYY-MM-DD) for daily tracking.
        runs_today: Number of runs today.
        concurrent_runs: Current concurrent runs.
        storage_used_mb: Storage used in MB.
        project_count: Number of projects.
        api_key_count: Number of API keys.
    """

    tenant_id: str
    date: str = ""
    runs_today: int = 0
    concurrent_runs: int = 0
    storage_used_mb: float = 0.0
    project_count: int = 0
    api_key_count: int = 0

    def __post_init__(self) -> None:
        if not self.date:
            self.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "date": self.date,
            "runs_today": self.runs_today,
            "concurrent_runs": self.concurrent_runs,
            "storage_used_mb": self.storage_used_mb,
            "project_count": self.project_count,
            "api_key_count": self.api_key_count,
        }


class QuotaExceededError(Exception):
    """Raised when a tenant exceeds their resource quota."""

    def __init__(self, tenant_id: str, resource: str, limit: int, current: int) -> None:
        self.tenant_id = tenant_id
        self.resource = resource
        self.limit = limit
        self.current = current
        super().__init__(
            f"Quota exceeded for tenant '{tenant_id}': "
            f"{resource} limit is {limit}, current usage is {current}"
        )


class TenantNotFoundError(Exception):
    """Raised when a tenant is not found."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant not found: {tenant_id}")


class TenantManager:
    """Manages tenants, projects, and resource quotas.

    Provides CRUD operations for tenants and projects, quota enforcement,
    and usage tracking.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._projects: dict[str, Project] = {}
        self._projects_by_tenant: dict[str, list[str]] = {}
        self._usage: dict[str, UsageRecord] = {}
        self._run_timestamps: dict[str, list[float]] = {}

    # --- Tenant CRUD ---

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        slug: str,
        quota: ResourceQuota | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Tenant:
        """Create a new tenant."""
        if tenant_id in self._tenants:
            raise ValueError(f"Tenant already exists: {tenant_id}")

        tenant = Tenant(
            id=tenant_id,
            name=name,
            slug=slug,
            quota=quota or ResourceQuota(),
            metadata=metadata or {},
        )
        self._tenants[tenant_id] = tenant
        self._projects_by_tenant[tenant_id] = []
        self._usage[tenant_id] = UsageRecord(tenant_id=tenant_id)
        self._run_timestamps[tenant_id] = []

        logger.info(f"Tenant created: {tenant_id} ({name})")
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant:
        """Get a tenant by ID."""
        if tenant_id not in self._tenants:
            raise TenantNotFoundError(tenant_id)
        return self._tenants[tenant_id]

    def list_tenants(self) -> list[Tenant]:
        """List all tenants."""
        return list(self._tenants.values())

    def update_tenant(
        self,
        tenant_id: str,
        name: str | None = None,
        status: TenantStatus | None = None,
        quota: ResourceQuota | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Tenant:
        """Update a tenant's attributes."""
        tenant = self.get_tenant(tenant_id)
        if name is not None:
            tenant.name = name
        if status is not None:
            tenant.status = status
        if quota is not None:
            tenant.quota = quota
        if metadata is not None:
            tenant.metadata.update(metadata)
        logger.info(f"Tenant updated: {tenant_id}")
        return tenant

    def delete_tenant(self, tenant_id: str) -> None:
        """Delete a tenant and all its projects."""
        self.get_tenant(tenant_id)  # Raises if not found
        project_ids = self._projects_by_tenant.pop(tenant_id, [])
        for pid in project_ids:
            self._projects.pop(pid, None)
        self._tenants.pop(tenant_id)
        self._usage.pop(tenant_id, None)
        self._run_timestamps.pop(tenant_id, None)
        logger.info(f"Tenant deleted: {tenant_id}")

    def suspend_tenant(self, tenant_id: str) -> Tenant:
        """Suspend a tenant."""
        return self.update_tenant(tenant_id, status=TenantStatus.suspended)

    def reactivate_tenant(self, tenant_id: str) -> Tenant:
        """Reactivate a suspended tenant."""
        return self.update_tenant(tenant_id, status=TenantStatus.active)

    # --- Project CRUD ---

    def create_project(
        self,
        project_id: str,
        tenant_id: str,
        name: str,
        repo_root: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Project:
        """Create a new project within a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant.is_active:
            raise ValueError(f"Tenant '{tenant_id}' is not active")

        # Check quota
        usage = self._get_usage(tenant_id)
        self._check_quota(tenant_id, "projects", tenant.quota.max_projects, usage.project_count)

        if project_id in self._projects:
            raise ValueError(f"Project already exists: {project_id}")

        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name=name,
            repo_root=repo_root,
            metadata=metadata or {},
        )
        self._projects[project_id] = project
        self._projects_by_tenant.setdefault(tenant_id, []).append(project_id)
        usage.project_count += 1

        logger.info(f"Project created: {project_id} (tenant: {tenant_id})")
        return project

    def get_project(self, project_id: str) -> Project:
        """Get a project by ID."""
        if project_id not in self._projects:
            raise KeyError(f"Project not found: {project_id}")
        return self._projects[project_id]

    def list_projects(self, tenant_id: str) -> list[Project]:
        """List all projects for a tenant."""
        self.get_tenant(tenant_id)  # Raises if not found
        project_ids = self._projects_by_tenant.get(tenant_id, [])
        return [self._projects[pid] for pid in project_ids if pid in self._projects]

    def delete_project(self, project_id: str) -> None:
        """Delete a project."""
        project = self.get_project(project_id)
        tenant_id = project.tenant_id
        self._projects.pop(project_id)
        if tenant_id in self._projects_by_tenant:
            self._projects_by_tenant[tenant_id] = [
                pid for pid in self._projects_by_tenant[tenant_id] if pid != project_id
            ]
        usage = self._get_usage(tenant_id)
        usage.project_count = max(0, usage.project_count - 1)
        logger.info(f"Project deleted: {project_id}")

    def get_project_tenant(self, project_id: str) -> str:
        """Get the tenant ID for a project."""
        return self.get_project(project_id).tenant_id

    # --- Quota enforcement ---

    def _get_usage(self, tenant_id: str) -> UsageRecord:
        """Get or create usage record for a tenant."""
        if tenant_id not in self._usage:
            self._usage[tenant_id] = UsageRecord(tenant_id=tenant_id)
        usage = self._usage[tenant_id]

        # Reset daily counters if date changed
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if usage.date != today:
            usage.date = today
            usage.runs_today = 0
            self._run_timestamps[tenant_id] = []

        return usage

    def _check_quota(self, tenant_id: str, resource: str, limit: int, current: int) -> None:
        """Check if a resource usage is within quota."""
        if limit < 0:
            return  # Unlimited
        if current >= limit:
            raise QuotaExceededError(tenant_id, resource, limit, current)

    def check_run_allowed(self, tenant_id: str) -> None:
        """Check if a tenant can start a new run. Raises QuotaExceededError if not."""
        tenant = self.get_tenant(tenant_id)
        if not tenant.is_active:
            raise ValueError(f"Tenant '{tenant_id}' is not active")

        usage = self._get_usage(tenant_id)
        quota = tenant.quota

        # Check daily run limit
        self._check_quota(tenant_id, "runs_per_day", quota.max_runs_per_day, usage.runs_today)

        # Check concurrent runs
        self._check_quota(tenant_id, "concurrent_runs", quota.max_concurrent_runs, usage.concurrent_runs)

    def record_run_start(self, tenant_id: str) -> None:
        """Record that a run has started."""
        usage = self._get_usage(tenant_id)
        usage.runs_today += 1
        usage.concurrent_runs += 1
        self._run_timestamps.setdefault(tenant_id, []).append(time.time())
        logger.debug(f"Run started for tenant {tenant_id}: runs_today={usage.runs_today}")

    def record_run_end(self, tenant_id: str) -> None:
        """Record that a run has ended."""
        usage = self._get_usage(tenant_id)
        usage.concurrent_runs = max(0, usage.concurrent_runs - 1)
        logger.debug(f"Run ended for tenant {tenant_id}: concurrent={usage.concurrent_runs}")

    def record_storage(self, tenant_id: str, storage_mb: float) -> None:
        """Record storage usage for a tenant."""
        usage = self._get_usage(tenant_id)
        usage.storage_used_mb = storage_mb

    def check_storage_allowed(self, tenant_id: str, additional_mb: float = 0) -> None:
        """Check if storage usage is within quota."""
        tenant = self.get_tenant(tenant_id)
        usage = self._get_usage(tenant_id)
        total = usage.storage_used_mb + additional_mb
        self._check_quota(tenant_id, "storage_mb", tenant.quota.max_storage_mb, int(total))

    def check_api_key_allowed(self, tenant_id: str) -> None:
        """Check if tenant can create another API key."""
        tenant = self.get_tenant(tenant_id)
        usage = self._get_usage(tenant_id)
        self._check_quota(tenant_id, "api_keys", tenant.quota.max_api_keys, usage.api_key_count)

    def record_api_key_created(self, tenant_id: str) -> None:
        """Record that an API key was created."""
        usage = self._get_usage(tenant_id)
        usage.api_key_count += 1

    def record_api_key_revoked(self, tenant_id: str) -> None:
        """Record that an API key was revoked."""
        usage = self._get_usage(tenant_id)
        usage.api_key_count = max(0, usage.api_key_count - 1)

    def get_usage(self, tenant_id: str) -> UsageRecord:
        """Get current usage for a tenant."""
        return self._get_usage(tenant_id)

    def get_usage_summary(self, tenant_id: str) -> dict[str, Any]:
        """Get a usage summary with quota info."""
        tenant = self.get_tenant(tenant_id)
        usage = self._get_usage(tenant_id)
        quota = tenant.quota
        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "tenant_status": tenant.status.value,
            "usage": usage.to_dict(),
            "quota": quota.to_dict(),
            "limits": {
                "projects": {
                    "used": usage.project_count,
                    "limit": quota.max_projects,
                    "remaining": max(0, quota.max_projects - usage.project_count) if quota.max_projects >= 0 else -1,
                },
                "runs_today": {
                    "used": usage.runs_today,
                    "limit": quota.max_runs_per_day,
                    "remaining": max(0, quota.max_runs_per_day - usage.runs_today) if quota.max_runs_per_day >= 0 else -1,
                },
                "concurrent_runs": {
                    "used": usage.concurrent_runs,
                    "limit": quota.max_concurrent_runs,
                    "remaining": max(0, quota.max_concurrent_runs - usage.concurrent_runs) if quota.max_concurrent_runs >= 0 else -1,
                },
                "storage_mb": {
                    "used": usage.storage_used_mb,
                    "limit": quota.max_storage_mb,
                    "remaining": max(0, quota.max_storage_mb - usage.storage_used_mb) if quota.max_storage_mb >= 0 else -1,
                },
                "api_keys": {
                    "used": usage.api_key_count,
                    "limit": quota.max_api_keys,
                    "remaining": max(0, quota.max_api_keys - usage.api_key_count) if quota.max_api_keys >= 0 else -1,
                },
            },
        }
