"""Tests for Phase 25: Multi-tenant project isolation.

Tests Tenant, Project, ResourceQuota, UsageRecord, TenantManager,
quota enforcement, and isolation between tenants.
"""

import pytest
from datetime import datetime, timezone

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


# --- ResourceQuota tests ---

class TestResourceQuota:
    def test_defaults(self):
        q = ResourceQuota()
        assert q.max_projects == 10
        assert q.max_runs_per_day == 100
        assert q.max_concurrent_runs == 5
        assert q.max_storage_mb == 1024
        assert q.max_api_keys == 10

    def test_unlimited(self):
        q = ResourceQuota.unlimited()
        assert q.max_projects == -1
        assert q.max_runs_per_day == -1
        assert q.max_concurrent_runs == -1
        assert q.max_storage_mb == -1
        assert q.max_api_keys == -1

    def test_to_dict(self):
        q = ResourceQuota(max_projects=5, max_runs_per_day=50)
        d = q.to_dict()
        assert d["max_projects"] == 5
        assert d["max_runs_per_day"] == 50

    def test_from_dict(self):
        d = {"max_projects": 3, "max_runs_per_day": 20, "max_concurrent_runs": 2}
        q = ResourceQuota.from_dict(d)
        assert q.max_projects == 3
        assert q.max_runs_per_day == 20
        assert q.max_concurrent_runs == 2

    def test_from_dict_defaults(self):
        q = ResourceQuota.from_dict({})
        assert q.max_projects == 10
        assert q.max_runs_per_day == 100

    def test_roundtrip(self):
        q = ResourceQuota(max_projects=7, max_api_keys=3)
        q2 = ResourceQuota.from_dict(q.to_dict())
        assert q2.max_projects == 7
        assert q2.max_api_keys == 3


# --- Tenant tests ---

class TestTenant:
    def test_create(self):
        t = Tenant(id="t1", name="Acme", slug="acme")
        assert t.id == "t1"
        assert t.name == "Acme"
        assert t.slug == "acme"
        assert t.status == TenantStatus.active
        assert isinstance(t.quota, ResourceQuota)
        assert t.is_active

    def test_to_dict(self):
        t = Tenant(id="t1", name="Acme", slug="acme")
        d = t.to_dict()
        assert d["id"] == "t1"
        assert d["name"] == "Acme"
        assert d["slug"] == "acme"
        assert d["status"] == "active"
        assert "quota" in d
        assert "created_at" in d

    def test_from_dict(self):
        d = {
            "id": "t1",
            "name": "Acme",
            "slug": "acme",
            "status": "suspended",
            "quota": {"max_projects": 3},
        }
        t = Tenant.from_dict(d)
        assert t.id == "t1"
        assert t.status == TenantStatus.suspended
        assert t.quota.max_projects == 3
        assert not t.is_active

    def test_suspended_not_active(self):
        t = Tenant(id="t1", name="Acme", slug="acme", status=TenantStatus.suspended)
        assert not t.is_active

    def test_deleted_not_active(self):
        t = Tenant(id="t1", name="Acme", slug="acme", status=TenantStatus.deleted)
        assert not t.is_active


# --- Project tests ---

class TestProject:
    def test_create(self):
        p = Project(id="p1", tenant_id="t1", name="Web App")
        assert p.id == "p1"
        assert p.tenant_id == "t1"
        assert p.name == "Web App"
        assert p.repo_root == ""

    def test_to_dict(self):
        p = Project(id="p1", tenant_id="t1", name="Web App", repo_root="/repo")
        d = p.to_dict()
        assert d["id"] == "p1"
        assert d["tenant_id"] == "t1"
        assert d["repo_root"] == "/repo"

    def test_from_dict(self):
        d = {"id": "p1", "tenant_id": "t1", "name": "App", "repo_root": "/r"}
        p = Project.from_dict(d)
        assert p.id == "p1"
        assert p.tenant_id == "t1"


# --- UsageRecord tests ---

class TestUsageRecord:
    def test_defaults(self):
        u = UsageRecord(tenant_id="t1")
        assert u.tenant_id == "t1"
        assert u.runs_today == 0
        assert u.concurrent_runs == 0
        assert u.date  # Auto-populated

    def test_to_dict(self):
        u = UsageRecord(tenant_id="t1", runs_today=5, concurrent_runs=2)
        d = u.to_dict()
        assert d["runs_today"] == 5
        assert d["concurrent_runs"] == 2


# --- TenantManager: Tenant CRUD ---

