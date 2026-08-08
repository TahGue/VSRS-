"""Integration tests for cross-module workflows.

Tests that exercise multiple VSRS modules together to verify
end-to-end functionality across enterprise, distributed, and core modules.
"""

import base64
import json
import time
import pytest
from datetime import datetime, timezone

from vsrs.enterprise import (
    APIKeyManager,
    AuditEventType,
    AuditLogger,
    Permission,
    RateLimitConfig,
    RateLimiter,
    ResourceQuota,
    RoleManager,
    SSOManager,
    OIDCProvider,
    SAMLProvider,
    SSOProtocol,
    Tenant,
    TenantManager,
    TenantStatus,
)
from vsrs.distributed import (
    InMemoryQueue,
    JobResult,
    JobStatus,
    PoolConfig,
    ResourceSpec,
    TaskJob,
    Worker,
    WorkerPool,
)


# --- Enterprise + Distributed integration ---

class TestTenantWithWorkerPool:
    """Tenant quota enforcement integrated with worker pool."""

    def test_tenant_run_lifecycle_with_pool(self):
        """A tenant can submit jobs to a worker pool within quota."""
        queue = InMemoryQueue()
        pool = WorkerPool(queue, config=PoolConfig(min_workers=1, max_workers=5))
        pool.add_worker(
            worker_id="w1",
            capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
            handlers={"verify": lambda job: {"status": "verified"}},
        )

        mgr = TenantManager()
        mgr.create_tenant("acme", "Acme", "acme", quota=ResourceQuota(max_runs_per_day=5))
        mgr.create_project("p1", "acme", "Web App")

        # Submit 3 runs within quota
        for i in range(3):
            mgr.check_run_allowed("acme")
            mgr.record_run_start("acme")

            job = TaskJob(id=f"job-{i}", task_type="verify", payload={"task": f"task-{i}"})
            result = pool.process_job_on_worker(job, ResourceSpec(cpu=1.0, memory_mb=512))
            assert result.success

            mgr.record_run_end("acme")

        usage = mgr.get_usage("acme")
        assert usage.runs_today == 3
        assert usage.concurrent_runs == 0

    def test_tenant_quota_blocks_excess_runs(self):
        """Tenant quota blocks job submission when exceeded."""
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(
            worker_id="w1",
            capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
            handlers={"verify": lambda job: {"ok": True}},
        )

        mgr = TenantManager()
        mgr.create_tenant("acme", "Acme", "acme", quota=ResourceQuota(max_runs_per_day=2))

        # First two runs are fine
        for i in range(2):
            mgr.check_run_allowed("acme")
            mgr.record_run_start("acme")
            mgr.record_run_end("acme")

        # Third run should be blocked
        from vsrs.enterprise import QuotaExceededError
        with pytest.raises(QuotaExceededError, match="runs_per_day"):
            mgr.check_run_allowed("acme")

    def test_suspended_tenant_cannot_use_pool(self):
        """A suspended tenant cannot submit jobs."""
        mgr = TenantManager()
        mgr.create_tenant("acme", "Acme", "acme")
        mgr.suspend_tenant("acme")

        with pytest.raises(ValueError, match="not active"):
            mgr.check_run_allowed("acme")


# --- SSO + Enterprise integration ---

class TestSSOWithEnterprise:
    """SSO authentication integrated with enterprise features."""

    def _make_jwt(self, payload: dict) -> str:
        h = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        return f"{h}.{p}.sig"

    def test_sso_user_gets_api_key(self):
        """An SSO-provisioned user can get an API key."""
        sso = SSOManager()
        sso.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="https://accounts.google.com",
            client_id="cid",
        ))

        jwt = self._make_jwt({
            "sub": "ext123", "email": "user@acme.com", "name": "Test User",
            "exp": int(time.time()) + 3600,
        })
        session = sso.authenticate_oidc("google", jwt)
        user = sso.get_user(session.user_id)
        assert user is not None

        # Create an API key for the SSO user
        key_mgr = APIKeyManager()
        raw_key, api_key = key_mgr.create_key(user_id=user.id, scopes=["read", "write"])
        assert api_key.user_id == user.id
        assert api_key.is_valid

    def test_sso_login_audited(self):
        """SSO login events are recorded in the audit log."""
        sso = SSOManager()
        sso.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="url", client_id="cid",
        ))
        auditor = AuditLogger()

        jwt = self._make_jwt({"sub": "ext1", "email": "u@e.com", "exp": int(time.time()) + 3600})
        session = sso.authenticate_oidc("google", jwt)

        auditor.log_event(
            event_type=AuditEventType.auth_login,
            user_id=session.user_id,
            resource=f"session/{session.id}",
            details={"provider": "google", "protocol": "oidc"},
        )

        events = auditor.query(user_id=session.user_id)
        assert len(events) >= 1
        assert events[0].user_id == session.user_id

    def test_sso_user_assigned_role(self):
        """SSO users can be assigned roles via RBAC."""
        sso = SSOManager()
        sso.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="url", client_id="cid",
        ))
        role_mgr = RoleManager()
        # "developer" is a built-in role
        dev_role = role_mgr.get("developer")
        assert dev_role is not None
        assert role_mgr.check("developer", Permission.task_create.value)

        jwt = self._make_jwt({"sub": "ext1", "email": "dev@acme.com", "exp": int(time.time()) + 3600})
        session = sso.authenticate_oidc("google", jwt)
        user = sso.get_user(session.user_id)

        # Assign role
        user.role = "developer"
        assert user.role == "developer"

    def test_sso_session_rate_limited(self):
        """SSO session creation respects rate limits."""
        sso = SSOManager()
        sso.register_oidc_provider(OIDCProvider(
            id="g", name="G", issuer_url="url", client_id="cid",
        ))
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=2))

        jwt = self._make_jwt({"sub": "ext1", "email": "u@e.com", "exp": int(time.time()) + 3600})

        # First two auth attempts allowed
        r1 = limiter.check("sso-client")
        assert r1.allowed
        sso.authenticate_oidc("g", jwt)

        r2 = limiter.check("sso-client")
        assert r2.allowed
        sso.authenticate_oidc("g", jwt)

        # Third should be rate limited
        r3 = limiter.check("sso-client")
        assert not r3.allowed


