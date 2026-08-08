"""Git index: recent commits, blame, changed files (Section 6.1).

Provides git history context for repository intelligence: recent commits,
blame information, and changed file tracking.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger

logger = get_logger("repo.git")


@dataclass
class CommitInfo:
    """Information about a single git commit."""

    hash: str
    author: str
    date: str
    message: str
    changed_files: list[str] = field(default_factory=list)


@dataclass
class BlameLine:
    """A single line of git blame output."""

    commit_hash: str
    author: str
    date: str
    line_number: int
    content: str


class GitIndex:
    """Index of git history for a repository.

    Provides:
    - Recent commit history
    - Blame information for specific files
    - Changed file tracking between commits
    - Current branch and status
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def _run_git(self, args: list[str]) -> tuple[int, str, str]:
        """Run a git command and return (exit_code, stdout, stderr)."""
        result = subprocess.run(
            ["git"] + args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def current_commit(self) -> str:
        """Get the current HEAD commit hash."""
        code, stdout, _ = self._run_git(["rev-parse", "HEAD"])
        if code != 0:
            return ""
        return stdout.strip()

    def current_branch(self) -> str:
        """Get the current branch name."""
        code, stdout, _ = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if code != 0:
            return ""
        return stdout.strip()

    def recent_commits(self, count: int = 20) -> list[CommitInfo]:
        """Get recent commits.

        Args:
            count: Number of commits to retrieve.

        Returns:
            List of commit info, most recent first.
        """
        # Get commit hashes
        code, stdout, _ = self._run_git(["log", f"-{count}", "--format=%H"])
        if code != 0:
            return []

        hashes = stdout.strip().splitlines()
        commits: list[CommitInfo] = []

        for h in hashes:
            commit = self._get_commit_info(h)
            if commit:
                commits.append(commit)

        return commits

    def _get_commit_info(self, commit_hash: str) -> CommitInfo | None:
        """Get detailed info for a single commit."""
        # Get metadata
        code, stdout, _ = self._run_git([
            "show", "-s", "--format=%H%n%an%n%ad%n%s", commit_hash
        ])
        if code != 0:
            return None

        lines = stdout.strip().split("\n", 3)
        if len(lines) < 4:
            return None

        # Get changed files
        code, files_stdout, _ = self._run_git([
            "show", "--name-only", "--format=", commit_hash
        ])
        changed_files = [f for f in files_stdout.strip().splitlines() if f]

        return CommitInfo(
            hash=lines[0],
            author=lines[1],
            date=lines[2],
            message=lines[3],
            changed_files=changed_files,
        )

    def blame(self, file_path: str) -> list[BlameLine]:
        """Get blame information for a file.

        Args:
            file_path: Relative path to the file.

        Returns:
            List of blame lines.
        """
        # Use porcelain format for easier parsing
        code, stdout, _ = self._run_git([
            "blame", "--porcelain", file_path
        ])
        if code != 0:
            return []

        lines: list[BlameLine] = []
        current_hash = ""
        current_author = ""
        current_date = ""

        for line in stdout.splitlines():
            if line.startswith("\t"):
                # Content line
                content = line[1:]
                lines.append(BlameLine(
                    commit_hash=current_hash,
                    author=current_author,
                    date=current_date,
                    line_number=len(lines) + 1,
                    content=content,
                ))
            elif " " in line:
                parts = line.split(" ", 1)
                current_hash = parts[0]
            elif line.startswith("author "):
                current_author = line[7:]
            elif line.startswith("author-time "):
                current_date = line[12:]

        return lines

    def changed_files(self, base_commit: str, target_commit: str = "HEAD") -> list[str]:
        """Get files changed between two commits.

        Args:
            base_commit: Base commit hash.
            target_commit: Target commit hash (defaults to HEAD).

        Returns:
            List of relative file paths that changed.
        """
        code, stdout, _ = self._run_git([
            "diff", "--name-only", base_commit, target_commit
        ])
        if code != 0:
            return []
        return [f for f in stdout.strip().splitlines() if f]

    def file_history(self, file_path: str, count: int = 10) -> list[CommitInfo]:
        """Get commit history for a specific file.

        Args:
            file_path: Relative path to the file.
            count: Number of commits to retrieve.

        Returns:
            List of commits that touched this file.
        """
        code, stdout, _ = self._run_git([
            "log", f"-{count}", "--format=%H", "--", file_path
        ])
        if code != 0:
            return []

        hashes = stdout.strip().splitlines()
        commits: list[CommitInfo] = []
        for h in hashes:
            commit = self._get_commit_info(h)
            if commit:
                commits.append(commit)
        return commits

    def is_clean(self) -> bool:
        """Check if the working directory is clean (no uncommitted changes)."""
        code, stdout, _ = self._run_git(["status", "--porcelain"])
        if code != 0:
            return False
        return stdout.strip() == ""

    def diff(self, base_commit: str = "HEAD") -> str:
        """Get the current uncommitted diff.

        Args:
            base_commit: Base commit to diff against (defaults to HEAD).

        Returns:
            Unified diff string.
        """
        code, stdout, _ = self._run_git(["diff", base_commit])
        return stdout if code == 0 else ""

    def remote_url(self) -> str:
        """Get the remote URL of the repository."""
        code, stdout, _ = self._run_git(["remote", "get-url", "origin"])
        if code != 0:
            return ""
        return stdout.strip()
