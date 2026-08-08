"""Tests for Phase 35: Role & Rate Limit CLI + API pagination."""

import pytest
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from vsrs.cli import app
from vsrs.api.app import create_app
from vsrs.api.auth import reset_managers, get_key_manager

runner = CliRunner()


class TestRoleCLI:
    def test_role_list(self):
        result = runner.invoke(app, ["role", "list"])
        assert result.exit_code == 0
        assert "viewer" in result.stdout
        assert "developer" in result.stdout
        assert "admin" in result.stdout

    def test_role_show(self):
        result = runner.invoke(app, ["role", "show", "admin"])
        assert result.exit_code == 0
        assert "admin" in result.stdout
        assert "task:create" in result.stdout

    def test_role_show_not_found(self):
        result = runner.invoke(app, ["role", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_role_check_allowed(self):
        result = runner.invoke(app, [
            "role", "check",
            "--role", "admin",
            "--permission", "task:create",
        ])
        assert result.exit_code == 0
        assert "ALLOWED" in result.stdout

    def test_role_check_denied(self):
        result = runner.invoke(app, [
            "role", "check",
            "--role", "viewer",
            "--permission", "task:create",
        ])
        assert result.exit_code == 1
        assert "DENIED" in result.stdout

    def test_role_check_not_found(self):
        result = runner.invoke(app, [
            "role", "check",
            "--role", "nonexistent",
            "--permission", "task:read",
        ])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_role_help(self):
        result = runner.invoke(app, ["role", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "show" in result.stdout
        assert "check" in result.stdout


class TestRateLimitCLI:
    def test_ratelimit_usage(self):
        result = runner.invoke(app, ["ratelimit", "usage"])
        assert result.exit_code == 0
        assert "Minute" in result.stdout
        assert "Hour" in result.stdout
        assert "Burst" in result.stdout

    def test_ratelimit_usage_with_id(self):
        result = runner.invoke(app, ["ratelimit", "usage", "--id", "test-user"])
        assert result.exit_code == 0
        assert "test-user" in result.stdout

    def test_ratelimit_config(self):
        result = runner.invoke(app, ["ratelimit", "config"])
        assert result.exit_code == 0
        assert "Requests per minute" in result.stdout
        assert "Requests per hour" in result.stdout
        assert "Burst size" in result.stdout

    def test_ratelimit_reset_all(self):
        result = runner.invoke(app, ["ratelimit", "reset"])
        assert result.exit_code == 0
        assert "All rate limits reset" in result.stdout

    def test_ratelimit_reset_id(self):
        result = runner.invoke(app, ["ratelimit", "reset", "--id", "test-id"])
        assert result.exit_code == 0
        assert "test-id" in result.stdout

    def test_ratelimit_help(self):
        result = runner.invoke(app, ["ratelimit", "--help"])
        assert result.exit_code == 0
        assert "usage" in result.stdout
        assert "config" in result.stdout
        assert "reset" in result.stdout


class TestMainHelpShowsNewCommands:
    def test_main_help_has_role(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "role" in result.stdout

    def test_main_help_has_ratelimit(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "ratelimit" in result.stdout


class TestAPIPagination:
    @pytest.fixture
    def admin_client(self):
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

    def test_tenant_pagination_fields(self, admin_client):
        resp = admin_client.get("/api/v1/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert data["offset"] == 0

    def test_tenant_pagination_offset(self, admin_client):
        resp = admin_client.get("/api/v1/tenants?offset=0&limit=1")
        assert resp.status_code == 0 or resp.status_code == 200
        if resp.status_code == 200:
            data = resp.json()
            assert data["offset"] == 0
            assert data["limit"] == 1

    def test_keys_pagination_fields(self, admin_client):
        resp = admin_client.get("/api/v1/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "offset" in data
        assert data["total"] >= 1

    def test_audit_pagination_fields(self, admin_client):
        resp = admin_client.get("/api/v1/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "offset" in data
        assert "limit" in data

    def test_roles_pagination_fields(self, admin_client):
        resp = admin_client.get("/api/v1/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert data["total"] >= 3
        assert "offset" in data

    def test_roles_pagination_limit(self, admin_client):
        resp = admin_client.get("/api/v1/roles?offset=0&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] <= 2
        assert data["total"] >= 3
        assert data["limit"] == 2
