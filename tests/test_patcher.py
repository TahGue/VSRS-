"""Tests for the patcher (Phase 3.4-3.5)."""

import subprocess
from pathlib import Path

import pytest

from vsrs.reasoning.patcher import Patcher, ParsedDiff, DiffFile, DiffHunk


SAMPLE_DIFF = """\
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,4 +1,6 @@
 def validate_password(pw: str) -> bool:
-    return bool(pw)
+    if not pw:
+        return False
+    return bool(pw)
 
 def login(username: str, password: str) -> bool:
"""

MULTI_FILE_DIFF = """\
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,3 +1,4 @@
 def validate_password(pw: str) -> bool:
-    return bool(pw)
+    if not pw:
+        return False
+    return bool(pw)
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -1,2 +1,5 @@
 def test_valid_password():
     assert validate_password("secret")
+def test_empty_password():
+    assert not validate_password("")
"""

NEW_FILE_DIFF = '''\
--- /dev/null
+++ b/src/new_module.py
@@ -0,0 +1,3 @@
+def new_function():
+    """A new function."""
+    return True
'''


class TestDiffParsing:
    def test_parse_single_file(self):
        patcher = Patcher()
        parsed = patcher.parse_diff(SAMPLE_DIFF)

        assert len(parsed.files) == 1
        assert parsed.files[0].old_path == "src/auth.py"
        assert parsed.files[0].new_path == "src/auth.py"

    def test_parse_multi_file(self):
        patcher = Patcher()
        parsed = patcher.parse_diff(MULTI_FILE_DIFF)

        assert len(parsed.files) == 2
        assert parsed.files[0].new_path == "src/auth.py"
        assert parsed.files[1].new_path == "tests/test_auth.py"

    def test_parse_new_file(self):
        patcher = Patcher()
        parsed = patcher.parse_diff(NEW_FILE_DIFF)

        assert len(parsed.files) == 1
        assert parsed.files[0].is_new is True
        assert parsed.files[0].old_path == "/dev/null"

    def test_parse_hunk_counts(self):
        patcher = Patcher()
        parsed = patcher.parse_diff(SAMPLE_DIFF)

        file = parsed.files[0]
        assert len(file.hunks) == 1
        hunk = file.hunks[0]
        assert hunk.old_start == 1
        assert len(hunk.added_lines) == 3
        assert len(hunk.removed_lines) == 1

    def test_total_changes(self):
        patcher = Patcher()
        parsed = patcher.parse_diff(SAMPLE_DIFF)

        assert parsed.total_added == 3
        assert parsed.total_removed == 1
        assert parsed.total_changes == 4

    def test_empty_diff(self):
        patcher = Patcher()
        parsed = patcher.parse_diff("")

        assert len(parsed.files) == 0
        assert parsed.total_changes == 0

    def test_changed_files_property(self):
        patcher = Patcher()
        parsed = patcher.parse_diff(MULTI_FILE_DIFF)

        assert "src/auth.py" in parsed.changed_files
        assert "tests/test_auth.py" in parsed.changed_files


class TestDiffValidation:
    def test_valid_diff(self):
        patcher = Patcher()
        result = patcher.validate(SAMPLE_DIFF)

        assert result.valid
        assert len(result.errors) == 0

    def test_empty_diff_valid(self):
        patcher = Patcher()
        result = patcher.validate("")

        assert result.valid
        assert any("Empty diff" in w for w in result.warnings)

    def test_diff_with_no_files(self):
        patcher = Patcher()
        result = patcher.validate("some random text\nnot a diff")

        assert not result.valid

    def test_validation_has_parsed_diff(self):
        patcher = Patcher()
        result = patcher.validate(SAMPLE_DIFF)

        assert result.parsed_diff is not None
        assert len(result.parsed_diff.files) == 1


