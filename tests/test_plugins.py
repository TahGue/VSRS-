"""Tests for the plugin system (Phase 16)."""

import pytest

from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskType,
)
from vsrs.plugins import (
    FileSizeVerifier,
    GitLogRetriever,
    ImportCheckerVerifier,
    MinimalityCritic,
    Plugin,
    PluginInfo,
    PluginRegistry,
    PluginType,
    SecurityCritic,
    get_registry,
    register_builtins,
)
from vsrs.plugins.base import CriticPlugin, RetrieverPlugin, VerifierPlugin
from vsrs.repo.retrieval import RetrievalResult


# --- Helpers ---

def _make_patch(diff: str = "", changed_files: list[str] | None = None) -> PatchCandidate:
    return PatchCandidate(
        id="patch_001",
        task_id="task_001",
        attempt_no=1,
        base_commit="abc123",
        diff=diff,
        changed_files=changed_files or [],
        changed_symbols=[],
        assumptions=[],
        predicted_effects=[],
        falsification_checks=[],
    )


def _make_task() -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=TaskType.bugfix,
        instruction="Fix a bug",
        acceptance_criteria=["test passes"],
        risk_level=RiskLevel.low,
    )


# --- Plugin Base Tests ---

class TestPluginBase:
    def test_plugin_type_values(self):
        assert PluginType.verifier.value == "verifier"
        assert PluginType.retriever.value == "retriever"
        assert PluginType.critic.value == "critic"

    def test_plugin_info_creation(self):
        info = PluginInfo(
            name="test-plugin",
            version="0.1.0",
            plugin_type=PluginType.verifier,
            description="A test plugin",
        )
        assert info.name == "test-plugin"
        assert info.tags == []

    def test_plugin_info_with_tags(self):
        info = PluginInfo(
            name="test",
            version="1.0.0",
            plugin_type=PluginType.critic,
            tags=["security", "review"],
        )
        assert "security" in info.tags


# --- Registry Tests ---

