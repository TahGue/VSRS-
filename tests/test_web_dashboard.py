"""Tests for the web dashboard (Phase 22).

Tests the dashboard file structure, API endpoints it consumes,
and the FastAPI static file serving capability.
"""

import json
import pytest
from pathlib import Path

from vsrs.api.app import create_app


# --- Dashboard Structure Tests ---

class TestDashboardStructure:
    def test_package_json_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "package.json").exists()

    def test_tsconfig_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "tsconfig.json").exists()

    def test_vite_config_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "vite.config.ts").exists()

    def test_index_html_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "index.html").exists()

    def test_main_tsx_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "main.tsx").exists()

    def test_app_tsx_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "App.tsx").exists()

    def test_api_ts_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "api.ts").exists()

    def test_types_ts_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "types.ts").exists()

    def test_index_css_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "index.css").exists()

    def test_readme_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "README.md").exists()

    def test_pages_dir_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "pages").is_dir()

    def test_runs_page_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "pages" / "RunsPage.tsx").exists()

    def test_run_detail_page_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "pages" / "RunDetailPage.tsx").exists()

    def test_benchmarks_page_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "pages" / "BenchmarksPage.tsx").exists()

    def test_settings_page_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "pages" / "SettingsPage.tsx").exists()


# --- Package.json Content Tests ---

class TestDashboardPackageJson:
    @pytest.fixture
    def pkg(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        with open(dash_dir / "package.json") as f:
            return json.load(f)

    def test_name(self, pkg):
        assert pkg["name"] == "vsrs-dashboard"

    def test_react_dependency(self, pkg):
        assert "react" in pkg["dependencies"]

    def test_react_router_dependency(self, pkg):
        assert "react-router-dom" in pkg["dependencies"]

    def test_vite_dev_dependency(self, pkg):
        assert "vite" in pkg["devDependencies"]

    def test_scripts(self, pkg):
        assert "dev" in pkg["scripts"]
        assert "build" in pkg["scripts"]
        assert "preview" in pkg["scripts"]


# --- TypeScript Source Content Tests ---

class TestDashboardSource:
    def test_main_has_router(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "main.tsx").read_text()
        assert "BrowserRouter" in content
        assert "Routes" in content

    def test_app_has_sidebar(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "App.tsx").read_text()
        assert "sidebar" in content
        assert "NavLink" in content

    def test_api_has_endpoints(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "api.ts").read_text()
        assert "listRuns" in content
        assert "createRun" in content
        assert "getRun" in content
        assert "getRunVerification" in content
        assert "getRunDiff" in content
        assert "getConfig" in content
        assert "listBenchmarks" in content

    def test_types_define_interfaces(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "types.ts").read_text()
        assert "interface Run" in content
        assert "interface Task" in content
        assert "interface VerificationReport" in content
        assert "interface CheckResult" in content
        assert "interface Patch" in content

    def test_runs_page_has_form(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "pages" / "RunsPage.tsx").read_text()
        assert "createRun" in content
        assert "form" in content.lower()

    def test_run_detail_has_verification(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "pages" / "RunDetailPage.tsx").read_text()
        assert "verification" in content.lower()
        assert "check" in content.lower()

    def test_run_detail_has_diff_viewer(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "pages" / "RunDetailPage.tsx").read_text()
        assert "diff" in content.lower()

    def test_benchmarks_page_lists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "pages" / "BenchmarksPage.tsx").read_text()
        assert "listBenchmarks" in content

    def test_settings_page_shows_config(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "pages" / "SettingsPage.tsx").read_text()
        assert "getConfig" in content

    def test_css_has_dark_theme(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "index.css").read_text()
        assert "--bg" in content
        assert "--surface" in content
        assert "--text" in content

    def test_vite_config_has_proxy(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "vite.config.ts").read_text()
        assert "proxy" in content
        assert "localhost:8000" in content


# --- API Endpoint Compatibility Tests ---

class TestDashboardAPICompatibility:
    """Verify the API endpoints the dashboard uses are available."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_create_run(self, client, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1\n")
        response = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Fix bug",
            "task_type": "bugfix",
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert "run_id" in data

    def test_get_run(self, client, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1\n")
        create = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Test",
            "task_type": "bugfix",
        })
        run_id = create.json()["run_id"]
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200

    def test_get_run_task(self, client, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("x = 1\n")
        create = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Test",
            "task_type": "bugfix",
        })
        run_id = create.json()["run_id"]
        response = client.get(f"/api/v1/runs/{run_id}/task")
        assert response.status_code == 200

    def test_get_config(self, client):
        response = client.get("/api/v1/config")
        assert response.status_code == 200

    def test_list_benchmarks(self, client):
        response = client.get("/api/v1/benchmarks")
        assert response.status_code == 200
