"""Tests for Phase 29: Enterprise CLI commands.

Tests tenant, SSO, and pool CLI subcommands using Typer's CliRunner.
"""

import pytest
from typer.testing import CliRunner

from vsrs.cli import app

runner = CliRunner()


class TestTenantCLI:
    def test_tenant_create(self):
        result = runner.invoke(app, [
            "tenant", "create",
            "--id", "test-acme",
            "--name", "Test Acme",
        ])
        assert result.exit_code == 0
        assert "Tenant created" in result.stdout
        assert "test-acme" in result.stdout

    def test_tenant_create_with_quota(self):
        result = runner.invoke(app, [
            "tenant", "create",
            "--id", "test-quota",
            "--name", "Quota Test",
            "--max-projects", "50",
            "--max-runs-day", "1000",
            "--max-storage-mb", "10240",
        ])
        assert result.exit_code == 0
        assert "Tenant created" in result.stdout

    def test_tenant_list_empty(self):
        result = runner.invoke(app, ["tenant", "list"])
        assert result.exit_code == 0
        # Fresh in-memory manager, so no tenants
        assert "No tenants" in result.stdout or "Tenants" in result.stdout

    def test_tenant_show_not_found(self):
        result = runner.invoke(app, ["tenant", "show", "nonexistent-tenant"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_tenant_suspend_not_found(self):
        result = runner.invoke(app, ["tenant", "suspend", "nonexistent-tenant"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_tenant_reactivate_not_found(self):
        result = runner.invoke(app, ["tenant", "reactivate", "nonexistent-tenant"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_tenant_delete_not_found(self):
        result = runner.invoke(app, ["tenant", "delete", "nonexistent-tenant", "--force"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_tenant_delete_cancelled(self):
        result = runner.invoke(app, ["tenant", "delete", "some-tenant"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.stdout


class TestSSOCLI:
    def test_sso_list_providers_empty(self):
        result = runner.invoke(app, ["sso", "list-providers"])
        assert result.exit_code == 0
        assert "No SSO providers" in result.stdout

    def test_sso_list_sessions_empty(self):
        result = runner.invoke(app, ["sso", "list-sessions"])
        assert result.exit_code == 0
        assert "No active SSO sessions" in result.stdout

    def test_sso_cleanup(self):
        result = runner.invoke(app, ["sso", "cleanup"])
        assert result.exit_code == 0
        assert "expired" in result.stdout

    def test_sso_list_users_empty(self):
        result = runner.invoke(app, ["sso", "list-users"])
        assert result.exit_code == 0
        assert "No SSO users" in result.stdout


class TestPoolCLI:
    def test_pool_stats(self):
        result = runner.invoke(app, ["pool", "stats"])
        assert result.exit_code == 0
        assert "WorkerPool" in result.stdout or "worker pool" in result.stdout.lower()


class TestCLIHelp:
    def test_tenant_help(self):
        result = runner.invoke(app, ["tenant", "--help"])
        assert result.exit_code == 0
        assert "create" in result.stdout
        assert "list" in result.stdout
        assert "show" in result.stdout
        assert "suspend" in result.stdout
        assert "delete" in result.stdout

    def test_sso_help(self):
        result = runner.invoke(app, ["sso", "--help"])
        assert result.exit_code == 0
        assert "list-providers" in result.stdout
        assert "list-sessions" in result.stdout
        assert "cleanup" in result.stdout
        assert "list-users" in result.stdout

    def test_pool_help(self):
        result = runner.invoke(app, ["pool", "--help"])
        assert result.exit_code == 0
        assert "stats" in result.stdout

    def test_main_help_shows_subcommands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "tenant" in result.stdout
        assert "sso" in result.stdout
        assert "pool" in result.stdout