class TestPluginRegistry:
    def test_register_and_get(self):
        reg = PluginRegistry()
        plugin = FileSizeVerifier()
        reg.register(plugin)
        assert reg.count() == 1
        assert reg.get("file-size-verifier") is plugin

    def test_register_duplicate_raises(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(FileSizeVerifier())

    def test_unregister(self):
        reg = PluginRegistry()
        plugin = FileSizeVerifier()
        reg.register(plugin)
        removed = reg.unregister("file-size-verifier")
        assert removed is plugin
        assert reg.count() == 0

    def test_unregister_not_found(self):
        reg = PluginRegistry()
        assert reg.unregister("nonexistent") is None

    def test_get_not_found(self):
        reg = PluginRegistry()
        assert reg.get("nonexistent") is None

    def test_get_by_type(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        reg.register(MinimalityCritic())
        verifiers = reg.get_by_type(PluginType.verifier)
        critics = reg.get_by_type(PluginType.critic)
        assert len(verifiers) == 1
        assert len(critics) == 1

    def test_get_verifiers(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        reg.register(ImportCheckerVerifier())
        reg.register(MinimalityCritic())
        verifiers = reg.get_verifiers()
        assert len(verifiers) == 2
        assert all(isinstance(v, VerifierPlugin) for v in verifiers)

    def test_get_retrievers(self):
        reg = PluginRegistry()
        reg.register(GitLogRetriever())
        retrievers = reg.get_retrievers()
        assert len(retrievers) == 1
        assert isinstance(retrievers[0], RetrieverPlugin)

    def test_get_critics(self):
        reg = PluginRegistry()
        reg.register(MinimalityCritic())
        reg.register(SecurityCritic())
        critics = reg.get_critics()
        assert len(critics) == 2
        assert all(isinstance(c, CriticPlugin) for c in critics)

    def test_all(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        reg.register(MinimalityCritic())
        all_plugins = reg.all()
        assert "file-size-verifier" in all_plugins
        assert "minimality-critic" in all_plugins

    def test_names(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        reg.register(MinimalityCritic())
        names = reg.names()
        assert "file-size-verifier" in names
        assert "minimality-critic" in names

    def test_clear(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        reg.clear()
        assert reg.count() == 0

    def test_info_all(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        infos = reg.info_all()
        assert len(infos) == 1
        assert infos[0].name == "file-size-verifier"

    def test_to_dict(self):
        reg = PluginRegistry()
        reg.register(FileSizeVerifier())
        d = reg.to_dict()
        assert d["count"] == 1
        assert d["plugins"][0]["name"] == "file-size-verifier"
        assert d["plugins"][0]["type"] == "verifier"


# --- Registry Singleton Tests ---

class TestRegistrySingleton:
    def test_get_registry_returns_same_instance(self):
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2

    def test_register_builtins(self):
        reg = get_registry()
        reg.clear()
        count = register_builtins()
        assert count == 5
        assert reg.count() == 5

    def test_register_builtins_idempotent(self):
        reg = get_registry()
        reg.clear()
        register_builtins()
        count = register_builtins()
        assert count == 0


# --- Verifier Plugin Tests ---

class TestFileSizeVerifier:
    def test_info(self):
        plugin = FileSizeVerifier()
        info = plugin.info
        assert info.name == "file-size-verifier"
        assert info.plugin_type == PluginType.verifier

    def test_small_diff_passes(self):
        plugin = FileSizeVerifier(max_diff_lines=100)
        patch = _make_patch(diff="+a\n+b\n+c\n")
        result = plugin.run(patch)
        assert isinstance(result, CheckResult)
        assert result.status == CheckStatus.pass_

    def test_large_diff_fails(self):
        plugin = FileSizeVerifier(max_diff_lines=3)
        diff = "\n".join(f"+line{i}" for i in range(10))
        patch = _make_patch(diff=diff)
        result = plugin.run(patch)
        assert result.status == CheckStatus.fail
        assert "exceeding max" in result.error_message

    def test_empty_diff_passes(self):
        plugin = FileSizeVerifier()
        patch = _make_patch(diff="")
        result = plugin.run(patch)
        assert result.status == CheckStatus.pass_


class TestImportCheckerVerifier:
    def test_info(self):
        plugin = ImportCheckerVerifier()
        assert plugin.info.name == "import-checker"
        assert plugin.info.plugin_type == PluginType.verifier

    def test_no_imports_passes(self):
        plugin = ImportCheckerVerifier()
        patch = _make_patch(diff="+x = 1\n+y = 2\n")
        result = plugin.run(patch)
        assert result.status == CheckStatus.pass_

    def test_used_import_passes(self):
        plugin = ImportCheckerVerifier()
        patch = _make_patch(diff="+import os\n+os.getcwd()\n")
        result = plugin.run(patch)
        assert result.status == CheckStatus.pass_

    def test_empty_diff_passes(self):
        plugin = ImportCheckerVerifier()
        patch = _make_patch(diff="")
        result = plugin.run(patch)
        assert result.status == CheckStatus.pass_


# --- Retriever Plugin Tests -----

class TestGitLogRetriever:
    def test_info(self):
        plugin = GitLogRetriever()
        assert plugin.info.name == "git-log-retriever"
        assert plugin.info.plugin_type == PluginType.retriever

    def test_no_repo_returns_empty(self):
        plugin = GitLogRetriever()
        task = _make_task()
        result = plugin.run(task, repo_path="/nonexistent/path")
        assert isinstance(result, RetrievalResult)
        assert len(result.evidence) == 0

    def test_empty_repo_path_returns_empty(self):
        plugin = GitLogRetriever()
        task = _make_task()
        result = plugin.run(task, repo_path="")
        assert len(result.evidence) == 0


# --- Critic Plugin Tests ---

class TestMinimalityCritic:
    def test_info(self):
        plugin = MinimalityCritic()
        assert plugin.info.name == "minimality-critic"
        assert plugin.info.plugin_type == PluginType.critic

    def test_empty_diff_finding(self):
        plugin = MinimalityCritic()
        patch = _make_patch(diff="")
        findings = plugin.run(patch)
        assert any(f["category"] == "empty_patch" for f in findings)
        assert any(f["severity"] == "blocker" for f in findings)

    def test_too_many_files_finding(self):
        plugin = MinimalityCritic(max_files=2)
        patch = _make_patch(
            diff="+x\n",
            changed_files=["a.py", "b.py", "c.py", "d.py"],
        )
        findings = plugin.run(patch)
        assert any(f["category"] == "overreach" for f in findings)

    def test_minimal_patch_no_findings(self):
        plugin = MinimalityCritic()
        patch = _make_patch(
            diff="+x = 1\n",
            changed_files=["a.py"],
        )
        findings = plugin.run(patch)
        assert len(findings) == 0


class TestSecurityCritic:
    def test_info(self):
        plugin = SecurityCritic()
        assert plugin.info.name == "security-critic"
        assert plugin.info.plugin_type == PluginType.critic

    def test_eval_finding(self):
        plugin = SecurityCritic()
        patch = _make_patch(diff="+result = eval(user_input)\n")
        findings = plugin.run(patch)
        assert any(f["category"] == "security" for f in findings)
        assert any("eval" in f["text"].lower() for f in findings)

    def test_hardcoded_password_finding(self):
        plugin = SecurityCritic()
        patch = _make_patch(diff="+password = 'secret123'\n")
        findings = plugin.run(patch)
        assert any(f["category"] == "security" for f in findings)

    def test_safe_code_no_findings(self):
        plugin = SecurityCritic()
        patch = _make_patch(diff="+x = 1 + 2\n")
        findings = plugin.run(patch)
        assert len(findings) == 0

    def test_empty_diff_no_findings(self):
        plugin = SecurityCritic()
        patch = _make_patch(diff="")
        findings = plugin.run(patch)
        assert len(findings) == 0


# --- Entry Point Discovery Tests ---

class TestEntryPointDiscovery:
    def test_discover_finds_plugins(self):
        reg = PluginRegistry()
        count = reg.discover()
        # Should find 5 built-in plugins via entry points
        assert count == 5
        assert reg.count() == 5
        assert "file-size-verifier" in reg.names()

    def test_discover_idempotent(self):
        reg = PluginRegistry()
        reg.discover()
        count = reg.discover()
        assert count == 0