# --- Tenant + SSO integration ---

class TestTenantWithSSO:
    """Multi-tenant with SSO authentication."""

    def _make_jwt(self, payload: dict) -> str:
        h = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        return f"{h}.{p}.sig"

    def test_sso_user_in_tenant_context(self):
        """An SSO user operates within a tenant's project."""
        tenant_mgr = TenantManager()
        sso = SSOManager()

        # Set up tenant
        tenant_mgr.create_tenant("acme", "Acme", "acme")
        tenant_mgr.create_project("web-app", "acme", "Web App", "/repos/acme/web")

        # Set up SSO
        sso.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="url", client_id="cid",
        ))

        # User authenticates via SSO
        jwt = self._make_jwt({"sub": "ext1", "email": "dev@acme.com", "exp": int(time.time()) + 3600})
        session = sso.authenticate_oidc("google", jwt)
        user = sso.get_user(session.user_id)

        # User operates within tenant context
        assert user is not None
        assert user.email == "dev@acme.com"
        projects = tenant_mgr.list_projects("acme")
        assert len(projects) == 1
        assert projects[0].name == "Web App"

    def test_different_tenants_different_sso_providers(self):
        """Different tenants can use different SSO providers."""
        tenant_mgr = TenantManager()
        sso = SSOManager()

        tenant_mgr.create_tenant("acme", "Acme", "acme")
        tenant_mgr.create_tenant("globex", "Globex", "globex")

        sso.register_oidc_provider(OIDCProvider(id="google", name="Google", issuer_url="url", client_id="cid1"))
        sso.register_oidc_provider(OIDCProvider(id="okta", name="Okta", issuer_url="url", client_id="cid2"))

        jwt1 = self._make_jwt({"sub": "ext1", "email": "user@acme.com", "exp": int(time.time()) + 3600})
        jwt2 = self._make_jwt({"sub": "ext2", "email": "user@globex.com", "exp": int(time.time()) + 3600})

        s1 = sso.authenticate_oidc("google", jwt1)
        s2 = sso.authenticate_oidc("okta", jwt2)

        assert s1.user_id != s2.user_id
        u1 = sso.get_user(s1.user_id)
        u2 = sso.get_user(s2.user_id)
        assert u1.email == "user@acme.com"
        assert u2.email == "user@globex.com"


# --- Worker pool + distributed integration ---

