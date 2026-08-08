"""Built-in example plugins for VSRS.

These plugins demonstrate the plugin system and can be used as templates
for custom plugins. They are not auto-registered — users must register
them explicitly or via entry points.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskType,
)
from vsrs.plugins.base import (
    CriticPlugin,
    PluginInfo,
    PluginType,
    RetrieverPlugin,
    VerifierPlugin,
)
from vsrs.repo.retrieval import RetrievalResult, RetrievedEvidence


class FileSizeVerifier(VerifierPlugin):
    """Verifier plugin that checks patch diff size.

    Fails if the diff exceeds a configurable maximum line count,
    encouraging minimal patches.
    """

    def __init__(self, max_diff_lines: int = 500) -> None:
        self._max_diff_lines = max_diff_lines

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="file-size-verifier",
            version="0.1.0",
            plugin_type=PluginType.verifier,
            description="Checks that patch diffs don't exceed a maximum line count",
            tags=["minimality", "diff-size"],
        )

    def run(
        self,
        patch: PatchCandidate,
        repo_path: str = "",
        **kwargs: Any,
    ) -> CheckResult:
        diff_lines = len([l for l in patch.diff.split("\n") if l.startswith(("+", "-"))])
        passed = diff_lines <= self._max_diff_lines

        return CheckResult(
            check_type="diff_size",
            command=f"diff-line-count (max={self._max_diff_lines})",
            status=CheckStatus.pass_ if passed else CheckStatus.fail,
            error_message=(
                f"Diff has {diff_lines} changed lines, exceeding max of {self._max_diff_lines}"
                if not passed else ""
            ),
        )


class ImportCheckerVerifier(VerifierPlugin):
    """Verifier plugin that checks for unused imports in changed files.

    Scans added lines for import statements and checks if the imported
    names appear in the rest of the diff.
    """

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="import-checker",
            version="0.1.0",
            plugin_type=PluginType.verifier,
            description="Checks for potentially unused imports in patch additions",
            tags=["imports", "lint"],
        )

    def run(
        self,
        patch: PatchCandidate,
        repo_path: str = "",
        **kwargs: Any,
    ) -> CheckResult:
        added_lines = [
            line[1:].strip()
            for line in patch.diff.split("\n")
            if line.startswith("+") and not line.startswith("+++")
        ]

        imported_names: list[str] = []
        for line in added_lines:
            if line.startswith("import ") or line.startswith("from "):
                parts = line.split()
                for part in parts:
                    clean = part.strip(",();*")
                    if clean and clean not in ("import", "from", "as"):
                        imported_names.append(clean)

        # Check if imported names appear in other added lines
        all_added_text = " ".join(added_lines)
        unused = [
            name for name in imported_names
            if name not in all_added_text or all_added_text.count(name) <= 1
        ]

        if unused and imported_names:
            return CheckResult(
                check_type="unused_imports",
                command="import-usage-check",
                status=CheckStatus.fail,
                error_message=f"Potentially unused imports: {', '.join(unused)}",
            )

        return CheckResult(
            check_type="unused_imports",
            command="import-usage-check",
            status=CheckStatus.pass_,
        )


class GitLogRetriever(RetrieverPlugin):
    """Retriever plugin that fetches recent git log entries as evidence.

    Provides historical context about recent changes to the repository.
    """

    def __init__(self, max_entries: int = 10) -> None:
        self._max_entries = max_entries

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="git-log-retriever",
            version="0.1.0",
            plugin_type=PluginType.retriever,
            description="Retrieves recent git log entries as historical evidence",
            tags=["git", "history"],
        )

    def run(
        self,
        task: Task,
        repo_path: str = "",
        **kwargs: Any,
    ) -> RetrievalResult:
        evidence: list[RetrievedEvidence] = []

        if not repo_path or not os.path.isdir(repo_path):
            return RetrievalResult(query=task.instruction[:100], evidence=[])

        try:
            import subprocess
            result = subprocess.run(
                ["git", "log", f"--max-count={self._max_entries}", "--oneline", "--format=%H %s"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for i, line in enumerate(result.stdout.strip().split("\n")):
                    if line:
                        parts = line.split(" ", 1)
                        commit = parts[0]
                        message = parts[1] if len(parts) > 1 else ""
                        evidence.append(RetrievedEvidence(
                            kind="git",
                            locator=f"git:{commit[:8]}",
                            content=message,
                            source="git_log",
                            rank=i,
                            metadata={"commit": commit},
                        ))
        except Exception:
            pass

        return RetrievalResult(query=task.instruction[:100], evidence=evidence)


class MinimalityCritic(CriticPlugin):
    """Critic plugin that checks patch minimality.

    Reviews the patch for unnecessary changes, large diffs, or changes
    to files not mentioned in the task.
    """

    def __init__(self, max_files: int = 5, max_diff_lines: int = 200) -> None:
        self._max_files = max_files
        self._max_diff_lines = max_diff_lines

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="minimality-critic",
            version="0.1.0",
            plugin_type=PluginType.critic,
            description="Reviews patches for minimality and unnecessary changes",
            tags=["minimality", "review"],
        )

    def run(
        self,
        patch: PatchCandidate,
        verification_passed: bool = True,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []

        # Check number of changed files
        if len(patch.changed_files) > self._max_files:
            findings.append({
                "severity": "major",
                "category": "overreach",
                "text": (
                    f"Patch modifies {len(patch.changed_files)} files, "
                    f"exceeding recommended max of {self._max_files}"
                ),
            })

        # Check diff size
        diff_lines = len([
            l for l in patch.diff.split("\n")
            if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))
        ])
        if diff_lines > self._max_diff_lines:
            findings.append({
                "severity": "minor",
                "category": "diff_size",
                "text": (
                    f"Diff has {diff_lines} changed lines, "
                    f"consider splitting into smaller patches"
                ),
            })

        # Check for empty diff
        if not patch.diff.strip():
            findings.append({
                "severity": "blocker",
                "category": "empty_patch",
                "text": "Patch diff is empty — no changes proposed",
            })

        return findings


class SecurityCritic(CriticPlugin):
    """Critic plugin that checks for security concerns in patches.

    Looks for common security anti-patterns: hardcoded secrets,
    SQL injection, eval/exec usage, and unsafe deserialization.
    """

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="security-critic",
            version="0.1.0",
            plugin_type=PluginType.critic,
            description="Reviews patches for security anti-patterns",
            tags=["security", "review"],
        )

    def run(
        self,
        patch: PatchCandidate,
        verification_passed: bool = True,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []

        added_lines = [
            line[1:].strip()
            for line in patch.diff.split("\n")
            if line.startswith("+") and not line.startswith("+++")
        ]

        security_patterns = [
            ("eval(", "Use of eval() is dangerous — can execute arbitrary code"),
            ("exec(", "Use of exec() is dangerous — can execute arbitrary code"),
            ("pickle.loads(", "pickle.loads is unsafe — use json or signed deserialization"),
            ("subprocess.call(shell=True", "shell=True with subprocess is vulnerable to injection"),
            ("os.system(", "os.system is vulnerable to injection — use subprocess with shell=False"),
            ("password =", "Hardcoded password detected — use environment variables or secrets"),
            ("api_key =", "Hardcoded API key detected — use environment variables or secrets"),
            ("secret =", "Hardcoded secret detected — use environment variables or secrets"),
        ]

        for line in added_lines:
            for pattern, message in security_patterns:
                if pattern in line.lower():
                    findings.append({
                        "severity": "blocker",
                        "category": "security",
                        "text": message,
                    })

        return findings
