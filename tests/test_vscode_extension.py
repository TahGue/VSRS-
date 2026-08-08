"""Tests for VSCode extension integration (Phase 21).

Tests the API endpoints and data structures that the VSCode extension
relies on. Since the extension itself is TypeScript, these tests verify
the Python backend API surface that the extension consumes.
"""

import json
import pytest
from pathlib import Path

from vsrs.api.app import create_app
from vsrs.core.schemas import (
    FinalStatus,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskType,
    VerificationReport,
    CheckResult,
    CheckStatus,
)


# --- Extension Package Structure Tests ---

class TestExtensionStructure:
    def test_package_json_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "package.json").exists()

    def test_tsconfig_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "tsconfig.json").exists()

    def test_extension_ts_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "src" / "extension.ts").exists()

    def test_types_ts_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "src" / "types.ts").exists()

    def test_api_client_ts_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "src" / "apiClient.ts").exists()

    def test_task_tree_provider_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "src" / "taskTreeProvider.ts").exists()

    def test_status_bar_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "src" / "statusBar.ts").exists()

    def test_results_panel_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "src" / "resultsPanel.ts").exists()

    def test_icon_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "media" / "vsrs-icon.svg").exists()

    def test_readme_exists(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        assert (ext_dir / "README.md").exists()


# --- Package.json Content Tests ---

class TestPackageJson:
    @pytest.fixture
    def pkg(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        with open(ext_dir / "package.json") as f:
            return json.load(f)

    def test_name(self, pkg):
        assert pkg["name"] == "vsrs-vscode"

    def test_display_name(self, pkg):
        assert "VSRS" in pkg["displayName"]

    def test_main(self, pkg):
        assert pkg["main"] == "./out/extension.js"

    def test_commands(self, pkg):
        commands = pkg["contributes"]["commands"]
        cmd_ids = [c["command"] for c in commands]
        assert "vsrs.runVerification" in cmd_ids
        assert "vsrs.runRepair" in cmd_ids
        assert "vsrs.runBenchmark" in cmd_ids
        assert "vsrs.connectServer" in cmd_ids
        assert "vsrs.disconnectServer" in cmd_ids
        assert "vsrs.refreshTasks" in cmd_ids
        assert "vsrs.viewResults" in cmd_ids
        assert "vsrs.viewTaskDetails" in cmd_ids
        assert "vsrs.cancelTask" in cmd_ids
        assert "vsrs.showSettings" in cmd_ids

    def test_views(self, pkg):
        views = pkg["contributes"]["views"]
        assert "vsrs-sidebar" in views
        view_ids = [v["id"] for v in views["vsrs-sidebar"]]
        assert "vsrs.tasksView" in view_ids

    def test_configuration(self, pkg):
        config = pkg["contributes"]["configuration"]["properties"]
        assert "vsrs.serverUrl" in config
        assert "vsrs.apiKey" in config
        assert "vsrs.maxAttempts" in config
        assert "vsrs.timeout" in config
        assert "vsrs.requiredGates" in config
        assert "vsrs.autoRunVerification" in config

    def test_keybindings(self, pkg):
        keybindings = pkg["contributes"]["keybindings"]
        commands = [kb["command"] for kb in keybindings]
        assert "vsrs.runVerification" in commands
        assert "vsrs.runRepair" in commands

    def test_view_container(self, pkg):
        containers = pkg["contributes"]["viewsContainers"]["activitybar"]
        assert any(c["id"] == "vsrs-sidebar" for c in containers)


# --- TypeScript Source Content Tests ---

class TestTypeScriptSource:
    def test_extension_exports_activate(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        content = (ext_dir / "src" / "extension.ts").read_text()
        assert "export function activate" in content
        assert "export function deactivate" in content

    def test_api_client_implements_interface(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        content = (ext_dir / "src" / "apiClient.ts").read_text()
        assert "class VSRSApiClient" in content
        assert "implements VSRSClient" in content

    def test_types_define_client_interface(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        content = (ext_dir / "src" / "types.ts").read_text()
        assert "interface VSRSClient" in content
        assert "interface ServerConfig" in content
        assert "interface TaskInfo" in content
        assert "interface VerificationReport" in content
        assert "interface BenchmarkResult" in content

    def test_tree_provider_extends_tree_data_provider(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        content = (ext_dir / "src" / "taskTreeProvider.ts").read_text()
        assert "TaskTreeProvider" in content
        assert "TreeDataProvider" in content

    def test_status_bar_uses_status_bar_item(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        content = (ext_dir / "src" / "statusBar.ts").read_text()
        assert "StatusBarItem" in content
        assert "createStatusBarItem" in content

    def test_results_panel_uses_webview(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        content = (ext_dir / "src" / "resultsPanel.ts").read_text()
        assert "WebviewPanel" in content
        assert "createWebviewPanel" in content
        assert "showVerificationReport" in content
        assert "showBenchmarkResult" in content

    def test_extension_registers_all_commands(self):
        ext_dir = Path(__file__).parent.parent / "vscode-extension"
        content = (ext_dir / "src" / "extension.ts").read_text()
        for cmd in [
            "vsrs.connectServer",
            "vsrs.disconnectServer",
            "vsrs.runVerification",
            "vsrs.runRepair",
            "vsrs.runBenchmark",
            "vsrs.viewResults",
            "vsrs.refreshTasks",
            "vsrs.viewTaskDetails",
            "vsrs.cancelTask",
            "vsrs.showSettings",
        ]:
            assert cmd in content, f"Command {cmd} not registered in extension.ts"


# --- API Endpoint Tests (Extension Backend) ---

class TestAPIEndpoints:
    """Test that the API server provides the endpoints the extension needs."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_create_run_endpoint(self, client, tmp_path):
        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1\n")
        response = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Fix a bug",
            "task_type": "bugfix",
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert "run_id" in data
        assert "task_id" in data

    def test_get_run_endpoint(self, client, tmp_path):
        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1\n")
        create_resp = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Test task",
            "task_type": "bugfix",
        })
        run_id = create_resp.json()["run_id"]
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["run_id"] == run_id

    def test_get_run_task_endpoint(self, client, tmp_path):
        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1\n")
        create_resp = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Test task",
            "task_type": "bugfix",
        })
        run_id = create_resp.json()["run_id"]
        response = client.get(f"/api/v1/runs/{run_id}/task")
        assert response.status_code == 200
        assert "instruction" in response.json()

    def test_get_run_verification_endpoint(self, client, tmp_path):
        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1\n")
        create_resp = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Test task",
            "task_type": "bugfix",
        })
        run_id = create_resp.json()["run_id"]
        # Fresh run won't have verification reports yet
        response = client.get(f"/api/v1/runs/{run_id}/verify")
        assert response.status_code in (200, 404)

    def test_get_config_endpoint(self, client):
        response = client.get("/api/v1/config")
        assert response.status_code == 200

    def test_list_benchmarks_endpoint(self, client):
        response = client.get("/api/v1/benchmarks")
        assert response.status_code == 200


# --- Data Structure Compatibility Tests ---

class TestDataStructures:
    """Verify that Python data structures serialize to JSON
    that matches what the TypeScript types expect."""

    def test_check_result_json(self):
        check = CheckResult(
            check_type="syntax",
            command="python -m py_compile",
            exit_code=0,
            status=CheckStatus.pass_,
            duration_seconds=0.5,
            error_message="",
        )
        # The extension expects: check_type, command, exit_code, status,
        # duration_seconds, error_message
        d = check.model_dump(mode="json")
        assert "check_type" in d
        assert "command" in d
        assert "exit_code" in d
        assert "status" in d
        assert "duration_seconds" in d
        assert "error_message" in d

    def test_verification_report_json(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[],
            required_passed=True,
            blockers=[],
            unresolved_unknowns=[],
            final_status=FinalStatus.verified_candidate,
        )
        d = report.model_dump(mode="json")
        # Extension expects: patch_id, checks, required_passed, blockers, final_status
        assert "patch_id" in d
        assert "checks" in d
        assert "required_passed" in d
        assert "blockers" in d
        assert "final_status" in d

    def test_task_json(self):
        task = Task(
            id="task_001",
            repo_snapshot_id="repo_001",
            type=TaskType.bugfix,
            instruction="Fix a bug",
            acceptance_criteria=["test passes"],
            risk_level=RiskLevel.low,
            required_gates=["syntax", "build"],
        )
        d = task.model_dump(mode="json")
        # Extension expects: id, type, instruction, status, created_at, updated_at
        assert "id" in d
        assert "type" in d
        assert "instruction" in d