class TestWorkerPoolWithQueue:
    """Worker pool integration with task queue."""

    def test_pool_processes_jobs_from_queue(self):
        """Jobs submitted to the queue are processed by pool workers."""
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(
            worker_id="w1",
            capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
            handlers={"test": lambda job: {"result": job.payload.get("value", 0) * 2}},
        )

        # Submit jobs to queue via pool
        job1 = TaskJob(id="j1", task_type="test", payload={"value": 5})
        job2 = TaskJob(id="j2", task_type="test", payload={"value": 10})

        pool.submit_job(job1, ResourceSpec(cpu=1.0, memory_mb=512))
        pool.submit_job(job2, ResourceSpec(cpu=1.0, memory_mb=512))

        # Process synchronously
        r1 = pool.process_job_on_worker(job1, ResourceSpec(cpu=1.0, memory_mb=512))
        r2 = pool.process_job_on_worker(job2, ResourceSpec(cpu=1.0, memory_mb=512))

        assert r1.success
        assert r1.output["result"] == 10
        assert r2.success
        assert r2.output["result"] == 20

    def test_pool_worker_stats_after_processing(self):
        """Worker stats are updated after job processing."""
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(
            worker_id="w1",
            capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
            handlers={"test": lambda job: {"ok": True}},
        )

        for i in range(5):
            job = TaskJob(id=f"j{i}", task_type="test")
            pool.process_job_on_worker(job, ResourceSpec(cpu=1.0, memory_mb=512))

        info = pool.get_worker("w1")
        assert info.jobs_processed == 5
        assert info.jobs_succeeded == 5
        assert info.state.value == "idle"  # Back to idle after processing

    def test_pool_with_mixed_capacity_workers(self):
        """Pool routes jobs to workers based on resource requirements."""
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(
            worker_id="small",
            capacity=ResourceSpec(cpu=1.0, memory_mb=512),
            handlers={"test": lambda job: {"worker": "small"}},
        )
        pool.add_worker(
            worker_id="large",
            capacity=ResourceSpec(cpu=8.0, memory_mb=16384),
            handlers={"test": lambda job: {"worker": "large"}},
        )

        # Small job can go to either worker
        small_job = TaskJob(id="small-job", task_type="test")
        result = pool.process_job_on_worker(small_job, ResourceSpec(cpu=0.5, memory_mb=256))

        # Large job must go to large worker
        large_job = TaskJob(id="large-job", task_type="test")
        result = pool.process_job_on_worker(large_job, ResourceSpec(cpu=4.0, memory_mb=8192))
        assert result.success

    def test_pool_stats_reflect_state(self):
        """Pool stats accurately reflect worker states."""
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=4.0, memory_mb=4096))
        pool.add_worker(worker_id="w2", capacity=ResourceSpec(cpu=2.0, memory_mb=2048))

        stats = pool.pool_stats()
        assert stats["worker_count"] == 2
        assert stats["idle_count"] == 2
        assert stats["busy_count"] == 0
        assert stats["total_capacity"]["cpu"] == 6.0
        assert stats["total_available"]["cpu"] == 6.0


# --- Full end-to-end integration ---

class TestEndToEnd:
    """Full end-to-end workflow across all enterprise modules."""

    def _make_jwt(self, payload: dict) -> str:
        h = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        return f"{h}.{p}.sig"

    def test_full_enterprise_workflow(self):
        """Complete enterprise workflow: tenant → SSO → API key → audit → pool."""
        # 1. Create tenant
        tenant_mgr = TenantManager()
        tenant_mgr.create_tenant("acme", "Acme", "acme", quota=ResourceQuota(
            max_projects=5, max_runs_per_day=10, max_api_keys=5,
        ))
        tenant_mgr.create_project("web", "acme", "Web App", "/repo")

        # 2. Set up SSO
        sso = SSOManager()
        sso.register_oidc_provider(OIDCProvider(
            id="google", name="Google", issuer_url="url", client_id="cid",
        ))

        # 3. User authenticates via SSO
        jwt = self._make_jwt({
            "sub": "ext1", "email": "dev@acme.com", "name": "Dev",
            "exp": int(time.time()) + 3600,
        })
        session = sso.authenticate_oidc("google", jwt)
        user = sso.get_user(session.user_id)
        assert user is not None

        # 4. Create API key for the user
        key_mgr = APIKeyManager()
        tenant_mgr.check_api_key_allowed("acme")
        raw_key, api_key = key_mgr.create_key(user_id=user.id, scopes=["read", "write"])
        tenant_mgr.record_api_key_created("acme")

        # 5. Audit the key creation
        auditor = AuditLogger()
        auditor.log_event(
            event_type=AuditEventType.auth_key_create,
            user_id=user.id,
            resource=f"api-key/{api_key.id}",
            details={"tenant": "acme", "scopes": ["read", "write"]},
        )

        # 6. Set up worker pool
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(
            worker_id="w1",
            capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
            handlers={"verify": lambda job: {"status": "verified", "checks_passed": 5}},
        )

        # 7. Submit a verification job within tenant quota
        tenant_mgr.check_run_allowed("acme")
        tenant_mgr.record_run_start("acme")

        job = TaskJob(id="job-1", task_type="verify", payload={"project": "web"})
        result = pool.process_job_on_worker(job, ResourceSpec(cpu=2.0, memory_mb=1024))

        assert result.success
        assert result.output["status"] == "verified"

        tenant_mgr.record_run_end("acme")

        # 8. Verify everything is consistent
        usage = tenant_mgr.get_usage("acme")
        assert usage.runs_today == 1
        assert usage.concurrent_runs == 0
        assert usage.project_count == 1
        assert usage.api_key_count == 1

        assert sso.user_count == 1
        assert sso.session_count == 1
        assert pool.worker_count == 1

        # 9. SSO session still valid
        assert session.is_valid

        # 10. Audit trail has events
        events = auditor.query(user_id=user.id)
        assert len(events) >= 1
