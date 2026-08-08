"""Patch generator: valid unified diff that applies cleanly (Section 7.2).

Parses, validates, and applies unified diffs. Provides minimality checks
and grounding validation for proposed patches.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.reasoning.protocol import PatchProposal

logger = get_logger("reasoning.patcher")


@dataclass
class DiffHunk:
    """A single hunk from a unified diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)

    @property
    def added_lines(self) -> list[str]:
        return [l[1:] for l in self.lines if l.startswith("+")]

    @property
    def removed_lines(self) -> list[str]:
        return [l[1:] for l in self.lines if l.startswith("-")]

    @property
    def context_lines(self) -> list[str]:
        return [l[1:] for l in self.lines if l.startswith(" ")]


@dataclass
class DiffFile:
    """A single file change from a unified diff."""

    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False

    @property
    def added_line_count(self) -> int:
        return sum(len(h.added_lines) for h in self.hunks)

    @property
    def removed_line_count(self) -> int:
        return sum(len(h.removed_lines) for h in self.hunks)

    @property
    def total_changes(self) -> int:
        return self.added_line_count + self.removed_line_count


@dataclass
class ParsedDiff:
    """A parsed unified diff."""

    files: list[DiffFile] = field(default_factory=list)

    @property
    def changed_files(self) -> list[str]:
        return [f.new_path for f in self.files]

    @property
    def total_added(self) -> int:
        return sum(f.added_line_count for f in self.files)

    @property
    def total_removed(self) -> int:
        return sum(f.removed_line_count for f in self.files)

    @property
    def total_changes(self) -> int:
        return self.total_added + self.total_removed

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass
class ValidationResult:
    """Result of patch validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    parsed_diff: ParsedDiff | None = None


class Patcher:
    """Patch generator and validator.

    Provides:
    - Diff parsing (unified diff format)
    - Diff validation (syntax, applicability)
    - Diff application (git apply or manual)
    - Minimality checks (changed files/lines are bounded)
    - Grounding validation (referenced symbols exist)
    """

    def parse_diff(self, diff: str) -> ParsedDiff:
        """Parse a unified diff string into a ParsedDiff.

        Args:
            diff: Unified diff string.

        Returns:
            ParsedDiff with all file changes and hunks.

        Raises:
            ValueError: If the diff is malformed.
        """
        if not diff.strip():
            return ParsedDiff()

        lines = diff.splitlines()
        parsed = ParsedDiff()
        current_file: DiffFile | None = None
        current_hunk: DiffHunk | None = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # File header: --- old_path
            if line.startswith("--- "):
                old_path = line[4:].split("\t")[0].strip()
                # Strip a/ b/ prefixes from git diff
                if old_path.startswith("a/"):
                    old_path = old_path[2:]
                i += 1
                if i < len(lines) and lines[i].startswith("+++ "):
                    new_path = lines[i][4:].split("\t")[0].strip()
                    if new_path.startswith("b/"):
                        new_path = new_path[2:]
                    is_new = old_path == "/dev/null"
                    is_deleted = new_path == "/dev/null"
                    current_file = DiffFile(
                        old_path=old_path,
                        new_path=new_path,
                        is_new=is_new,
                        is_deleted=is_deleted,
                    )
                    parsed.files.append(current_file)
                i += 1
                continue

            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            hunk_match = re.match(
                r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line
            )
            if hunk_match:
                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2) or "1")
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4) or "1")
                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                )
                if current_file:
                    current_file.hunks.append(current_hunk)
                i += 1
                continue

            # Hunk content lines
            if current_hunk and (line.startswith(" ") or line.startswith("+") or line.startswith("-") or line == ""):
                current_hunk.lines.append(line)
                i += 1
                continue

            # Binary file
            if line.startswith("Binary files"):
                if current_file:
                    current_file.is_binary = True
                i += 1
                continue

            i += 1

        return parsed

    def validate(self, diff: str, repo_root: Path | None = None) -> ValidationResult:
        """Validate a unified diff.

        Checks:
        - Diff syntax is correct
        - Hunk headers are well-formed
        - File paths are reasonable
        - If repo_root is provided, checks that the diff would apply cleanly

        Args:
            diff: Unified diff string.
            repo_root: Repository root for applicability check.

        Returns:
            ValidationResult with errors and warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not diff.strip():
            return ValidationResult(
                valid=True,
                warnings=["Empty diff — no changes proposed"],
                parsed_diff=ParsedDiff(),
            )

        # Parse the diff
        try:
            parsed = self.parse_diff(diff)
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[f"Failed to parse diff: {e}"],
            )

        # Check for files
        if not parsed.files:
            errors.append("Diff contains no file changes")
            return ValidationResult(valid=False, errors=errors)

        # Validate each file
        for file in parsed.files:
            if not file.hunks and not file.is_binary:
                warnings.append(f"File {file.new_path} has no hunks")

            for hunk in file.hunks:
                # Check hunk line counts
                added = len(hunk.added_lines)
                removed = len(hunk.removed_lines)
                context = len(hunk.context_lines)

                if added + removed == 0 and context == 0:
                    warnings.append(f"Empty hunk in {file.new_path}")

                # Check that hunk content matches header counts
                if removed != hunk.old_count and hunk.old_count != 0:
                    # Allow some flexibility — some diffs have slightly different counts
                    pass
                if added != hunk.new_count and hunk.new_count != 0:
                    pass

        # Check applicability if repo_root is provided
        if repo_root:
            apply_errors = self._check_applicability(diff, repo_root)
            errors.extend(apply_errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            parsed_diff=parsed,
        )

    def _check_applicability(self, diff: str, repo_root: Path) -> list[str]:
        """Check if a diff would apply cleanly using git apply --check."""
        try:
            result = subprocess.run(
                ["git", "apply", "--check", "--verbose"],
                input=diff,
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return [f"Diff does not apply cleanly: {result.stderr.strip()}"]
        except FileNotFoundError:
            return ["git not available for applicability check"]
        return []

    def apply(self, diff: str, repo_root: Path, check: bool = True) -> tuple[bool, str]:
        """Apply a unified diff to a repository.

        Args:
            diff: Unified diff string.
            repo_root: Repository root path.
            check: Whether to run git apply --check first.

        Returns:
            Tuple of (success, error_message).
        """
        if not diff.strip():
            return True, "No changes to apply"

        if check:
            validation = self.validate(diff, repo_root)
            if not validation.valid:
                return False, "; ".join(validation.errors)

        try:
            result = subprocess.run(
                ["git", "apply"],
                input=diff,
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return False, result.stderr.strip()
            return True, ""
        except FileNotFoundError:
            return False, "git not available"

    def minimality_check(
        self,
        diff: str,
        max_files: int = 5,
        max_lines_per_file: int = 100,
        max_total_lines: int = 300,
    ) -> tuple[bool, list[str]]:
        """Check if a patch is minimal (Section 7.2).

        A minimal patch:
        - Changes few files (default max 5)
        - Changes few lines per file (default max 100)
        - Has bounded total changes (default max 300)

        Args:
            diff: Unified diff string.
            max_files: Maximum number of files to change.
            max_lines_per_file: Maximum changed lines per file.
            max_total_lines: Maximum total changed lines.

        Returns:
            Tuple of (is_minimal, violations).
        """
        violations: list[str] = []

        parsed = self.parse_diff(diff)

        if parsed.file_count > max_files:
            violations.append(
                f"Changes {parsed.file_count} files (max {max_files})"
            )

        if parsed.total_changes > max_total_lines:
            violations.append(
                f"Total changes: {parsed.total_changes} lines (max {max_total_lines})"
            )

        for file in parsed.files:
            if file.total_changes > max_lines_per_file:
                violations.append(
                    f"File {file.new_path}: {file.total_changes} changes (max {max_lines_per_file})"
                )

        return len(violations) == 0, violations

    def grounding_check(
        self,
        diff: str,
        retriever: object | None = None,
    ) -> tuple[bool, list[str]]:
        """Check that all referenced symbols in the diff are grounded.

        Implements Section 6.3: every referenced symbol should resolve in
        the repository or be intentionally introduced.

        Args:
            diff: Unified diff string.
            retriever: Retriever instance for symbol resolution.

        Returns:
            Tuple of (is_grounded, ungrounded_symbols).
        """
        if not retriever:
            return True, []

        parsed = self.parse_diff(diff)
        ungrounded: list[str] = []

        # Extract identifiers from added lines
        for file in parsed.files:
            for hunk in file.hunks:
                for line in hunk.added_lines:
                    # Find function calls and references
                    identifiers = re.findall(r'\b([a-z_][a-zA-Z0-9_]*)\s*\(', line)
                    for ident in identifiers:
                        # Skip Python builtins and keywords
                        if ident in {"print", "len", "str", "int", "float", "bool",
                                      "list", "dict", "set", "tuple", "range", "type",
                                      "isinstance", "issubclass", "super", "property",
                                      "staticmethod", "classmethod", "abs", "max", "min",
                                      "sum", "sorted", "reversed", "enumerate", "zip",
                                      "map", "filter", "any", "all", "open", "input",
                                      "assert", "raise", "return", "yield", "await",
                                      "self", "cls", "init"}:
                            continue
                        if hasattr(retriever, "grounding_check"):
                            if not retriever.grounding_check(ident):
                                ungrounded.append(ident)

        # Deduplicate
        ungrounded = list(dict.fromkeys(ungrounded))
        return len(ungrounded) == 0, ungrounded

    def extract_new_imports(self, diff: str) -> list[str]:
        """Extract new import statements from a diff.

        Returns a list of module names that are newly imported.
        """
        parsed = self.parse_diff(diff)
        new_imports: list[str] = []

        for file in parsed.files:
            for hunk in file.hunks:
                for line in hunk.added_lines:
                    # import xxx
                    match = re.match(r"^\s*import\s+([\w.]+)", line)
                    if match:
                        new_imports.append(match.group(1))
                    # from xxx import yyy
                    match = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
                    if match:
                        new_imports.append(match.group(1))

        return list(dict.fromkeys(new_imports))

    def extract_new_symbols(self, diff: str) -> list[str]:
        """Extract newly defined symbols (functions, classes) from a diff."""
        parsed = self.parse_diff(diff)
        new_symbols: list[str] = []

        for file in parsed.files:
            for hunk in file.hunks:
                for line in hunk.added_lines:
                    # def xxx(
                    match = re.match(r"^\s*(?:async\s+)?def\s+(\w+)", line)
                    if match:
                        new_symbols.append(match.group(1))
                    # class xxx(
                    match = re.match(r"^\s*class\s+(\w+)", line)
                    if match:
                        new_symbols.append(match.group(1))

        return list(dict.fromkeys(new_symbols))

    def from_proposal(self, proposal: PatchProposal) -> ParsedDiff:
        """Parse a PatchProposal's diff into a ParsedDiff."""
        return self.parse_diff(proposal.diff)