class TestMinimalityCheck:
    def test_minimal_diff_passes(self):
        patcher = Patcher()
        is_minimal, violations = patcher.minimality_check(SAMPLE_DIFF)

        assert is_minimal
        assert len(violations) == 0

    def test_too_many_files(self):
        patcher = Patcher()
        # Create a diff with many files
        diff_parts = []
        for i in range(10):
            diff_parts.append(f"--- a/file_{i}.py\n+++ b/file_{i}.py\n@@ -1,1 +1,2 @@\n-old\n+new\n+new2\n")
        diff = "\n".join(diff_parts)

        is_minimal, violations = patcher.minimality_check(diff, max_files=5)
        assert not is_minimal
        assert any("files" in v for v in violations)

    def test_too_many_lines(self):
        patcher = Patcher()
        lines_added = "\n".join(f"+line_{i}" for i in range(200))
        diff = f"--- a/big.py\n+++ b/big.py\n@@ -1,1 +1,201 @@\n-old\n{lines_added}\n"

        is_minimal, violations = patcher.minimality_check(diff, max_total_lines=100)
        assert not is_minimal
        assert any("Total" in v for v in violations)

    def test_too_many_lines_per_file(self):
        patcher = Patcher()
        lines_added = "\n".join(f"+line_{i}" for i in range(150))
        diff = f"--- a/big.py\n+++ b/big.py\n@@ -1,1 +1,151 @@\n-old\n{lines_added}\n"

        is_minimal, violations = patcher.minimality_check(diff, max_lines_per_file=100)
        assert not is_minimal
        assert any("big.py" in v for v in violations)


class TestGroundingCheck:
    def test_no_retriever_passes(self):
        patcher = Patcher()
        grounded, ungrounded = patcher.grounding_check(SAMPLE_DIFF)

        assert grounded
        assert len(ungrounded) == 0

    def test_builtins_not_flagged(self):
        patcher = Patcher()

        # Mock retriever that doesn't know any symbols
        class MockRetriever:
            def grounding_check(self, name: str) -> bool:
                return False

        diff = "--- a/f.py\n+++ b/f.py\n@@ -1,1 +1,3 @@\n-old\n+print(len(str(x)))\n+new\n"
        grounded, ungrounded = patcher.grounding_check(diff, retriever=MockRetriever())

        # Builtins should not be flagged
        assert "print" not in ungrounded
        assert "len" not in ungrounded
        assert "str" not in ungrounded


class TestExtractNewImports:
    def test_extract_import(self):
        patcher = Patcher()
        diff = "--- a/f.py\n+++ b/f.py\n@@ -1,1 +1,3 @@\n-old\n+import os\n+from typing import List\n"
        imports = patcher.extract_new_imports(diff)

        assert "os" in imports
        assert "typing" in imports

    def test_no_new_imports(self):
        patcher = Patcher()
        imports = patcher.extract_new_imports(SAMPLE_DIFF)
        assert len(imports) == 0


class TestExtractNewSymbols:
    def test_extract_function(self):
        patcher = Patcher()
        diff = "--- a/f.py\n+++ b/f.py\n@@ -1,1 +1,3 @@\n-old\n+def new_func():\n+    pass\n"
        symbols = patcher.extract_new_symbols(diff)

        assert "new_func" in symbols

    def test_extract_class(self):
        patcher = Patcher()
        diff = "--- a/f.py\n+++ b/f.py\n@@ -1,1 +1,3 @@\n-old\n+class NewClass:\n+    pass\n"
        symbols = patcher.extract_new_symbols(diff)

        assert "NewClass" in symbols

    def test_extract_async_function(self):
        patcher = Patcher()
        diff = "--- a/f.py\n+++ b/f.py\n@@ -1,1 +1,3 @@\n-old\n+async def async_func():\n+    pass\n"
        symbols = patcher.extract_new_symbols(diff)

        assert "async_func" in symbols


class TestApplyDiff:
    def _create_git_repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "auth.py").write_text(
            "def validate_password(pw: str) -> bool:\n"
            "    return bool(pw)\n\n"
            "def login(username: str, password: str) -> bool:\n"
            "    if not validate_password(password):\n"
            "        return False\n"
            "    return True\n"
        )
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)
        return repo

    def test_apply_valid_diff(self, tmp_path):
        repo = self._create_git_repo(tmp_path)
        patcher = Patcher()
        success, error = patcher.apply(SAMPLE_DIFF, repo)

        assert success
        assert error == ""

        # Verify the change was applied
        content = (repo / "src" / "auth.py").read_text()
        assert "if not pw:" in content

    def test_apply_empty_diff(self, tmp_path):
        repo = self._create_git_repo(tmp_path)
        patcher = Patcher()
        success, error = patcher.apply("", repo)

        assert success

    def test_apply_invalid_diff(self, tmp_path):
        repo = self._create_git_repo(tmp_path)
        patcher = Patcher()
        success, error = patcher.apply("not a valid diff", repo)

        assert not success
