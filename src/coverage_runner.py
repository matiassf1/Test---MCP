from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.models import CoverageResult, FileChange


class CoverageRunner:
    """Runs pytest with coverage.py and maps results to modified lines.

    The runner operates on a local clone of the repository.  It executes:

        pytest --cov=<source_dir> --cov-report=json:<output_file>

    and then reads the resulting JSON to determine which of the PR's modified
    lines are actually covered by tests.

    Design principles:
    - Never raises — all errors are captured in ``CoverageResult.error``.
    - Falls back to file-level coverage when line-level mapping is not possible.
    - Exposes ``run_safe()`` as the primary API for callers that don't need
      to distinguish between coverage data and an error state.
    """

    def __init__(self, repo_path: str, source_dir: Optional[str] = None) -> None:
        self.repo_path = Path(repo_path)
        # If not specified, assume source lives at the repo root
        self.source_dir = source_dir or str(self.repo_path)

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def run_safe(
        self,
        file_changes: list[FileChange],
        extra_pytest_args: Optional[list[str]] = None,
    ) -> CoverageResult:
        """Run coverage analysis and return a ``CoverageResult``.

        Never raises — all failures are captured in the returned object.
        """
        try:
            raw = self._run_pytest(extra_pytest_args)
        except Exception as exc:
            return CoverageResult(ran_successfully=False, error=str(exc))

        if not raw:
            return CoverageResult(
                ran_successfully=False,
                error="pytest produced no coverage output",
            )

        overall_pct = self._overall_percent(raw)

        try:
            covered, total = self._compute_line_coverage(raw, file_changes)
            fallback = False
        except Exception:
            covered, total, fallback = self._fallback_file_coverage(raw, file_changes)

        change_cov = (covered / total) if total > 0 else 0.0

        return CoverageResult(
            ran_successfully=True,
            lines_covered=covered,
            lines_modified=total,
            change_coverage=change_cov,
            overall_percent=overall_pct,
            fallback_used=fallback,
        )

    # ------------------------------------------------------------------
    # Lower-level helpers (kept public for callers that need raw data)
    # ------------------------------------------------------------------

    def run(self, extra_pytest_args: Optional[list[str]] = None) -> dict:
        """Execute pytest with coverage and return the raw coverage JSON data.

        Returns an empty dict if coverage output is unavailable.
        """
        try:
            return self._run_pytest(extra_pytest_args)
        except Exception:
            return {}

    def covered_lines_for_file(self, coverage_data: dict, filename: str) -> set[int]:
        """Return the set of line numbers covered for a given file.

        ``filename`` should be relative to the repo root (e.g. ``src/foo.py``).
        The coverage JSON uses absolute paths, so we match by suffix.
        """
        if not coverage_data:
            return set()

        files: dict = coverage_data.get("files", {})
        normalized = filename.replace("\\", "/")

        for abs_path, file_data in files.items():
            abs_normalized = abs_path.replace("\\", "/")
            if abs_normalized.endswith(normalized):
                executed: list[int] = file_data.get("executed_lines", [])
                return set(executed)

        return set()

    def compute_covered_modified_lines(
        self,
        coverage_data: dict,
        file_changes: list[FileChange],
    ) -> tuple[int, int]:
        """Return ``(lines_covered, total_lines_modified)`` for the given changes.

        Only non-removed files are considered.
        """
        return self._compute_line_coverage(coverage_data, file_changes)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_pytest(self, extra_pytest_args: Optional[list[str]]) -> dict:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            coverage_file = tmp.name

        try:
            cmd = [
                "python",
                "-m",
                "pytest",
                f"--cov={self.source_dir}",
                f"--cov-report=json:{coverage_file}",
                "--tb=no",
                "-q",
            ]
            if extra_pytest_args:
                cmd.extend(extra_pytest_args)

            subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,  # pytest returns non-zero when tests fail; we still want coverage
            )

            if not os.path.exists(coverage_file):
                return {}

            with open(coverage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        finally:
            if os.path.exists(coverage_file):
                os.unlink(coverage_file)

    def _compute_line_coverage(
        self, coverage_data: dict, file_changes: list[FileChange]
    ) -> tuple[int, int]:
        total = 0
        covered = 0
        for fc in file_changes:
            if fc.status == "removed":
                continue
            covered_set = self.covered_lines_for_file(coverage_data, fc.filename)
            for line in fc.modified_lines:
                total += 1
                if line in covered_set:
                    covered += 1
        return covered, total

    def _fallback_file_coverage(
        self, coverage_data: dict, file_changes: list[FileChange]
    ) -> tuple[int, int, bool]:
        """Estimate coverage using file-level percent_covered when line mapping fails.

        Returns ``(covered_estimate, total_modified, fallback_used=True)``.
        """
        files: dict = coverage_data.get("files", {})
        total = 0
        covered_estimate = 0

        for fc in file_changes:
            if fc.status == "removed" or not fc.modified_lines:
                continue
            n = len(fc.modified_lines)
            total += n

            # Find the file in coverage data
            normalized = fc.filename.replace("\\", "/")
            for abs_path, file_data in files.items():
                if abs_path.replace("\\", "/").endswith(normalized):
                    pct = file_data.get("summary", {}).get("percent_covered", 0.0)
                    covered_estimate += int(n * pct / 100)
                    break

        return covered_estimate, total, True

    def _overall_percent(self, coverage_data: dict) -> Optional[float]:
        """Extract the repo-wide percent_covered from the coverage JSON totals."""
        try:
            return coverage_data["totals"]["percent_covered"]
        except (KeyError, TypeError):
            return None
