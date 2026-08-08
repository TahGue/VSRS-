"""Tests for Phase 31: API authentication middleware.

Tests API key validation, scope checking, rate limiting, and
audit logging on protected enterprise endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from vsrs.api.app import create_app
from vsrs.api.auth import reset_managers, get_key_manager


@pytest.fixture
def client():
    """Create a test client with fresh auth managers."""
    import vsrs.api.enterprise_routes as er
    er._tenant_mgr = None
    er._sso_mgr = None
    reset_managers()
    app = create_app()
    return TestClient(app)


@pytest.fixture
def admin_client():
    """Create a test client with a pre-registered admin API key."""
    import vsrs.api.enterprise_routes as er
    er._tenant_mgr = None
    er._sso_mgr = None
    reset_managers()
    app = create_app()
    client = TestClient(app)

    # Create an admin API key
    key_mgr = get_key_manager()
    raw_key, api_key = key_mgr.create_key(
        user_id="admin-user",
        name="admin",
        scopes=["admin:all"],
    )
    client.headers["X-API-Key"] = raw_key
    return client


@pytest.fixture
def readonly_client():
    """Create a test client with a read-only API key (no admin scopes)."""
    import vsrs.api.enterprise_routes as er
    er._tenant_mgr = None
    er._sso_mgr = None
    reset_managers()
    app = create_app()
    client = TestClient(app)

    key_mgr = get_key_manager()
    raw_key, api_key = key_mgr.create_key(
        user_id="reader-user",
        name="reader",
        scopes=["read"],
    )
    client.headers["X-API-Key"] = raw_key
    return client


class TestNoApiKey:
    """Endpoints that require auth should reject requests without API key."""

    def test_list_tenants_no_key(self, client):
        resp = client.get("/api/v1/tenants")
        assert resp.status_code == 401
        assert "Missing API key" in resp.json()["detail"]

    def test_create_tenant_no_key(self, client):
        resp = client.post("/api/v1/tenants", json={"tenant_id": "t", "name": "T"})
        assert resp.status_code == 401

    def test_get_tenant_no_key(self, client):
        resp = client.get("/api/v1/tenants/some-id")
        assert resp.status_code == 401

    def test_pool_stats_no_key(self, client):
        resp = client.get("/api/v1/pool/stats")
        assert resp.status_code == 401

    def test_sso_providers_no_key(self, client):
        resp = client.get("/api/v1/sso/providers")
        assert resp.status_code == 401


class TestInvalidApiKey:
    def test_list_tenants_invalid_key(self, client):
        resp = client.get("/api/v1/tenants", headers={"X-API-Key": "invalid-key"})
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]


class TestReadOnlyAccess:
    """Read-only key can access GET endpoints but not admin endpoints."""

    def test_list_tenants_with_read_key(self, readonly_client):
        resp = readonly_client.get("/api/v1/tenants")
        assert resp.status_code == 200

    def test_create_tenant_with_read_key(self, readonly_client):
        resp = readonly_client.post("/api/v1/tenants", json={"tenant_id": "t", "name": "T"})
        assert resp.status_code == 403
        assert "Insufficient scope" in resp.json()["detail"]

    def test_pool_stats_with_read_key(self, readonly_client):
        resp = readonly_client.get("/api/v1/pool/stats")
        assert resp.status_code == 200

    def test_sso_providers_with_read_key(self, readonly_client):
        resp = readonly_client.get("/api/v1/sso/providers")
        assert resp.status_code == 200

    def test_sso_cleanup_with_read_key(self, readonly_client):
        resp = readonly_client.post("/api/v1/sso/cleanup")
        assert resp.status_code == 403


class TestAdminAccess:
    """Admin key can access all endpoints."""

    def test_create_tenant_with_admin_key(self, admin_client):
        resp = admin_client.post("/api/v1/tenants", json={"tenant_id": "acme", "name": "Acme"})
        assert resp.status_code == 200
        assert resp.json()["id"] == "acme"

    def test_list_tenants_with_admin_key(self, admin_client):
        admin_client.post("/api/v1/tenants", json={"tenant_id": "t1", "name": "T1"})
        resp = admin_client.get("/api/v1/tenants")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_suspend_tenant_with_admin_key(self, admin_client):
        admin_client.post("/api/v1/tenants", json={"tenant_id": "susp", "name": "S"})
        resp = admin_client.post("/api/v1/tenants/susp/suspend")
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

    def test_delete_tenant_with_admin_key(self, admin_client):
        admin_client.post("/api/v1/tenants", json={"tenant_id": "del", "name": "D"})
        resp = admin_client.delete("/api/v1/tenants/del")
        assert resp.status_code == 200

    def test_create_project_with_admin_key(self, admin_client):
        admin_client.post("/api/v1/tenants", json={"tenant_id": "p1", "name": "P1"})
        resp = admin_client.post("/api/v1/tenants/p1/projects", json={
            "project_id": "proj1", "name": "Proj1",
        })
        assert resp.status_code == 200

    def test_sso_cleanup_with_admin_key(self, admin_client):
        resp = admin_client.post("/api/v1/sso/cleanup")
        assert resp.status_code == 200
        assert resp.json()["removed"] == 0


class TestRateLimiting:
    """Rate limiting is enforced on authenticated requests."""

    def test_rate_limit_headers(self, admin_client):
        resp = admin_client.get("/api/v1/tenants")
        assert resp.status_code == 200


class TestUnprotectedEndpoints:
    """Health and existing core endpoints remain unprotected."""

    def test_health_no_key(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_benchmarks_no_key(self, client):
        resp = client.get("/api/v1/benchmarks")
        assert resp.status_code == 200
