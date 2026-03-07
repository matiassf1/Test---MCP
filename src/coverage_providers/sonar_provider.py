from __future__ import annotations

from typing import Optional

from src.models import CoverageResult, FileChange


class SonarCoverageProvider:
    """Fetches coverage from SonarQube / SonarCloud.

    Requires ``SONAR_TOKEN`` in the environment / .env.
    ``SONAR_URL`` defaults to ``https://sonarcloud.io``.
    ``SONAR_PROJECT_KEY`` defaults to ``{org}_{repo}`` derived from the repo slug.

    If not configured, ``get_coverage`` returns ``None`` silently.
    """

    def __init__(
        self,
        token: str,
        sonar_url: str = "https://sonarcloud.io",
        project_key: Optional[str] = None,
        timeout: int = 15,
    ) -> None:
        self._token = token
        self._sonar_url = sonar_url.rstrip("/")
        self._project_key = project_key
        self._timeout = timeout

    def get_coverage(
        self,
        repo: str,
        head_sha: str,
        file_changes: list[FileChange],
    ) -> Optional[CoverageResult]:
        """Return a CoverageResult from SonarQube/SonarCloud, or None on any failure.

        SonarQube does not provide per-commit coverage — it returns the latest
        analysis for the project.  ``head_sha`` is accepted for API compatibility
        but not used.
        """
        if not self._token:
            return None
        try:
            import requests

            project_key = self._project_key or self._derive_project_key(repo)
            session = requests.Session()
            session.auth = (self._token, "")

            # Overall line coverage
            url = f"{self._sonar_url}/api/measures/component"
            resp = session.get(
                url,
                params={
                    "component": project_key,
                    "metricKeys": "line_coverage,lines_to_cover,uncovered_lines",
                },
                timeout=self._timeout,
            )
            if not resp.ok:
                return None

            measures = {
                m["metric"]: m.get("value")
                for m in resp.json().get("component", {}).get("measures", [])
            }

            overall_pct: Optional[float] = None
            if "line_coverage" in measures and measures["line_coverage"] is not None:
                overall_pct = float(measures["line_coverage"])

            # Without per-file data from Sonar we can only return overall %
            return CoverageResult(
                ran_successfully=True,
                overall_percent=overall_pct,
            ) if overall_pct is not None else None

        except Exception:
            return None

    @staticmethod
    def _derive_project_key(repo: str) -> str:
        """Derive a SonarCloud project key from 'org/repo' → 'org_repo'."""
        return repo.replace("/", "_")
