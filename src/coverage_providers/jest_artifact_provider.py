from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.models import CoverageResult, FileChange

_DEFAULT_PATHS = [
    "coverage/coverage-summary.json",
    "coverage-summary.json",
]


class JestArtifactProvider:
    """Loads a local Jest/Istanbul coverage-summary.json and maps it to changed files.

    Used when CI has already run tests and left the coverage report on disk
    (e.g. inside the repo clone or a mounted artifact directory).  Falls back
    gracefully to ``None`` when the file is missing or unparseable.
    """

    def __init__(self, coverage_path: Optional[str] = None) -> None:
        if coverage_path:
            self._candidates = [Path(coverage_path)]
        else:
            self._candidates = [Path(p) for p in _DEFAULT_PATHS]

    def get_coverage(self, file_changes: list[FileChange]) -> Optional[CoverageResult]:
        """Return CoverageResult from the local coverage-summary.json, or None."""
        data = self._load()
        if data is None:
            return None
        try:
            return self._build_result(data, file_changes)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> Optional[dict]:
        for path in self._candidates:
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    return None
        return None

    def _build_result(self, data: dict, file_changes: list[FileChange]) -> CoverageResult:
        """Parse coverage-summary.json into a CoverageResult.

        Expected format::

            {
                "total": {"lines": {"total": 100, "covered": 85, "pct": 85}},
                "src/foo.ts": {"lines": {"total": 10, "covered": 8, "pct": 80}}
            }
        """
        overall_pct: Optional[float] = None
        total_section = data.get("total", {})
        if "lines" in total_section:
            overall_pct = total_section["lines"].get("pct")

        covered = 0
        total = 0

        for fc in file_changes:
            if fc.status == "removed" or fc.additions == 0:
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

        change_cov = (covered / total) if total > 0 else 0.0

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
