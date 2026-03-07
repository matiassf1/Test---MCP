from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.models import CoverageResult, FileChange

# Extensions considered JS/TS source (non-test)
_JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def _is_test_file(path: str) -> bool:
    p = path.lower()
    return ".test." in p or ".spec." in p or "/__tests__/" in p or "\\__tests__\\" in p


class JestRunner:
    """Run Jest with --findRelatedTests to get mechanical coverage for PR-changed files.

    Only runs when a local repo checkout is available (``repo_path`` is passed).
    Falls back gracefully to ``None`` on any error.
    """

    def __init__(self, repo_path: str) -> None:
        self._repo_path = Path(repo_path)

    def get_coverage(self, file_changes: list[FileChange]) -> Optional[CoverageResult]:
        """Run Jest against changed files and return coverage, or None on failure."""
        # Collect JS/TS production files (not test files) that were added/modified
        changed_prod = [
            fc.filename
            for fc in file_changes
            if fc.status != "removed"
            and Path(fc.filename).suffix in _JS_EXTENSIONS
            and not _is_test_file(fc.filename)
        ]

        if not changed_prod:
            return None

        # Resolve to absolute paths that exist in the repo
        abs_files = [
            str(self._repo_path / f)
            for f in changed_prod
            if (self._repo_path / f).exists()
        ]

        if not abs_files:
            return None

        coverage_dir = tempfile.mkdtemp(prefix="jest_cov_")
        coverage_json = os.path.join(coverage_dir, "coverage-summary.json")

        cmd = [
            "npx", "jest",
            "--findRelatedTests", *abs_files,
            "--coverage",
            "--coverageReporters", "json-summary",
            f"--coverageDirectory={coverage_dir}",
            "--passWithNoTests",
            "--forceExit",
            "--no-cache",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._repo_path),
                capture_output=True,
                text=True,
                timeout=300,  # 5-minute safety cap
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        # Jest exits non-zero when tests fail; we still want coverage data
        if not os.path.exists(coverage_json):
            return None

        try:
            data = json.loads(Path(coverage_json).read_text(encoding="utf-8"))
        except Exception:
            return None

        return self._build_result(data, file_changes)

    # ------------------------------------------------------------------

    def _build_result(self, data: dict, file_changes: list[FileChange]) -> Optional[CoverageResult]:
        overall_pct: Optional[float] = None
        total_section = data.get("total", {})
        if "lines" in total_section:
            overall_pct = total_section["lines"].get("pct")

        covered = 0
        total = 0

        for fc in file_changes:
            if fc.status == "removed" or fc.additions == 0:
                continue
            if Path(fc.filename).suffix not in _JS_EXTENSIONS:
                continue
            if _is_test_file(fc.filename):
                continue

            normalized = fc.filename.replace("\\", "/")
            for key, file_data in data.items():
                if key == "total":
                    continue
                key_norm = key.replace("\\", "/")
                if key_norm.endswith(normalized) or normalized.endswith(key_norm):
                    pct = file_data.get("lines", {}).get("pct", 0.0) / 100.0
                    file_lines = fc.additions
                    covered += round(file_lines * pct)
                    total += file_lines
                    break

        if total == 0:
            return None

        change_cov = covered / total

        return CoverageResult(
            ran_successfully=True,
            lines_covered=covered,
            lines_modified=total,
            change_coverage=change_cov,
            overall_percent=overall_pct,
            changed_lines=total,
            covered_changed_lines=covered,
            changed_lines_coverage_percent=round(change_cov * 100, 2),
        )
