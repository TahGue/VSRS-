"""Tests for configuration management (Phase 10)."""

import os
from pathlib import Path

import pytest
import yaml

from typer.testing import CliRunner

from vsrs.cli import app
from vsrs.core.config import (
    DatabaseConfig,
    ModelConfig,
    SandboxConfig,
    VerificationConfig,
    VSRSConfig,
)

runner = CliRunner()


class TestVSRSConfigDefaults:
    def test_default_config(self):
        config = VSRSConfig()
        assert config.database.url
        assert config.log_level == "INFO"
        assert config.model.provider == "stub"
        assert config.sandbox.use_docker is False

    def test_default_with_env_overrides(self, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", "/tmp/test.db")
        monkeypatch.setenv("VSRS_LOG_LEVEL", "DEBUG")
        config = VSRSConfig.default()
        assert config.database.url == "/tmp/test.db"
        assert config.log_level == "DEBUG"


class TestVSRSConfigFromDict:
    def test_from_dict_full(self):
        data = {
            "database": {"url": "/tmp/custom.db", "echo": True},
            "sandbox": {"use_docker": True, "worktree_dir": "/tmp/wt", "wall_time_limit_seconds": 600},
            "model": {"provider": "anthropic", "model_name": "claude-3", "max_tokens": 8192},
            "verification": {"max_repair_attempts": 5, "pytest_command": "pytest -x"},
            "log_dir": "/tmp/logs",
            "log_level": "WARNING",
        }
        config = VSRSConfig.from_dict(data)
        assert config.database.url == "/tmp/custom.db"
        assert config.database.echo is True
        assert config.sandbox.use_docker is True
        assert str(config.sandbox.worktree_dir) == "/tmp/wt"
        assert config.sandbox.wall_time_limit_seconds == 600
        assert config.model.provider == "anthropic"
        assert config.model.model_name == "claude-3"
        assert config.model.max_tokens == 8192
        assert config.verification.max_repair_attempts == 5
        assert config.verification.pytest_command == "pytest -x"
        assert str(config.log_dir) == "/tmp/logs"
        assert config.log_level == "WARNING"

    def test_from_dict_partial(self):
        data = {"log_level": "ERROR"}
        config = VSRSConfig.from_dict(data)
        assert config.log_level == "ERROR"
        # Other fields remain default
        assert config.model.provider == "stub"

    def test_from_dict_empty(self):
        config = VSRSConfig.from_dict({})
        assert config.log_level == "INFO"


class TestVSRSConfigFromYAML:
    def test_from_yaml(self, tmp_path):
        yaml_content = """
database:
  url: /tmp/test.db
  echo: true
sandbox:
  use_docker: true
  worktree_dir: /tmp/worktrees
model:
  provider: anthropic
  model_name: claude-3-opus
  temperature: 0.5
verification:
  max_repair_attempts: 5
log_level: DEBUG
"""
        config_path = tmp_path / "vsrs.yaml"
        config_path.write_text(yaml_content)

        config = VSRSConfig.from_yaml(config_path)
        assert config.database.url == "/tmp/test.db"
        assert config.database.echo is True
        assert config.sandbox.use_docker is True
        assert config.model.provider == "anthropic"
        assert config.model.temperature == 0.5
        assert config.verification.max_repair_attempts == 5
        assert config.log_level == "DEBUG"

    def test_from_yaml_empty_file(self, tmp_path):
        config_path = tmp_path / "empty.yaml"
        config_path.write_text("")

        config = VSRSConfig.from_yaml(config_path)
        assert config.log_level == "INFO"


class TestVSRSConfigSerialization:
    def test_to_dict(self):
        config = VSRSConfig()
        config.database.url = "/tmp/test.db"
        config.log_level = "DEBUG"

        data = config.to_dict()
        assert data["database"]["url"] == "/tmp/test.db"
        assert data["log_level"] == "DEBUG"
        assert "sandbox" in data
        assert "model" in data
        assert "verification" in data

    def test_to_yaml(self):
        config = VSRSConfig()
        config.log_level = "WARNING"

        yaml_str = config.to_yaml()
        assert "WARNING" in yaml_str
        assert "database" in yaml_str

    def test_roundtrip(self, tmp_path):
        config = VSRSConfig()
        config.database.url = "/tmp/roundtrip.db"
        config.log_level = "ERROR"
        config.model.provider = "anthropic"
        config.verification.max_repair_attempts = 7

        config_path = tmp_path / "roundtrip.yaml"
        config.save_yaml(config_path)

        loaded = VSRSConfig.from_yaml(config_path)
        assert loaded.database.url == "/tmp/roundtrip.db"
        assert loaded.log_level == "ERROR"
        assert loaded.model.provider == "anthropic"
        assert loaded.verification.max_repair_attempts == 7

    def test_save_yaml_creates_parent_dirs(self, tmp_path):
        config = VSRSConfig()
        config_path = tmp_path / "subdir" / "config.yaml"
        config.save_yaml(config_path)
        assert config_path.exists()


class TestVSRSConfigValidation:
    def test_valid_config(self):
        config = VSRSConfig()
        errors = config.validate()
        assert len(errors) == 0

    def test_negative_repair_attempts(self):
        config = VSRSConfig()
        config.verification.max_repair_attempts = -1
        errors = config.validate()
        assert any("max_repair_attempts" in e for e in errors)

    def test_too_many_repair_attempts(self):
        config = VSRSConfig()
        config.verification.max_repair_attempts = 20
        errors = config.validate()
        assert any("max_repair_attempts" in e for e in errors)

    def test_invalid_max_tokens(self):
        config = VSRSConfig()
        config.model.max_tokens = 0
        errors = config.validate()
        assert any("max_tokens" in e for e in errors)

    def test_invalid_temperature(self):
        config = VSRSConfig()
        config.model.temperature = 3.0
        errors = config.validate()
        assert any("temperature" in e for e in errors)

    def test_invalid_wall_time(self):
        config = VSRSConfig()
        config.sandbox.wall_time_limit_seconds = 0
        errors = config.validate()
        assert any("wall_time_limit_seconds" in e for e in errors)

    def test_invalid_log_level(self):
        config = VSRSConfig()
        config.log_level = "VERBOSE"
        errors = config.validate()
        assert any("log_level" in e for e in errors)

    def test_empty_db_url(self):
        config = VSRSConfig()
        config.database.url = ""
        errors = config.validate()
        assert any("database.url" in e for e in errors)


class TestVSRSConfigLoad:
    def test_load_with_explicit_path(self, tmp_path):
        config_path = tmp_path / "vsrs.yaml"
        config_path.write_text("log_level: DEBUG\n")

        config = VSRSConfig.load(config_path)
        assert config.log_level == "DEBUG"

    def test_load_with_env_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "custom.yaml"
        config_path.write_text("log_level: WARNING\n")

        monkeypatch.setenv("VSRS_CONFIG", str(config_path))
        config = VSRSConfig.load()
        assert config.log_level == "WARNING"

    def test_load_falls_back_to_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("VSRS_CONFIG", "")
        # Ensure no config files are found
        config = VSRSConfig.load()
        assert config.log_level == "INFO"

    def test_load_env_overrides_yaml(self, tmp_path, monkeypatch):
        config_path = tmp_path / "vsrs.yaml"
        config_path.write_text("log_level: DEBUG\n")

        monkeypatch.setenv("VSRS_LOG_LEVEL", "ERROR")
        config = VSRSConfig.load(config_path)
        assert config.log_level == "ERROR"


class TestVSRSConfigEnvOverrides:
    def test_model_env_overrides(self, monkeypatch):
        monkeypatch.setenv("VSRS_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("VSRS_MODEL_NAME", "claude-3")
        monkeypatch.setenv("VSRS_MODEL_MAX_TOKENS", "8192")
        monkeypatch.setenv("VSRS_MODEL_TEMPERATURE", "0.5")

        config = VSRSConfig.default()
        assert config.model.provider == "anthropic"
        assert config.model.model_name == "claude-3"
        assert config.model.max_tokens == 8192
        assert config.model.temperature == 0.5

    def test_sandbox_env_overrides(self, monkeypatch):
        monkeypatch.setenv("VSRS_SANDBOX_DOCKER", "true")
        monkeypatch.setenv("VSRS_SANDBOX_WORKTREE_DIR", "/tmp/wt")
        monkeypatch.setenv("VSRS_SANDBOX_WALL_TIME", "600")

        config = VSRSConfig.default()
        assert config.sandbox.use_docker is True
        assert str(config.sandbox.worktree_dir) == "/tmp/wt"
        assert config.sandbox.wall_time_limit_seconds == 600

    def test_verification_env_override(self, monkeypatch):
        monkeypatch.setenv("VSRS_MAX_REPAIR_ATTEMPTS", "5")

        config = VSRSConfig.default()
        assert config.verification.max_repair_attempts == 5

    def test_db_echo_env_override(self, monkeypatch):
        monkeypatch.setenv("VSRS_DB_ECHO", "true")

        config = VSRSConfig.default()
        assert config.database.echo is True

    def test_log_dir_env_override(self, monkeypatch):
        monkeypatch.setenv("VSRS_LOG_DIR", "/tmp/customlogs")

        config = VSRSConfig.default()
        assert str(config.log_dir) == "/tmp/customlogs"


class TestCLIConfig:
    def test_config_show(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "database" in result.stdout

    def test_config_init(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        output = tmp_path / "vsrs.yaml"
        result = runner.invoke(app, ["config", "init", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        data = yaml.safe_load(output.read_text())
        assert "database" in data
        assert "model" in data

    def test_config_validate_valid(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    def test_config_validate_invalid(self, tmp_path, monkeypatch):
        config_path = tmp_path / "bad.yaml"
        config_path.write_text("log_level: VERBOSE\n")
        result = runner.invoke(app, ["config", "validate", "--config", str(config_path)])
        assert result.exit_code == 1
        assert "invalid" in result.stdout.lower()
