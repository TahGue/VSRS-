"""Tests for the git index (Phase 2.5)."""

import subprocess
from pathlib import Path

import pytest

from vsrs.repo.git import GitIndex


def _create_git_repo(tmp_path: Path) -> Path:
    """Create a git repo with some commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True)

    (repo / "src.py").write_text("def foo():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, capture_output=True)

    (repo / "src.py").write_text("def foo():\n    return True\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "fix foo return"], cwd=repo, capture_output=True)

    return repo


class TestGitIndex:
    def test_current_commit(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        commit = git.current_commit()
        assert len(commit) == 40  # full SHA

    def test_current_branch(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        branch = git.current_branch()
        assert branch in ("master", "main")

    def test_recent_commits(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        commits = git.recent_commits(10)

        assert len(commits) == 2
        assert commits[0].message == "fix foo return"
        assert commits[1].message == "initial commit"
        assert commits[0].author == "Test User"

    def test_changed_files_in_commit(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        commits = git.recent_commits(1)
        assert "src.py" in commits[0].changed_files

    def test_changed_files_between_commits(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        commits = git.recent_commits(2)
        changed = git.changed_files(commits[1].hash, commits[0].hash)
        assert "src.py" in changed

    def test_file_history(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        history = git.file_history("src.py", count=10)
        assert len(history) == 2

    def test_is_clean(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        assert git.is_clean()

        # Make a change
        (repo / "src.py").write_text("def foo():\n    return False\n")
        assert not git.is_clean()

    def test_diff(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)

        # Make a change
        (repo / "src.py").write_text("def foo():\n    return False\n")
        diff = git.diff()
        assert "src.py" in diff
        assert "return False" in diff

    def test_blame(self, tmp_path):
        repo = _create_git_repo(tmp_path)
        git = GitIndex(repo)
        blame = git.blame("src.py")
        assert len(blame) >= 2
        assert blame[0].line_number == 1
        assert "def foo" in blame[0].content
