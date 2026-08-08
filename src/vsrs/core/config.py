"""Configuration management for VSRS.

Supports:
- YAML config files (discovered from VSRS_CONFIG env var, ./vsrs.yaml, ~/.vsrs/config.yaml)
- Environment variable overrides for all settings
- Programmatic construction via from_dict / from_yaml
- Serialization via to_dict / to_yaml
- Validation of required fields and value ranges
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

# Environment variable prefix for VSRS config overrides
_ENV_PREFIX = "VSRS_"

# Config file search paths (in priority order)
_CONFIG_SEARCH_PATHS = [
    Path("vsrs.yaml"),
    Path("vsrs.yml"),
    Path.home() / ".vsrs" / "config.yaml",
    Path.home() / ".vsrs" / "config.yml",
]


@dataclass
class SandboxConfig:
    """Sandbox isolation settings."""

    use_docker: bool = False
    worktree_dir: Path = field(default_factory=lambda: Path.home() / ".vsrs" / "worktrees")
    network_disabled: bool = True
    cpu_limit: str | None = None
    memory_limit: str | None = None
    wall_time_limit_seconds: int = 300
    mount_paths: list[str] = field(default_factory=list)


@dataclass
class ModelConfig:
    """Model interface settings."""

    provider: str = "openai"
    model_name: str = "gpt-4o"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.2


@dataclass
class VerificationConfig:
    """Verification pipeline settings."""

    max_repair_attempts: int = 3
    required_gates: list[str] = field(default_factory=lambda: ["syntax", "build", "existing_tests"])
    optional_gates: list[str] = field(default_factory=lambda: ["type_check", "lint", "static_analysis"])
    pytest_command: str = "pytest"
    ruff_command: str = "ruff check"
    mypy_command: str = "mypy"
    bandit_command: str = "bandit -r"


@dataclass
class DatabaseConfig:
    """Database settings."""

    url: str = field(default_factory=lambda: str(Path.home() / ".vsrs" / "vsrs.db"))
    echo: bool = False


@dataclass
class VSRSConfig:
    """Top-level configuration for VSRS."""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    log_dir: Path = field(default_factory=lambda: Path.home() / ".vsrs" / "logs")
    log_level: str = "INFO"

    @classmethod
    def from_yaml(cls, path: Path) -> VSRSConfig:
        """Load configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> VSRSConfig:
        """Build configuration from a dictionary."""
        config = cls()
        if "database" in data:
            config.database = DatabaseConfig(**data["database"])
        if "sandbox" in data:
            sb = data["sandbox"]
            if "worktree_dir" in sb:
                sb["worktree_dir"] = Path(sb["worktree_dir"])
            config.sandbox = SandboxConfig(**sb)
        if "model" in data:
            config.model = ModelConfig(**data["model"])
        if "verification" in data:
            config.verification = VerificationConfig(**data["verification"])
        if "log_dir" in data:
            config.log_dir = Path(data["log_dir"])
        if "log_level" in data:
            config.log_level = data["log_level"]
        return config

    @classmethod
    def default(cls) -> VSRSConfig:
        """Create a default configuration with environment overrides."""
        config = cls()
        cls._apply_env_overrides(config)
        return config

    @classmethod
    def load(cls, config_path: Path | None = None) -> VSRSConfig:
        """Load configuration from file or discovery.

        Priority (highest first):
        1. Explicit config_path argument
        2. VSRS_CONFIG environment variable
        3. ./vsrs.yaml or ./vsrs.yml in current directory
        4. ~/.vsrs/config.yaml or ~/.vsrs/config.yml
        5. Built-in defaults with env overrides
        """
        path = cls._discover_config_path(config_path)
        if path and path.exists():
            config = cls.from_yaml(path)
        else:
            config = cls()
        cls._apply_env_overrides(config)
        return config

    @classmethod
    def _discover_config_path(cls, explicit: Path | None = None) -> Path | None:
        """Find the config file to use."""
        if explicit:
            return explicit
        env_path = os.environ.get(f"{_ENV_PREFIX}CONFIG")
        if env_path:
            return Path(env_path)
        for candidate in _CONFIG_SEARCH_PATHS:
            if candidate.exists():
                return candidate
        return None

    @classmethod
    def _apply_env_overrides(cls, config: VSRSConfig) -> None:
        """Apply environment variable overrides to a config."""
        db_path = os.environ.get(f"{_ENV_PREFIX}DB_PATH")
        if db_path:
            config.database.url = db_path

        log_level = os.environ.get(f"{_ENV_PREFIX}LOG_LEVEL")
        if log_level:
            config.log_level = log_level

        log_dir = os.environ.get(f"{_ENV_PREFIX}LOG_DIR")
        if log_dir:
            config.log_dir = Path(log_dir)

        # Model overrides
        model_provider = os.environ.get(f"{_ENV_PREFIX}MODEL_PROVIDER")
        if model_provider:
            config.model.provider = model_provider

        model_name = os.environ.get(f"{_ENV_PREFIX}MODEL_NAME")
        if model_name:
            config.model.model_name = model_name

        model_api_key_env = os.environ.get(f"{_ENV_PREFIX}MODEL_API_KEY_ENV")
        if model_api_key_env:
            config.model.api_key_env = model_api_key_env

        model_base_url = os.environ.get(f"{_ENV_PREFIX}MODEL_BASE_URL")
        if model_base_url:
            config.model.base_url = model_base_url

        model_max_tokens = os.environ.get(f"{_ENV_PREFIX}MODEL_MAX_TOKENS")
        if model_max_tokens:
            config.model.max_tokens = int(model_max_tokens)

        model_temp = os.environ.get(f"{_ENV_PREFIX}MODEL_TEMPERATURE")
        if model_temp:
            config.model.temperature = float(model_temp)

        # Sandbox overrides
        sandbox_docker = os.environ.get(f"{_ENV_PREFIX}SANDBOX_DOCKER")
        if sandbox_docker:
            config.sandbox.use_docker = sandbox_docker.lower() in ("1", "true", "yes")

        sandbox_worktree = os.environ.get(f"{_ENV_PREFIX}SANDBOX_WORKTREE_DIR")
        if sandbox_worktree:
            config.sandbox.worktree_dir = Path(sandbox_worktree)

        sandbox_network = os.environ.get(f"{_ENV_PREFIX}SANDBOX_NETWORK_DISABLED")
        if sandbox_network:
            config.sandbox.network_disabled = sandbox_network.lower() in ("1", "true", "yes")

        sandbox_walltime = os.environ.get(f"{_ENV_PREFIX}SANDBOX_WALL_TIME")
        if sandbox_walltime:
            config.sandbox.wall_time_limit_seconds = int(sandbox_walltime)

        # Verification overrides
        max_repair = os.environ.get(f"{_ENV_PREFIX}MAX_REPAIR_ATTEMPTS")
        if max_repair:
            config.verification.max_repair_attempts = int(max_repair)

        db_echo = os.environ.get(f"{_ENV_PREFIX}DB_ECHO")
        if db_echo:
            config.database.echo = db_echo.lower() in ("1", "true", "yes")

    def to_dict(self) -> dict:
        """Serialize config to a dictionary."""
        data = asdict(self)
        # Convert Path objects to strings
        data["database"]["url"] = str(self.database.url)
        data["sandbox"]["worktree_dir"] = str(self.sandbox.worktree_dir)
        data["log_dir"] = str(self.log_dir)
        return data

    def to_yaml(self) -> str:
        """Serialize config to a YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    def save_yaml(self, path: Path) -> None:
        """Save configuration to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_yaml())

    def validate(self) -> list[str]:
        """Validate the configuration.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        errors: list[str] = []

        if self.verification.max_repair_attempts < 0:
            errors.append("verification.max_repair_attempts must be >= 0")

        if self.verification.max_repair_attempts > 10:
            errors.append("verification.max_repair_attempts should be <= 10")

        if self.model.max_tokens <= 0:
            errors.append("model.max_tokens must be > 0")

        if not (0.0 <= self.model.temperature <= 2.0):
            errors.append("model.temperature must be between 0.0 and 2.0")

        if self.sandbox.wall_time_limit_seconds <= 0:
            errors.append("sandbox.wall_time_limit_seconds must be > 0")

        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_log_levels:
            errors.append(f"log_level must be one of {valid_log_levels}")

        if not self.database.url:
            errors.append("database.url must not be empty")

        return errors

    def ensure_dirs(self) -> None:
        """Create necessary directories."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.worktree_dir.mkdir(parents=True, exist_ok=True)
        Path(self.database.url).parent.mkdir(parents=True, exist_ok=True)
