from __future__ import annotations

import re
from typing import Optional

from src.models import FileChange

_KEYWORDS = frozenset({
    "if", "else", "for", "while", "return", "import", "from", "const", "let",
    "var", "async", "await", "export", "default", "new", "try", "catch",
    "throw", "this", "super", "extends", "type", "interface", "enum", "def",
    "self", "pass", "raise", "with", "yield", "function", "public", "private",
    "protected", "static", "readonly", "abstract", "constructor", "switch",
    "case", "break", "continue", "true", "false", "null", "undefined", "void",
    "class", "get", "set", "None", "True", "False", "and", "or", "not", "in",
})

# Extracts names of defined functions, classes, and arrow-function variables
_DEF_RE = re.compile(
    r"(?:function|def)\s+(\w+)"                              # function/def name
    r"|class\s+(\w+)"                                        # class Name
    r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("    # arrow function
    r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function"  # function expr
)


class ChangeAnalyzer:
    """Analyzes the set of file changes in a PR to compute line-level metrics."""

    # Extensions that are not source code — excluded from coverage analysis
    _EXCLUDED_EXTENSIONS = {
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".md",
        ".txt",
        ".lock",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
        ".ico",
        ".gif",
        ".woff",
        ".woff2",
    }

    # Path segments that indicate auto-generated code — excluded from all metrics.
    # Matched as substrings of the normalized (forward-slash) file path.
    _GENERATED_PATH_SEGMENTS = {
        "/generated/",
        "/__generated__/",
        "/gen/",
        "/.generated/",
    }

    # File suffixes that indicate a single auto-generated file (e.g. foo.generated.ts)
    _GENERATED_FILE_SUFFIXES = (
        ".generated.ts",
        ".generated.js",
        ".generated.py",
        ".g.ts",
        ".g.js",
        ".pb.ts",
        ".pb.js",
        ".pb.go",
        "_pb2.py",
    )

    def filter_source_changes(self, file_changes: list[FileChange]) -> list[FileChange]:
        """Return all source-code files (excludes configs, docs, assets, removed files, generated files)."""
        result: list[FileChange] = []
        for fc in file_changes:
            ext = self._get_extension(fc.filename)
            if (
                ext not in self._EXCLUDED_EXTENSIONS
                and fc.status != "removed"
                and not self._is_generated(fc.filename)
            ):
                result.append(fc)
        return result

    def filter_production_changes(self, file_changes: list[FileChange]) -> list[FileChange]:
        """Return source files that are NOT test files.

        Used to compute production-code line counts separately from test lines.
        """
        source = self.filter_source_changes(file_changes)
        return [fc for fc in source if not self._is_test_file(fc.filename)]

    def filter_test_changes(self, file_changes: list[FileChange]) -> list[FileChange]:
        """Return source files that ARE test files."""
        source = self.filter_source_changes(file_changes)
        return [fc for fc in source if self._is_test_file(fc.filename)]

    def total_modified_lines(self, file_changes: list[FileChange]) -> int:
        """Count total added/changed lines across all provided FileChanges."""
        return sum(len(fc.modified_lines) for fc in file_changes)

    def total_added_lines(self, file_changes: list[FileChange]) -> int:
        """Count lines that were purely added (status == 'added' files or additions field)."""
        return sum(fc.additions for fc in file_changes if fc.status != "removed")

    def estimate_diff_coverage(
        self,
        production_changes: list[FileChange],
        test_changes: list[FileChange],
    ) -> Optional[float]:
        """Estimate what % of newly defined production names are covered by tests.

        Requires two conditions to count a name as covered (reduces false positives):
        1. The production module filename appears in an import/require statement in tests.
        2. The function/class name appears within a test block context
           (within 400 chars of describe(/it(/test(/expect()).

        Returns 0.0–1.0, or None if no identifiable names were found.
        """
        # Collect names from both newly added code AND modified existing code
        defined = (
            self._extract_defined_names(production_changes)
            | self._extract_modified_context_names(production_changes)
        )
        if not defined:
            return None

        test_content = " ".join(fc.patch for fc in test_changes if fc.patch)
        if not test_content:
            return 0.0

        # Check whether ANY production module is imported in tests
        module_imported = any(
            self._module_is_imported(fc.filename, test_content)
            for fc in production_changes
            if fc.patch
        )

        covered = sum(
            1 for name in defined
            if self._name_in_test_block(name, test_content, require_import=module_imported)
        )
        return covered / len(defined)

    def _module_is_imported(self, filename: str, test_content: str) -> bool:
        """True if the production file's basename appears in an import/require line."""
        import os
        stem = os.path.splitext(os.path.basename(filename))[0].lower()
        for line in test_content.splitlines():
            lower = line.lower()
            if ("import" in lower or "require" in lower) and stem in lower:
                return True
        return False

    def _name_in_test_block(
        self, name: str, test_content: str, require_import: bool
    ) -> bool:
        """True if name appears near a test block indicator in the test content.

        If require_import is False (module not found in imports) we still allow
        the match but require a stricter assertion proximity (expect/assert/toBe).
        """
        if name not in test_content:
            return False

        indicators = ("describe(", "it(", "test(", "expect(", "assert", "toBe(", "toEqual(", "toHaveBeenCalled")
        strict_indicators = ("expect(", "assert", "toBe(", "toEqual(", "toHaveBeenCalled")
        check = indicators if require_import else strict_indicators

        pos = 0
        while True:
            idx = test_content.find(name, pos)
            if idx == -1:
                break
            window = test_content[max(0, idx - 400): idx + 400]
            if any(ind in window for ind in check):
                return True
            pos = idx + 1
        return False

    def _extract_defined_names(self, file_changes: list[FileChange]) -> set[str]:
        """Extract function/class/variable names from added lines (+) in patch diffs."""
        names: set[str] = set()
        for fc in file_changes:
            if not fc.patch:
                continue
            for line in fc.patch.splitlines():
                if not line.startswith("+") or line.startswith("+++"):
                    continue
                for m in _DEF_RE.finditer(line[1:]):  # strip leading '+'
                    name = next((g for g in m.groups() if g), None)
                    if name and len(name) >= 3 and name not in _KEYWORDS:
                        names.add(name)
        return names

    def compute_test_file_pairing(
        self,
        production_changes: list[FileChange],
        test_changes: list[FileChange],
    ) -> float:
        """Return the fraction of production files that have a matching test file in the PR.

        A production file is 'paired' when any test file's basename contains the
        production file's stem, e.g. auth.ts → auth.test.ts / test_auth.py.
        Returns 1.0 when there are no production files (config-only PR).
        """
        import os

        if not production_changes:
            return 1.0

        test_basenames = [os.path.basename(tc.filename).lower() for tc in test_changes]

        paired = sum(
            1 for fc in production_changes
            if any(
                os.path.splitext(os.path.basename(fc.filename))[0].lower() in tb
                for tb in test_basenames
            )
        )
        return paired / len(production_changes)

    def count_test_assertions(self, test_changes: list[FileChange]) -> int:
        """Count lines containing assertion keywords in added test diff lines."""
        _KEYWORDS = (
            "expect(", "assert", "tobe(", "toequal(", "tohavebeencalled",
            "tocontain(", "tomatch(", "tothrow(", "should.", "assertraises(",
            "assertequal(", "asserttrue(", "assertfalse(", "assertin(",
            "verify(", "sinon.", "spy.", "stub.",
        )
        count = 0
        for fc in test_changes:
            if not fc.patch:
                continue
            for line in fc.patch.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    lower = line.lower()
                    if any(kw in lower for kw in _KEYWORDS):
                        count += 1
        return count

    def group_by_file(self, file_changes: list[FileChange]) -> dict[str, FileChange]:
        """Return a mapping of filename -> FileChange for quick lookup."""
        return {fc.filename: fc for fc in file_changes}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_extension(self, filename: str) -> str:
        dot_index = filename.rfind(".")
        if dot_index == -1:
            return ""
        return filename[dot_index:].lower()

    def _is_generated(self, filename: str) -> bool:
        """Return True if the file is auto-generated and should be excluded from metrics."""
        normalized = filename.replace("\\", "/").lower()
        if any(seg in normalized for seg in self._GENERATED_PATH_SEGMENTS):
            return True
        return any(normalized.endswith(suffix) for suffix in self._GENERATED_FILE_SUFFIXES)

    def _is_test_file(self, filename: str) -> bool:
        import os

        basename = os.path.basename(filename).lower()
        normalized = filename.replace("\\", "/").lower()
        return (
            # Python conventions
            basename.startswith("test_")
            or basename.endswith("_test.py")
            # JS/TS conventions: foo.test.ts, foo.spec.ts, foo.test.js, foo.spec.js
            or ".test." in basename
            or ".spec." in basename
            # Directory-based (any language)
            or "/tests/" in normalized
            or "/test/" in normalized
            or "/__tests__/" in normalized
        )

    def _extract_modified_context_names(self, file_changes: list[FileChange]) -> set[str]:
        """Extract function/class names from context lines that surround modified lines.

        When you modify lines inside an existing function, the function definition
        line itself is a context line (no + prefix) and is invisible to
        _extract_defined_names.  This method scans backward from each + line
        looking for the enclosing function/class definition in context, up to 30
        lines back or until a hunk header (@@) is reached.

        Example — modifying lines inside an existing function:
            @@ -10,7 +10,7 @@
             def process_items(items):   ← context line, detected here
            -    return [x for x in items]
            +    return [x for x in items if x.active]
        """
        names: set[str] = set()
        for fc in file_changes:
            if not fc.patch:
                continue
            lines = fc.patch.splitlines()
            for i, line in enumerate(lines):
                if not line.startswith("+") or line.startswith("+++"):
                    continue
                # Scan backward for a context-line function/class definition
                for j in range(i - 1, max(i - 30, -1), -1):
                    ctx = lines[j]
                    if ctx.startswith("@@"):
                        break  # hit hunk header
                    if ctx.startswith("+") or ctx.startswith("-"):
                        continue  # skip diff lines, only look at context
                    for m in _DEF_RE.finditer(ctx):
                        name = next((g for g in m.groups() if g), None)
                        if name and len(name) >= 3 and name not in _KEYWORDS:
                            names.add(name)
        return names
