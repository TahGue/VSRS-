"""Test index: test name, target module, markers (Section 6.1).

Discovers test files, test functions, pytest configuration, and build/test
commands from repository configuration files.
"""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger

logger = get_logger("repo.tests")


@dataclass
class TestEntry:
    """A single discovered test."""

    name: str
    file: str  # relative path
    start_line: int
    target_module: str = ""  # the module being tested, if detectable
    markers: list[str] = field(default_factory=list)
    is_async: bool = False
    test_type: str = "unit"  # unit, integration, e2e


@dataclass
class ProjectConfig:
    """Discovered project configuration for building and testing."""

    build_command: str = ""
    test_command: str = "pytest"
    lint_command: str = ""
    type_check_command: str = ""
    security_command: str = ""
    test_dir: str = "tests"
    src_dir: str = "src"
    python_version: str = ""
    has_pytest: bool = False
    has_ruff: bool = False
    has_mypy: bool = False
    has_bandit: bool = False
    pytest_markers: list[str] = field(default_factory=list)
    pytest_config_file: str = ""
    config_source: str = ""


class TestIndex:
    """Index of test files, test functions, and project configuration.

    Provides:
    - Test discovery from test directories
    - Test-to-module mapping (which tests test which modules)
    - Project config discovery (build/test/lint/type commands)
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self._tests: list[TestEntry] = []
        self._by_file: dict[str, list[TestEntry]] = {}
        self._by_name: dict[str, TestEntry] = {}
        self._by_target: dict[str, list[TestEntry]] = {}  # target module -> tests
        self._config: ProjectConfig | None = None

    def discover_tests(self, file_entries: list[tuple[str, str]]) -> list[TestEntry]:
        """Discover test functions from file contents.

        Args:
            file_entries: List of (relative_path, content) tuples for test files.

        Returns:
            List of discovered test entries.
        """
        self._tests.clear()
        self._by_file.clear()
        self._by_name.clear()
        self._by_target.clear()

        for rel_path, content in file_entries:
            if not self._is_test_file(rel_path):
                continue
            entries = self._extract_tests(rel_path, content)
            for entry in entries:
                self._add(entry)

        logger.info(f"Discovered {len(self._tests)} tests in {len(self._by_file)} files")
        return list(self._tests)

    def _is_test_file(self, rel_path: str) -> bool:
        """Check if a file is a test file."""
        name = Path(rel_path).name
        return name.startswith("test_") and name.endswith(".py") or name == "conftest.py"

    def _extract_tests(self, file_path: str, content: str) -> list[TestEntry]:
        """Extract test functions from a test file."""
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return []

        entries: list[TestEntry] = []
        target_module = self._guess_target_module(file_path)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    entry = TestEntry(
                        name=node.name,
                        file=file_path,
                        start_line=node.lineno,
                        target_module=target_module,
                        is_async=isinstance(node, ast.AsyncFunctionDef),
                        markers=self._extract_markers(node),
                        test_type=self._classify_test(file_path, node.name),
                    )
                    entries.append(entry)

        return entries

    def _guess_target_module(self, test_file: str) -> str:
        """Guess which module a test file is testing.

        Convention: tests/test_auth.py -> src/auth.py (module: src.auth)
        """
        name = Path(test_file).stem
        if name.startswith("test_"):
            name = name[5:]
        return name

    def _extract_markers(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Extract pytest markers from decorators."""
        markers: list[str] = []
        for dec in node.decorator_list:
            # @pytest.mark.xxx or @mark.xxx
            if isinstance(dec, ast.Attribute):
                parts = self._format_attribute(dec)
                if "mark" in parts:
                    marker_name = parts.split("mark.")[-1].split("(")[0].strip()
                    if marker_name:
                        markers.append(marker_name)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Attribute):
                    parts = self._format_attribute(dec.func)
                    if "mark" in parts:
                        marker_name = parts.split("mark.")[-1].strip()
                        if marker_name:
                            markers.append(marker_name)
        return markers

    def _format_attribute(self, node: ast.Attribute) -> str:
        """Format an attribute node as a string."""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        if isinstance(node.value, ast.Attribute):
            return f"{self._format_attribute(node.value)}.{node.attr}"
        return node.attr

    def _classify_test(self, file_path: str, test_name: str) -> str:
        """Classify a test as unit, integration, or e2e."""
        path_lower = file_path.lower()
        if "integration" in path_lower or "integration" in test_name.lower():
            return "integration"
        if "e2e" in path_lower or "e2e" in test_name.lower():
            return "e2e"
        return "unit"

    def _add(self, entry: TestEntry) -> None:
        """Add a test entry to all indexes."""
        self._tests.append(entry)
        self._by_file.setdefault(entry.file, []).append(entry)
        self._by_name[entry.name] = entry
        if entry.target_module:
            self._by_target.setdefault(entry.target_module, []).append(entry)

    # --- Config discovery ---

    def discover_config(self) -> ProjectConfig:
        """Discover project configuration from config files.

        Checks pyproject.toml, setup.cfg, tox.ini, pytest.ini, conftest.py,
        Makefile, and requirements files.
        """
        config = ProjectConfig()

        # Try pyproject.toml first
        pyproject = self.repo_root / "pyproject.toml"
        if pyproject.exists():
            config = self._parse_pyproject(pyproject)
            config.config_source = "pyproject.toml"

        # Try setup.cfg
        setup_cfg = self.repo_root / "setup.cfg"
        if setup_cfg.exists() and not config.config_source:
            config = self._parse_setup_cfg(setup_cfg)
            config.config_source = "setup.cfg"

        # Try pytest.ini
        pytest_ini = self.repo_root / "pytest.ini"
        if pytest_ini.exists():
            config = self._parse_pytest_ini(pytest_ini, config)
            if not config.config_source:
                config.config_source = "pytest.ini"

        # Try tox.ini
        tox_ini = self.repo_root / "tox.ini"
        if tox_ini.exists():
            config = self._parse_tox_ini(tox_ini, config)
            if not config.config_source:
                config.config_source = "tox.ini"

        # Try Makefile for build/test commands
        makefile = self.repo_root / "Makefile"
        if makefile.exists():
            config = self._parse_makefile(makefile, config)

        # Check for tool availability
        config.has_pytest = self._has_tool("pytest")
        config.has_ruff = self._has_tool("ruff")
        config.has_mypy = self._has_tool("mypy")
        config.has_bandit = self._has_tool("bandit")

        # Set defaults
        if not config.test_command:
            config.test_command = "pytest"
        if not config.lint_command and config.has_ruff:
            config.lint_command = "ruff check"
        if not config.type_check_command and config.has_mypy:
            config.type_check_command = "mypy"
        if not config.security_command and config.has_bandit:
            config.security_command = "bandit -r"

        self._config = config
        logger.info(
            f"Project config: test={config.test_command}, "
            f"lint={config.lint_command}, type={config.type_check_command}"
        )
        return config

    def _parse_pyproject(self, path: Path) -> ProjectConfig:
        """Parse pyproject.toml for project config."""
        config = ProjectConfig()
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            logger.warning(f"Could not parse {path}: {e}")
            return config

        # Pytest config
        pytest_section = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
        if pytest_section:
            config.has_pytest = True
            config.pytest_markers = pytest_section.get("markers", [])
            config.test_dir = pytest_section.get("testpaths", ["tests"])[0] if pytest_section.get("testpaths") else "tests"

        # Ruff config
        if "ruff" in data.get("tool", {}):
            config.has_ruff = True
            config.lint_command = "ruff check"

        # Mypy config
        if "mypy" in data.get("tool", {}):
            config.has_mypy = True
            config.type_check_command = "mypy"

        # Build system
        build_backend = data.get("build-system", {}).get("build-backend", "")
        if build_backend:
            config.build_command = "pip install -e ."

        # Project metadata
        project = data.get("project", {})
        config.python_version = project.get("requires-python", "")

        return config

    def _parse_setup_cfg(self, path: Path) -> ProjectConfig:
        """Parse setup.cfg for project config."""
        config = ProjectConfig()
        try:
            content = path.read_text()
        except OSError:
            return config

        # Parse [tool:pytest] section
        pytest_match = re.search(r"\[tool:pytest\](.*?)(?:\n\[|\Z)", content, re.DOTALL)
        if pytest_match:
            config.has_pytest = True
            section = pytest_match.group(1)
            testpaths = re.search(r"testpaths\s*=\s*(.+)", section)
            if testpaths:
                config.test_dir = testpaths.group(1).strip().split("\n")[0].strip()

        return config

    def _parse_pytest_ini(self, path: Path, config: ProjectConfig) -> ProjectConfig:
        """Parse pytest.ini for test config."""
        try:
            content = path.read_text()
        except OSError:
            return config

        config.has_pytest = True
        testpaths = re.search(r"testpaths\s*=\s*(.+)", content)
        if testpaths:
            config.test_dir = testpaths.group(1).strip().split("\n")[0].strip()

        markers_match = re.findall(r"markers\s*=\s*\n((?:\s+\S+.*\n?)+)", content)
        if markers_match:
            for line in markers_match[0].strip().splitlines():
                marker = line.strip().split(":")[0].strip()
                if marker:
                    config.pytest_markers.append(marker)

        return config

    def _parse_tox_ini(self, path: Path, config: ProjectConfig) -> ProjectConfig:
        """Parse tox.ini for test/build commands."""
        try:
            content = path.read_text()
        except OSError:
            return config

        # Look for [testenv] section
        testenv_match = re.search(r"\[testenv\](.*?)(?:\n\[|\Z)", content, re.DOTALL)
        if testenv_match:
            section = testenv_match.group(1)
            commands = re.search(r"commands\s*=\s*\n((?:\s+\S+.*\n?)+)", section)
            if commands:
                first_cmd = commands.group(1).strip().splitlines()[0].strip()
                config.test_command = first_cmd

        return config

    def _parse_makefile(self, path: Path, config: ProjectConfig) -> ProjectConfig:
        """Parse Makefile for build/test targets."""
        try:
            content = path.read_text()
        except OSError:
            return config

        if not config.build_command:
            build_match = re.search(r"^build?:.*\n\t(.+)", content, re.MULTILINE)
            if build_match:
                config.build_command = build_match.group(1).strip()

        test_match = re.search(r"^test?:.*\n\t(.+)", content, re.MULTILINE)
        if test_match:
            config.test_command = test_match.group(1).strip()

        lint_match = re.search(r"^lint?:.*\n\t(.+)", content, re.MULTILINE)
        if lint_match:
            config.lint_command = lint_match.group(1).strip()

        return config

    def _has_tool(self, tool_name: str) -> bool:
        """Check if a tool is available by looking for its config or in requirements."""
        # Check for config files
        config_indicators = {
            "pytest": ["pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py"],
            "ruff": ["ruff.toml", "pyproject.toml"],
            "mypy": ["mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg"],
            "bandit": [".bandit", "pyproject.toml", "bandit.yml"],
        }
        indicators = config_indicators.get(tool_name, [])
        for indicator in indicators:
            if (self.repo_root / indicator).exists():
                # For pyproject.toml, check if the tool section exists
                if indicator == "pyproject.toml":
                    try:
                        with open(self.repo_root / indicator, "rb") as f:
                            data = tomllib.load(f)
                        if tool_name in data.get("tool", {}):
                            return True
                        # pytest is special — might be under [tool.pytest]
                        if tool_name == "pytest" and "pytest" in data.get("tool", {}):
                            return True
                    except Exception:
                        pass
                else:
                    return True

        # Also check requirements files
        for req_file in ["requirements.txt", "requirements-dev.txt", "pyproject.toml"]:
            req_path = self.repo_root / req_file
            if req_path.exists():
                try:
                    content = req_path.read_text()
                    if tool_name in content:
                        return True
                except OSError:
                    pass

        return False

    # --- Query methods ---

    @property
    def config(self) -> ProjectConfig | None:
        """Get the discovered project config."""
        return self._config

    def all_tests(self) -> list[TestEntry]:
        """Get all discovered tests."""
        return list(self._tests)

    def tests_in_file(self, file_path: str) -> list[TestEntry]:
        """Get all tests in a specific file."""
        return self._by_file.get(file_path, [])

    def find_by_name(self, name: str) -> TestEntry | None:
        """Find a test by name."""
        return self._by_name.get(name)

    def tests_for_module(self, module_name: str) -> list[TestEntry]:
        """Get all tests targeting a given module."""
        return self._by_target.get(module_name, [])

    def tests_by_type(self, test_type: str) -> list[TestEntry]:
        """Get tests by type (unit, integration, e2e)."""
        return [t for t in self._tests if t.test_type == test_type]

    def tests_by_marker(self, marker: str) -> list[TestEntry]:
        """Get tests with a specific marker."""
        return [t for t in self._tests if marker in t.markers]

    @property
    def test_count(self) -> int:
        """Total number of discovered tests."""
        return len(self._tests)

    @property
    def test_file_count(self) -> int:
        """Number of test files."""
        return len(self._by_file)
