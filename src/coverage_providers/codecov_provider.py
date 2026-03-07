from __future__ import annotations

from typing import Optional

from src.models import CoverageResult, FileChange


class CodecovCoverageProvider:
    """Fetches coverage from the Codecov API v2.

    Requires ``CODECOV_TOKEN`` in the environment / .env.
    If not configured, ``get_coverage`` returns ``None`` silently.

    Codecov API docs: https://api.codecov.io/api/v2/
    """

    _BASE = "https://api.codecov.io/api/v2"

    def __init__(self, token: str, timeout: int = 15) -> None:
        self._token = token
        self._timeout = timeout

    def get_coverage(
        self,
        repo: str,
        head_sha: str,
        file_changes: list[FileChange],
    ) -> Optional[CoverageResult]:
        """Return a CoverageResult from Codecov, or None on any failure."""
        if not self._token:
            return None
        try:
            import requests

            owner, repo_name = repo.split("/", 1)
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {self._token}"

            # Commit-level summary
            url = f"{self._BASE}/gh/{owner}/repos/{repo_name}/commits/{head_sha}/"
            resp = session.get(url, timeout=self._timeout)
            if not resp.ok:
                return None

            commit_data = resp.json()
            overall_pct: Optional[float] = None
            totals = commit_data.get("totals") or {}
            if "coverage" in totals:
                overall_pct = float(totals["coverage"])

            # Per-file coverage
            files_url = f"{self._BASE}/gh/{owner}/repos/{repo_name}/commits/{head_sha}/files/"
            files_resp = session.get(files_url, timeout=self._timeout)
            if not files_resp.ok:
                # Return overall-only result
                return CoverageResult(
                    ran_successfully=True,
                    overall_percent=overall_pct,
                ) if overall_pct is not None else None

            file_data = {
                f["name"].replace("\\", "/"): f
                for f in files_resp.json().get("results", [])
            }

            covered = 0
            total = 0
            for fc in file_changes:
                if fc.status == "removed" or fc.additions == 0:
                    continue
                normalized = fc.filename.replace("\\", "/")
                for key, fdata in file_data.items():
                    if key.endswith(normalized) or normalized.endswith(key):
                        ftotals = fdata.get("totals") or {}
                        pct = float(ftotals.get("coverage", 0)) / 100.0
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
        except Exception:
            return None
