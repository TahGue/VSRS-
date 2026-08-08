"""Tests for Phase 33: API key & audit management API endpoints."""

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


class TestAPIKeyEndpoints:
    def test_create_key_admin(self, admin_client):
        resp = admin_client.post("/api/v1/keys", json={
            "user_id": "new-user",
            "name": "test-key",
            "scopes": ["read", "write"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"]["user_id"] == "new-user"
        assert data["key"]["name"] == "test-key"
        assert "read" in data["key"]["scopes"]
        assert data["raw_key"]  # Raw key returned

    def test_create_key_readonly_forbidden(self, readonly_client):
        resp = readonly_client.post("/api/v1/keys", json={
            "user_id": "u",
            "name": "k",
        })
        assert resp.status_code == 403

    def test_create_key_no_auth(self, no_key_client):
        resp = no_key_client.post("/api/v1/keys", json={"user_id": "u"})
        assert resp.status_code == 401

    def test_list_keys(self, admin_client):
        admin_client.post("/api/v1/keys", json={"user_id": "u1", "name": "k1"})
        admin_client.post("/api/v1/keys", json={"user_id": "u2", "name": "k2"})
        resp = admin_client.get("/api/v1/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2

    def test_list_keys_filter_user(self, admin_client):
        admin_client.post("/api/v1/keys", json={"user_id": "filter-user", "name": "fk"})
        resp = admin_client.get("/api/v1/keys?user_id=filter-user")
        assert resp.status_code == 200
        data = resp.json()
        assert all(k["user_id"] == "filter-user" for k in data["keys"])

    def test_count_keys(self, admin_client):
        resp = admin_client.get("/api/v1/keys/count")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1  # At least the admin key

    def test_revoke_key(self, admin_client):
        create_resp = admin_client.post("/api/v1/keys", json={"user_id": "rev", "name": "rev-me"})
        key_id = create_resp.json()["key"]["id"]
        resp = admin_client.delete(f"/api/v1/keys/{key_id}")
        assert resp.status_code == 200
        assert resp.json()["revoked"] is True

    def test_revoke_key_not_found(self, admin_client):
        resp = admin_client.delete("/api/v1/keys/nonexistent-key-id")
        assert resp.status_code == 404

    def test_revoke_key_readonly_forbidden(self, readonly_client):
        resp = readonly_client.delete("/api/v1/keys/some-id")
        assert resp.status_code == 403


class TestAuditEndpoints:
    def test_list_audit_empty(self, admin_client):
        resp = admin_client.get("/api/v1/audit")
        assert resp.status_code == 200
        data = resp.json()
        # May have some events from auth validation
        assert "events" in data
        assert "count" in data

    def test_list_audit_with_filter(self, admin_client):
        resp = admin_client.get("/api/v1/audit?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) <= 5

    def test_count_audit(self, admin_client):
        resp = admin_client.get("/api/v1/audit/count")
        assert resp.status_code == 200
        assert "count" in resp.json()

    def test_audit_no_auth(self, no_key_client):
        resp = no_key_client.get("/api/v1/audit")
        assert resp.status_code == 401


class TestKeyAuditIntegration:
    def test_create_key_then_use_it(self, admin_client):
        """Create a new admin key via API, then use it to make a request."""
        create_resp = admin_client.post("/api/v1/keys", json={
            "user_id": "new-admin",
            "name": "new-admin-key",
            "scopes": ["admin:all"],
        })
        assert create_resp.status_code == 200
        raw_key = create_resp.json()["raw_key"]

        # Use the new key to list tenants
        resp = admin_client.get("/api/v1/tenants", headers={"X-API-Key": raw_key})
        assert resp.status_code == 200

    def test_revoke_key_invalidates_it(self, admin_client):
        """Create a key, revoke it, then verify it no longer works."""
        create_resp = admin_client.post("/api/v1/keys", json={
            "user_id": "temp-user",
            "name": "temp-key",
            "scopes": ["admin:all"],
        })
        raw_key = create_resp.json()["raw_key"]
        key_id = create_resp.json()["key"]["id"]

        # Verify it works
        resp = admin_client.get("/api/v1/tenants", headers={"X-API-Key": raw_key})
        assert resp.status_code == 200

        # Revoke it
        del_resp = admin_client.delete(f"/api/v1/keys/{key_id}")
        assert del_resp.status_code == 200

        # Verify it no longer works
        resp = admin_client.get("/api/v1/tenants", headers={"X-API-Key": raw_key})
        assert resp.status_code == 401
