"""Tests for Phase 30: Enterprise API endpoints.

Tests tenant, SSO, and pool REST API endpoints using FastAPI's TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from vsrs.api.app import create_app
from vsrs.api.enterprise_routes import _tenant_mgr, _sso_mgr
from vsrs.api.auth import reset_managers, get_key_manager


@pytest.fixture
def client():
    """Create a test client with fresh managers and admin API key."""
    import vsrs.api.enterprise_routes as er
    er._tenant_mgr = None
    er._sso_mgr = None
    reset_managers()
    app = create_app()
    c = TestClient(app)

    # Create admin API key for all requests
    key_mgr = get_key_manager()
    raw_key, _ = key_mgr.create_key(user_id="admin", name="admin", scopes=["admin:all"])
    c.headers["X-API-Key"] = raw_key
    return c


# --- Tenant endpoints ---


class TestTenantAPI:
    def test_create_tenant(self, client):
        resp = client.post("/api/v1/tenants", json={
            "tenant_id": "acme",
            "name": "Acme Corp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "acme"
        assert data["name"] == "Acme Corp"
        assert data["status"] == "active"

    def test_create_tenant_with_quota(self, client):
        resp = client.post("/api/v1/tenants", json={
            "tenant_id": "quota-test",
            "name": "Quota Test",
            "max_projects": 50,
            "max_runs_per_day": 1000,
        })
        assert resp.status_code == 200
        assert resp.json()["quota"]["max_projects"] == 50

    def test_list_tenants(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "t1", "name": "T1"})
        client.post("/api/v1/tenants", json={"tenant_id": "t2", "name": "T2"})
        resp = client.get("/api/v1/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2
        ids = [t["id"] for t in data["tenants"]]
        assert "t1" in ids
        assert "t2" in ids

    def test_get_tenant(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "get-test", "name": "Get Test"})
        resp = client.get("/api/v1/tenants/get-test")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Test"

    def test_get_tenant_not_found(self, client):
        resp = client.get("/api/v1/tenants/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_get_tenant_usage(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "usage-test", "name": "Usage Test"})
        resp = client.get("/api/v1/tenants/usage-test/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "usage-test"
        assert data["project_count"] == 0

    def test_get_tenant_usage_not_found(self, client):
        resp = client.get("/api/v1/tenants/nonexistent/usage")
        assert resp.status_code == 404

    def test_suspend_tenant(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "suspend-test", "name": "Suspend"})
        resp = client.post("/api/v1/tenants/suspend-test/suspend")
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

    def test_reactivate_tenant(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "react-test", "name": "React"})
        client.post("/api/v1/tenants/react-test/suspend")
        resp = client.post("/api/v1/tenants/react-test/reactivate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_delete_tenant(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "del-test", "name": "Del"})
        resp = client.delete("/api/v1/tenants/del-test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_tenant_not_found(self, client):
        resp = client.delete("/api/v1/tenants/nonexistent")
        assert resp.status_code == 404


# --- Project endpoints ---


class TestProjectAPI:
    def test_create_project(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "p-test", "name": "P Test"})
        resp = client.post("/api/v1/tenants/p-test/projects", json={
            "project_id": "web-app",
            "name": "Web App",
            "repo_root": "/repo",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "web-app"
        assert data["tenant_id"] == "p-test"

    def test_create_project_tenant_not_found(self, client):
        resp = client.post("/api/v1/tenants/nonexistent/projects", json={
            "project_id": "p1",
            "name": "P1",
        })
        assert resp.status_code == 404

    def test_list_projects(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "lp-test", "name": "LP"})
        client.post("/api/v1/tenants/lp-test/projects", json={
            "project_id": "p1", "name": "P1",
        })
        client.post("/api/v1/tenants/lp-test/projects", json={
            "project_id": "p2", "name": "P2",
        })
        resp = client.get("/api/v1/tenants/lp-test/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_list_projects_tenant_not_found(self, client):
        resp = client.get("/api/v1/tenants/nonexistent/projects")
        assert resp.status_code == 404

    def test_delete_project(self, client):
        client.post("/api/v1/tenants", json={"tenant_id": "dp-test", "name": "DP"})
        client.post("/api/v1/tenants/dp-test/projects", json={
            "project_id": "del-p", "name": "Del P",
        })
        resp = client.delete("/api/v1/tenants/dp-test/projects/del-p")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


# --- SSO endpoints ---


class TestSSOAPI:
    def test_list_providers_empty(self, client):
        resp = client.get("/api/v1/sso/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["providers"] == []

    def test_list_sessions_empty(self, client):
        resp = client.get("/api/v1/sso/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_list_users_empty(self, client):
        resp = client.get("/api/v1/sso/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_cleanup_sessions(self, client):
        resp = client.post("/api/v1/sso/cleanup")
        assert resp.status_code == 200
        assert resp.json()["removed"] == 0


# --- Pool endpoints ---


class TestPoolAPI:
    def test_pool_stats(self, client):
        resp = client.get("/api/v1/pool/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["worker_count"] == 0
        assert data["idle_count"] == 0
        assert "total_capacity" in data
        assert "total_available" in data


# --- Health and existing endpoints still work ---


class TestBackwardCompat:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_existing_runs_endpoint(self, client):
        # /runs only has POST, so a GET should return 405 (method exists)
        resp = client.get("/api/v1/runs")
        assert resp.status_code == 405

    def test_existing_benchmarks_endpoint(self, client):
        resp = client.get("/api/v1/benchmarks")
        assert resp.status_code == 200