class TestTenantManagerCRUD:
    def test_create_tenant(self):
        mgr = TenantManager()
        t = mgr.create_tenant("t1", "Acme", "acme")
        assert t.id == "t1"
        assert t.name == "Acme"
        assert t.is_active

    def test_create_duplicate_raises(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        with pytest.raises(ValueError, match="already exists"):
            mgr.create_tenant("t1", "Other", "other")

    def test_get_tenant(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        t = mgr.get_tenant("t1")
        assert t.name == "Acme"

    def test_get_tenant_not_found(self):
        mgr = TenantManager()
        with pytest.raises(TenantNotFoundError):
            mgr.get_tenant("nonexistent")

    def test_list_tenants(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_tenant("t2", "Globex", "globex")
        tenants = mgr.list_tenants()
        assert len(tenants) == 2

    def test_update_tenant(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        t = mgr.update_tenant("t1", name="Acme Inc.")
        assert t.name == "Acme Inc."

    def test_update_tenant_quota(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        new_quota = ResourceQuota(max_projects=20)
        t = mgr.update_tenant("t1", quota=new_quota)
        assert t.quota.max_projects == 20

    def test_suspend_tenant(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        t = mgr.suspend_tenant("t1")
        assert t.status == TenantStatus.suspended
        assert not t.is_active

    def test_reactivate_tenant(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.suspend_tenant("t1")
        t = mgr.reactivate_tenant("t1")
        assert t.status == TenantStatus.active
        assert t.is_active

    def test_delete_tenant(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App")
        mgr.delete_tenant("t1")
        with pytest.raises(TenantNotFoundError):
            mgr.get_tenant("t1")

    def test_delete_tenant_removes_projects(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App")
        mgr.create_project("p2", "t1", "API")
        mgr.delete_tenant("t1")
        with pytest.raises(KeyError):
            mgr.get_project("p1")


# --- TenantManager: Project CRUD ---

class TestTenantManagerProjects:
    def test_create_project(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        p = mgr.create_project("p1", "t1", "Web App", "/repo")
        assert p.id == "p1"
        assert p.tenant_id == "t1"
        assert p.repo_root == "/repo"

    def test_create_project_duplicate(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App")
        with pytest.raises(ValueError, match="already exists"):
            mgr.create_project("p1", "t1", "Other")

    def test_create_project_suspended_tenant(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.suspend_tenant("t1")
        with pytest.raises(ValueError, match="not active"):
            mgr.create_project("p1", "t1", "App")

    def test_get_project(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App")
        p = mgr.get_project("p1")
        assert p.name == "App"

    def test_get_project_not_found(self):
        mgr = TenantManager()
        with pytest.raises(KeyError):
            mgr.get_project("nonexistent")

    def test_list_projects(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App1")
        mgr.create_project("p2", "t1", "App2")
        projects = mgr.list_projects("t1")
        assert len(projects) == 2

    def test_list_projects_empty(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        assert mgr.list_projects("t1") == []

    def test_delete_project(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App")
        mgr.delete_project("p1")
        with pytest.raises(KeyError):
            mgr.get_project("p1")

    def test_delete_project_updates_count(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App")
        mgr.delete_project("p1")
        usage = mgr.get_usage("t1")
        assert usage.project_count == 0

    def test_get_project_tenant(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_project("p1", "t1", "App")
        assert mgr.get_project_tenant("p1") == "t1"

    def test_project_isolation(self):
        """Projects from different tenants are isolated."""
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.create_tenant("t2", "Globex", "globex")
        mgr.create_project("p1", "t1", "Acme App")
        mgr.create_project("p2", "t2", "Globex App")

        t1_projects = mgr.list_projects("t1")
        t2_projects = mgr.list_projects("t2")
        assert len(t1_projects) == 1
        assert len(t2_projects) == 1
        assert t1_projects[0].name == "Acme App"
        assert t2_projects[0].name == "Globex App"


# --- Quota enforcement tests ---

class TestQuotaEnforcement:
    def test_project_quota_exceeded(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_projects=2))
        mgr.create_project("p1", "t1", "App1")
        mgr.create_project("p2", "t1", "App2")
        with pytest.raises(QuotaExceededError, match="projects"):
            mgr.create_project("p3", "t1", "App3")

    def test_run_quota_exceeded(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_runs_per_day=2))
        mgr.check_run_allowed("t1")
        mgr.record_run_start("t1")
        mgr.check_run_allowed("t1")
        mgr.record_run_start("t1")
        with pytest.raises(QuotaExceededError, match="runs_per_day"):
            mgr.check_run_allowed("t1")

    def test_concurrent_run_quota(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_concurrent_runs=1))
        mgr.record_run_start("t1")
        with pytest.raises(QuotaExceededError, match="concurrent_runs"):
            mgr.check_run_allowed("t1")

    def test_concurrent_run_freed_after_end(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_concurrent_runs=1))
        mgr.record_run_start("t1")
        mgr.record_run_end("t1")
        mgr.check_run_allowed("t1")  # Should not raise

    def test_unlimited_quota(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota.unlimited())
        for i in range(100):
            mgr.create_project(f"p{i}", "t1", f"App{i}")
        assert len(mgr.list_projects("t1")) == 100

    def test_suspended_tenant_cannot_run(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.suspend_tenant("t1")
        with pytest.raises(ValueError, match="not active"):
            mgr.check_run_allowed("t1")

    def test_storage_quota(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_storage_mb=100))
        mgr.record_storage("t1", 80)
        mgr.check_storage_allowed("t1", 10)  # 80 + 10 = 90 < 100, OK
        with pytest.raises(QuotaExceededError, match="storage"):
            mgr.check_storage_allowed("t1", 30)  # 80 + 30 = 110 > 100

    def test_api_key_quota(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_api_keys=2))
        mgr.record_api_key_created("t1")
        mgr.record_api_key_created("t1")
        with pytest.raises(QuotaExceededError, match="api_keys"):
            mgr.check_api_key_allowed("t1")

    def test_api_key_revoked_frees_slot(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_api_keys=1))
        mgr.record_api_key_created("t1")
        mgr.record_api_key_revoked("t1")
        mgr.check_api_key_allowed("t1")  # Should not raise


# --- Usage tracking tests ---

class TestUsageTracking:
    def test_get_usage(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        usage = mgr.get_usage("t1")
        assert usage.runs_today == 0
        assert usage.concurrent_runs == 0

    def test_record_run_start(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.record_run_start("t1")
        usage = mgr.get_usage("t1")
        assert usage.runs_today == 1
        assert usage.concurrent_runs == 1

    def test_record_run_end(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.record_run_start("t1")
        mgr.record_run_end("t1")
        usage = mgr.get_usage("t1")
        assert usage.runs_today == 1  # Still counts for the day
        assert usage.concurrent_runs == 0

    def test_record_storage(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme")
        mgr.record_storage("t1", 256.5)
        usage = mgr.get_usage("t1")
        assert usage.storage_used_mb == 256.5

    def test_usage_summary(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota(max_projects=5, max_runs_per_day=50))
        mgr.create_project("p1", "t1", "App")
        mgr.record_run_start("t1")
        summary = mgr.get_usage_summary("t1")
        assert summary["tenant_id"] == "t1"
        assert summary["tenant_name"] == "Acme"
        assert summary["usage"]["project_count"] == 1
        assert summary["usage"]["runs_today"] == 1
        assert summary["limits"]["projects"]["used"] == 1
        assert summary["limits"]["projects"]["limit"] == 5
        assert summary["limits"]["projects"]["remaining"] == 4
        assert summary["limits"]["runs_today"]["remaining"] == 49

    def test_usage_summary_unlimited(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "Acme", "acme", quota=ResourceQuota.unlimited())
        summary = mgr.get_usage_summary("t1")
        assert summary["limits"]["projects"]["remaining"] == -1
        assert summary["limits"]["runs_today"]["remaining"] == -1


# --- Module structure tests ---

class TestModuleStructure:
    def test_imports_from_enterprise(self):
        from vsrs.enterprise import (
            Tenant,
            TenantManager,
            ResourceQuota,
            Project,
            TenantStatus,
            QuotaExceededError,
            TenantNotFoundError,
            UsageRecord,
        )
        assert Tenant is not None
        assert TenantManager is not None

    def test_tenant_status_values(self):
        assert TenantStatus.active == "active"
        assert TenantStatus.suspended == "suspended"
        assert TenantStatus.deleted == "deleted"

    def test_quota_exceeded_error_attrs(self):
        err = QuotaExceededError("t1", "projects", 5, 5)
        assert err.tenant_id == "t1"
        assert err.resource == "projects"
        assert err.limit == 5
        assert err.current == 5

    def test_tenant_not_found_error_attrs(self):
        err = TenantNotFoundError("t1")
        assert err.tenant_id == "t1"
