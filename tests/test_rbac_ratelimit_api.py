"""Tests for Phase 34: Rate limiting & RBAC API endpoints."""

import pytest
from fastapi.testclient import TestClient

from vsrs.api.app import create_app
from vsrs.api.auth import reset_managers, get_key_manager


@pytest.fixture
def admin_client():
    """Client with admin API key."""
    import vsrs.api.enterprise_routes as er
    er._tenant_mgr = None
    er._sso_mgr = None
    reset_managers()
    app = create_app()
    client = TestClient(app)
    key_mgr = get_key_manager()
    raw_key, _ = key_mgr.create_key(user_id="admin", name="admin", scopes=["admin:all"])
    client.headers["X-API-Key"] = raw_key
    return client


@pytest.fixture
def readonly_client():
    """Client with read-only API key."""
    import vsrs.api.enterprise_routes as er
    er._tenant_mgr = None
    er._sso_mgr = None
    reset_managers()
    app = create_app()
    client = TestClient(app)
    key_mgr = get_key_manager()
    raw_key, _ = key_mgr.create_key(user_id="reader", name="reader", scopes=["read"])
    client.headers["X-API-Key"] = raw_key
    return client


@pytest.fixture
def no_key_client():
    """Client without any API key."""
    import vsrs.api.enterprise_routes as er
    er._tenant_mgr = None
    er._sso_mgr = None
    reset_managers()
    app = create_app()
    return TestClient(app)


class TestRateLimitEndpoints:
    def test_get_usage(self, admin_client):
        resp = admin_client.get("/api/v1/rate-limit/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert "minute_used" in data
        assert "minute_limit" in data
        assert "hour_used" in data
        assert "burst_remaining" in data

    def test_get_usage_with_identifier(self, admin_client):
        resp = admin_client.get("/api/v1/rate-limit/usage?identifier=test-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["minute_used"] == 0

    def test_get_config(self, admin_client):
        resp = admin_client.get("/api/v1/rate-limit/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["requests_per_minute"] > 0
        assert data["requests_per_hour"] > 0
        assert data["burst_size"] > 0

    def test_reset_all(self, admin_client):
        resp = admin_client.post("/api/v1/rate-limit/reset")
        assert resp.status_code == 200
        assert resp.json()["reset"] is True
        assert resp.json()["identifier"] is None

    def test_reset_with_identifier(self, admin_client):
        resp = admin_client.post("/api/v1/rate-limit/reset?identifier=test-id")
        assert resp.status_code == 200
        assert resp.json()["identifier"] == "test-id"

    def test_reset_readonly_forbidden(self, readonly_client):
        resp = readonly_client.post("/api/v1/rate-limit/reset")
        assert resp.status_code == 403

    def test_usage_no_auth(self, no_key_client):
        resp = no_key_client.get("/api/v1/rate-limit/usage")
        assert resp.status_code == 401


class TestRBACEndpoints:
    def test_list_roles(self, admin_client):
        resp = admin_client.get("/api/v1/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 3  # viewer, developer, admin
        role_names = [r["name"] for r in data["roles"]]
        assert "viewer" in role_names
        assert "developer" in role_names
        assert "admin" in role_names

    def test_get_role(self, admin_client):
        resp = admin_client.get("/api/v1/roles/admin")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "admin"
        assert len(data["permissions"]) > 0

    def test_get_role_not_found(self, admin_client):
        resp = admin_client.get("/api/v1/roles/nonexistent")
        assert resp.status_code == 404
        assert "Role not found" in resp.json()["detail"]

    def test_check_permission_allowed(self, admin_client):
        resp = admin_client.post("/api/v1/roles/check-permission", json={
            "role_name": "admin",
            "permission": "task:create",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True
        assert "task:create" in data["resolved_permissions"]

    def test_check_permission_denied(self, admin_client):
        resp = admin_client.post("/api/v1/roles/check-permission", json={
            "role_name": "viewer",
            "permission": "task:create",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False

    def test_check_permission_role_not_found(self, admin_client):
        resp = admin_client.post("/api/v1/roles/check-permission", json={
            "role_name": "nonexistent",
            "permission": "task:read",
        })
        assert resp.status_code == 404

    def test_list_roles_no_auth(self, no_key_client):
        resp = no_key_client.get("/api/v1/roles")
        assert resp.status_code == 401

    def test_get_role_readonly_allowed(self, readonly_client):
        resp = readonly_client.get("/api/v1/roles/developer")
        assert resp.status_code == 200
        assert resp.json()["name"] == "developer"
