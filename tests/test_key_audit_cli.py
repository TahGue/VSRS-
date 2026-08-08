"""Tests for Phase 32: API key & audit CLI commands."""

from typer.testing import CliRunner

from vsrs.cli import app

runner = CliRunner()


class TestKeyCLI:
    def test_key_create(self):
        result = runner.invoke(app, [
            "key", "create",
            "--user", "test-user",
            "--name", "test-key",
            "--scopes", "read,write",
        ])
        assert result.exit_code == 0
        assert "API key created" in result.stdout
        assert "test-user" in result.stdout
        assert "read, write" in result.stdout
        assert "Raw key" in result.stdout

    def test_key_create_no_scopes(self):
        result = runner.invoke(app, [
            "key", "create",
            "--user", "simple-user",
        ])
        assert result.exit_code == 0
        assert "API key created" in result.stdout
        assert "(none)" in result.stdout

    def test_key_list_empty(self):
        result = runner.invoke(app, ["key", "list"])
        assert result.exit_code == 0
        # Fresh in-memory manager, so no keys
        assert "No API keys" in result.stdout

    def test_key_revoke_not_found(self):
        result = runner.invoke(app, ["key", "revoke", "nonexistent-key-id"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_key_validate_invalid(self):
        result = runner.invoke(app, ["key", "validate", "vsrs_invalid_key_12345"])
        assert result.exit_code == 1
        assert "Invalid" in result.stdout

    def test_key_count(self):
        result = runner.invoke(app, ["key", "count"])
        assert result.exit_code == 0
        assert "Total API keys" in result.stdout


class TestAuditCLI:
    def test_audit_list_empty(self):
        result = runner.invoke(app, ["audit", "list"])
        assert result.exit_code == 0
        assert "No audit events" in result.stdout

    def test_audit_count(self):
        result = runner.invoke(app, ["audit", "count"])
        assert result.exit_code == 0
        assert "Total audit events" in result.stdout

    def test_audit_export(self, tmp_path):
        export_path = tmp_path / "audit.jsonl"
        result = runner.invoke(app, [
            "audit", "export",
            "--output", str(export_path),
        ])
        assert result.exit_code == 0
        assert "Exported" in result.stdout


class TestCLIHelp:
    def test_key_help(self):
        result = runner.invoke(app, ["key", "--help"])
        assert result.exit_code == 0
        assert "create" in result.stdout
        assert "list" in result.stdout
        assert "revoke" in result.stdout
        assert "validate" in result.stdout
        assert "count" in result.stdout

    def test_audit_help(self):
        result = runner.invoke(app, ["audit", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "count" in result.stdout
        assert "export" in result.stdout

    def test_main_help_shows_key_and_audit(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "key" in result.stdout
        assert "audit" in result.stdout
