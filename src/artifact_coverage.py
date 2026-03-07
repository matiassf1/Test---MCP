from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Optional

import requests

from src.models import CoverageResult, FileChange


# ---------------------------------------------------------------------------
# Coverage artifact / file name heuristics
# ---------------------------------------------------------------------------

# Artifact names that suggest coverage data (case-insensitive substring match)
_COVERAGE_ARTIFACT_NAMES = [
    "coverage",
    "code-coverage",
    "test-coverage",
    "jest-coverage",
    "coverage-report",
]

# Files inside the zip to look for, in priority order
_COVERAGE_FILE_CANDIDATES = [
    "coverage-summary.json",
    "coverage/coverage-summary.json",
    "coverage-final.json",
    "coverage/coverage-final.json",
    "coverage.json",
]


class ArtifactCoverageService:
    """Fetches coverage data from GitHub Actions artifacts for a PR commit.

    Supports Jest/Istanbul ``coverage-summary.json`` format (the most common
    format for TypeScript/JavaScript projects).  Falls back gracefully to
    ``None`` on any error so the pipeline always continues.

    Requires a GitHub token with ``repo`` / ``actions:read`` scope — the same
    token already used by ``GitHubService``.
    """

    def __init__(self, token: str, timeout: int = 20) -> None:
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def get_coverage(
        self,
        repo: str,
        head_sha: str,
        file_changes: list[FileChange],
    ) -> Optional[CoverageResult]:
        """Return a ``CoverageResult`` from GitHub Actions artifacts, or ``None``.

        Searches all completed workflow runs for ``head_sha``, then inspects
        their artifacts for a coverage report.  Returns the first one found.
        """
        try:
            runs = self._get_workflow_runs(repo, head_sha)
            for run in runs:
                artifacts = self._get_artifacts(repo, run["id"])
                for artifact in artifacts:
                    if not self._is_coverage_artifact(artifact["name"]):
                        continue
                    data = self._download_and_parse(repo, artifact["id"])
                    if data:
                        return self._build_result(data, file_changes)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # GitHub API helpers
    # ------------------------------------------------------------------

    def _get_workflow_runs(self, repo: str, head_sha: str) -> list[dict]:
        url = f"https://api.github.com/repos/{repo}/actions/runs"
        resp = self._session.get(
            url,
            params={"head_sha": head_sha, "status": "completed"},
            timeout=self._timeout,
        )
        if not resp.ok:
            return []
        return resp.json().get("workflow_runs", [])

    def _get_artifacts(self, repo: str, run_id: int) -> list[dict]:
        url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts"
        resp = self._session.get(url, timeout=self._timeout)
        if not resp.ok:
            return []
        return resp.json().get("artifacts", [])

    def _download_and_parse(self, repo: str, artifact_id: int) -> Optional[dict]:
        """Download the artifact zip and return the parsed coverage JSON, or None."""
        url = f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip"
        resp = self._session.get(url, timeout=self._timeout, allow_redirects=True)
        if not resp.ok:
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                names = zf.namelist()

                # Try known filenames first
                for candidate in _COVERAGE_FILE_CANDIDATES:
                    if candidate in names:
                        return json.loads(zf.read(candidate).decode("utf-8"))

                # Fallback: any file whose name contains "coverage-summary"
                for name in names:
                    if "coverage-summary" in name.lower() and name.endswith(".json"):
                        return json.loads(zf.read(name).decode("utf-8"))
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Option B: Check Runs
    # ------------------------------------------------------------------

    def get_coverage_from_check_runs(
        self,
        repo: str,
        head_sha: str,
    ) -> Optional[CoverageResult]:
        """Scan GitHub Check Runs for a coverage percentage posted by CI.

        Many tools (Codecov, custom Jest reporters, lcov-reporter-action, etc.)
        post the overall coverage % as part of a check run's output title or
        summary.  We extract the first percentage that looks like coverage and
        return it as ``overall_percent``.

        Because check runs only give us a repo-wide number (not per-file line
        data), ``change_coverage`` is not set here — callers should treat this
        as a best-effort overall signal only.
        """
        try:
            check_runs = self._get_check_runs(repo, head_sha)
            for cr in check_runs:
                pct = self._extract_coverage_pct(cr)
                if pct is not None:
                    return CoverageResult(
                        ran_successfully=True,
                        overall_percent=pct,
                        # change_coverage stays 0 — we only have repo-wide data
                    )
        except Exception:
            pass
        return None

    def _get_check_runs(self, repo: str, head_sha: str) -> list[dict]:
        url = f"https://api.github.com/repos/{repo}/commits/{head_sha}/check-runs"
        results: list[dict] = []
        params: dict = {"per_page": 100}
        while True:
            resp = self._session.get(url, params=params, timeout=self._timeout)
            if not resp.ok:
                break
            data = resp.json()
            results.extend(data.get("check_runs", []))
            # follow pagination
            next_url = resp.links.get("next", {}).get("url")
            if not next_url:
                break
            url = next_url
            params = {}
        return results

    def _extract_coverage_pct(self, check_run: dict) -> Optional[float]:
        """Return the first coverage percentage found in this check run, or None."""
        name = (check_run.get("name") or "").lower()
        output = check_run.get("output") or {}
        title = (output.get("title") or "").lower()
        summary = output.get("summary") or ""
        text = output.get("text") or ""

        # Only consider check runs whose name/title suggests coverage
        coverage_keywords = ("coverage", "codecov", "lcov", "jest", "istanbul", "nyc")
        relevant = any(kw in name or kw in title for kw in coverage_keywords)
        if not relevant:
            return None

        # Patterns to match:  "78.5%", "78.5% coverage", "coverage: 78.5"
        _PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")

        for blob in (title, summary, text):
            match = _PCT_RE.search(blob)
            if match:
                pct = float(match.group(1))
                if 0.0 <= pct <= 100.0:
                    return pct
        return None

    def _is_coverage_artifact(self, name: str) -> bool:
        lower = name.lower()
        return any(pattern in lower for pattern in _COVERAGE_ARTIFACT_NAMES)

    def _build_result(
        self, data: dict, file_changes: list[FileChange]
    ) -> CoverageResult:
        """Parse a Jest/Istanbul coverage-summary.json into a CoverageResult.

        Format expected::

            {
                "total": {"lines": {"pct": 78.5}, ...},
                "src/foo.ts": {"lines": {"total": 50, "covered": 40, "pct": 80}, ...},
                ...
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

            # Match the file against keys in coverage data (suffix match)
            normalized = fc.filename.replace("\\", "/")
            for key, file_data in data.items():
                if key == "total":
                    continue
                key_normalized = key.replace("\\", "/")
                if key_normalized.endswith(normalized) or normalized.endswith(
                    key_normalized
                ):
                    file_lines = fc.additions
                    pct = file_data.get("lines", {}).get("pct", 0.0) / 100.0
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
