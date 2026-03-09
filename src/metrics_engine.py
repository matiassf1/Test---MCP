from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.models import (
    AuthorStats,
    CoverageResult,
    FileChange,
    JiraIssue,
    PRMetrics,
    TeamSummary,
    TestFile,
    TestType,
    TestTypeCount,
)
from src.storage import JSONStorage, StorageBackend


def _compute_testing_quality_score(
    change_coverage: float,              # 0.0–1.0 (real CI; 0.0 means unavailable)
    test_lines_added: int,
    production_lines_added: int,
    diff_estimated_coverage: Optional[float] = None,
    test_file_pairing_rate: float = 0.0, # fraction of prod files with a test counterpart
    llm_estimated_coverage: Optional[float] = None,
) -> float:
    """Compute a 0–10 composite testing quality score.

    We prefer AI/LLM estimates over mechanical (CI) coverage when both exist.
    Branches by data availability:

    A) LLM-inferred coverage (when available) — primary source:
         coverage_llm * 0.85 * 0.45 + ratio * 0.35 + pairing * 0.20

    B) Real CI coverage (only when no LLM estimate):
         coverage * 0.5 + ratio * 0.3 + pairing * 0.2

    C) Diff-heuristic estimated coverage (name-matching, 0.7 discount):
         coverage_est * 0.7 * 0.35 + ratio * 0.4 + pairing * 0.25

    D) Tests exist but no coverage data — ratio + pairing only

    E) No tests at all → 0.0

    Clamped to [0, 10].
    """
    has_tests = test_lines_added > 0

    if production_lines_added > 0:
        ratio = min(test_lines_added / production_lines_added, 1.0)
    else:
        ratio = 1.0 if has_tests else 0.0

    ratio_score = ratio * 10.0
    pairing_score = test_file_pairing_rate * 10.0

    # Prefer LLM estimate over mechanical coverage when both exist
    if llm_estimated_coverage is not None:
        coverage_score = llm_estimated_coverage * 0.85 * 10.0
        raw = coverage_score * 0.45 + ratio_score * 0.35 + pairing_score * 0.20
    elif change_coverage > 0.0:
        coverage_score = change_coverage * 10.0
        raw = coverage_score * 0.5 + ratio_score * 0.3 + pairing_score * 0.2
    elif diff_estimated_coverage is not None:
        coverage_score = diff_estimated_coverage * 0.7 * 10.0
        raw = coverage_score * 0.35 + ratio_score * 0.4 + pairing_score * 0.25
    elif has_tests:
        raw = ratio_score * 0.55 + pairing_score * 0.45
    else:
        raw = 0.0

    return round(min(max(raw, 0.0), 10.0), 2)


class MetricsEngine:
    """Computes PR-level and aggregate metrics, and persists them via a storage backend.

    The storage backend defaults to ``JSONStorage`` to preserve backwards
    compatibility with existing ``/metrics/pr_*.json`` files.  Pass a different
    ``StorageBackend`` (e.g. ``SQLiteStorage``) to change persistence behaviour
    without touching computation logic.
    """

    def __init__(self, storage: Optional[StorageBackend] = None) -> None:
        self._storage: StorageBackend = storage or JSONStorage()

    # ------------------------------------------------------------------
    # PR metrics computation
    # ------------------------------------------------------------------

    def compute_pr_metrics(
        self,
        pr_number: int,
        author: str,
        title: str,
        repo: str,
        file_changes: list[FileChange],
        test_files: list[TestFile],
        lines_covered: int,
        lines_modified: int,
        jira_ticket: Optional[str] = None,
        jira_issue: Optional[JiraIssue] = None,
        pr_date: Optional[datetime] = None,
        coverage_result: Optional[CoverageResult] = None,
        production_lines_added: int = 0,
        test_lines_added: int = 0,
        diff_estimated_coverage: Optional[float] = None,
        test_file_pairing_rate: float = 0.0,
        assertion_count: int = 0,
        has_testable_code: bool = True,
        is_modification_only: bool = False,
    ) -> PRMetrics:
        # Prefer richer CoverageResult when available
        if coverage_result is not None and coverage_result.ran_successfully:
            lines_covered = coverage_result.lines_covered
            lines_modified = coverage_result.lines_modified or lines_modified
            overall_coverage = coverage_result.overall_percent
            change_coverage = coverage_result.change_coverage
        else:
            change_coverage = (lines_covered / lines_modified) if lines_modified > 0 else 0.0
            overall_coverage = None

        tests_added = len(test_files)  # all test files touched (new + modified)
        test_types = self._count_test_types(test_files)

        test_code_ratio = (
            test_lines_added / production_lines_added if production_lines_added > 0 else 0.0
        )

        testing_quality_score = _compute_testing_quality_score(
            change_coverage=change_coverage,
            test_lines_added=test_lines_added,
            production_lines_added=production_lines_added,
            diff_estimated_coverage=diff_estimated_coverage,
            test_file_pairing_rate=test_file_pairing_rate,
        )

        return PRMetrics(
            pr_number=pr_number,
            author=author,
            title=title,
            repo=repo,
            pr_date=pr_date,
            jira_ticket=jira_ticket,
            jira_issue=jira_issue,
            files_changed=len(file_changes),
            lines_modified=lines_modified,
            lines_covered=lines_covered,
            change_coverage=change_coverage,
            production_lines_added=production_lines_added,
            production_lines_modified=lines_modified,
            test_lines_added=test_lines_added,
            overall_coverage=overall_coverage,
            test_code_ratio=test_code_ratio,
            testing_quality_score=testing_quality_score,
            tests_added=tests_added,
            test_types=test_types,
            file_changes=file_changes,
            test_files=test_files,
            test_file_pairing_rate=test_file_pairing_rate,
            assertion_count=assertion_count,
            has_testable_code=has_testable_code,
            is_modification_only=is_modification_only,
        )

    # ------------------------------------------------------------------
    # Persistence (delegates to storage backend)
    # ------------------------------------------------------------------

    def save_pr_metrics(self, metrics: PRMetrics):
        """Persist metrics via the configured storage backend."""
        self._storage.save(metrics)
        if hasattr(self._storage, "path_for"):
            return self._storage.path_for(metrics.pr_number)  # type: ignore[attr-defined]
        return f"metrics/pr_{metrics.pr_number}"

    def load_pr_metrics(self, pr_number: int) -> Optional[PRMetrics]:
        return self._storage.load(pr_number)

    def load_all_metrics(self) -> list[PRMetrics]:
        return self._storage.load_all()

    # ------------------------------------------------------------------
    # Team summary
    # ------------------------------------------------------------------

    def compute_team_summary(
        self,
        pr_metrics_list: list[PRMetrics],
        repo: str,
        since_days: int,
        repos: Optional[list[str]] = None,
    ) -> TeamSummary:
        """Aggregate a list of PRMetrics into a TeamSummary.

        ``repos`` lists all repositories included in this summary — used for
        multi-repo analyses.  Defaults to ``[repo]`` when omitted.
        """
        repo_list = repos or [repo]

        if not pr_metrics_list:
            return TeamSummary(
                repo=repo,
                repos=repo_list,
                since_days=since_days,
                prs_analyzed=0,
                average_change_coverage=0.0,
                average_testing_quality_score=0.0,
                total_tests_added=0,
                test_type_distribution={},
            )

        avg_coverage = sum(m.change_coverage for m in pr_metrics_list) / len(pr_metrics_list)
        avg_quality = sum(m.testing_quality_score for m in pr_metrics_list) / len(pr_metrics_list)
        total_tests = sum(m.tests_added for m in pr_metrics_list)

        totals: dict[str, int] = {"unit": 0, "integration": 0, "e2e": 0, "unknown": 0}
        for m in pr_metrics_list:
            totals["unit"] += m.test_types.unit
            totals["integration"] += m.test_types.integration
            totals["e2e"] += m.test_types.e2e
            totals["unknown"] += m.test_types.unknown

        grand_total = sum(totals.values())
        distribution = (
            {k: v / grand_total for k, v in totals.items() if v > 0}
            if grand_total > 0
            else {}
        )

        by_author = self._compute_by_author(pr_metrics_list)

        top_contributors = [
            {
                "author": author,
                "prs": stats.prs,
                "avg_change_coverage": round(stats.avg_change_coverage * 100, 1),
                "avg_testing_quality_score": round(stats.avg_testing_quality_score, 2),
                "tests_added": stats.tests_added,
            }
            for author, stats in sorted(
                by_author.items(), key=lambda x: x[1].prs, reverse=True
            )
        ]

        return TeamSummary(
            repo=repo,
            repos=repo_list,
            since_days=since_days,
            prs_analyzed=len(pr_metrics_list),
            average_change_coverage=avg_coverage,
            average_testing_quality_score=round(avg_quality, 2),
            total_tests_added=total_tests,
            test_type_distribution=distribution,
            top_contributors=top_contributors,
            by_author=by_author,
            by_issue_type=self._compute_by_issue_type(pr_metrics_list),
            by_repo=self._compute_by_repo(pr_metrics_list),
            coverage_trend=self._compute_coverage_trend(pr_metrics_list),
            pr_metrics=pr_metrics_list,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _count_test_types(self, test_files: list[TestFile]) -> TestTypeCount:
        counts = TestTypeCount()
        for t in test_files:
            if t.test_type == TestType.unit:
                counts.unit += 1
            elif t.test_type == TestType.integration:
                counts.integration += 1
            elif t.test_type == TestType.e2e:
                counts.e2e += 1
            else:
                counts.unknown += 1
        return counts

    def _compute_by_author(self, metrics: list[PRMetrics]) -> dict[str, AuthorStats]:
        accumulator: dict[str, dict] = {}
        for m in metrics:
            if m.author not in accumulator:
                accumulator[m.author] = {
                    "prs": 0,
                    "coverage_sum": 0.0,
                    "quality_sum": 0.0,
                    "tests_added": 0,
                    "lines_modified": 0,
                }
            acc = accumulator[m.author]
            acc["prs"] += 1
            acc["coverage_sum"] += m.change_coverage
            acc["quality_sum"] += m.testing_quality_score
            acc["tests_added"] += m.tests_added
            acc["lines_modified"] += m.lines_modified

        return {
            author: AuthorStats(
                prs=acc["prs"],
                avg_change_coverage=acc["coverage_sum"] / acc["prs"],
                avg_testing_quality_score=round(acc["quality_sum"] / acc["prs"], 2),
                tests_added=acc["tests_added"],
                lines_modified=acc["lines_modified"],
            )
            for author, acc in accumulator.items()
        }

    def _compute_by_issue_type(self, metrics: list[PRMetrics]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for m in metrics:
            if m.jira_issue and m.jira_issue.issue_type:
                key = m.jira_issue.issue_type
                counts[key] = counts.get(key, 0) + 1
        return counts

    def _compute_by_repo(self, metrics: list[PRMetrics]) -> dict[str, dict]:
        repos: dict[str, dict] = {}
        for m in metrics:
            if m.repo not in repos:
                repos[m.repo] = {
                    "prs": 0,
                    "coverage_sum": 0.0,
                    "quality_sum": 0.0,
                    "tests_added": 0,
                }
            r = repos[m.repo]
            r["prs"] += 1
            r["coverage_sum"] += m.change_coverage
            r["quality_sum"] += m.testing_quality_score
            r["tests_added"] += m.tests_added

        return {
            repo_name: {
                "prs": d["prs"],
                "avg_change_coverage_pct": round(d["coverage_sum"] / d["prs"] * 100, 1),
                "avg_testing_quality_score": round(d["quality_sum"] / d["prs"], 2),
                "tests_added": d["tests_added"],
            }
            for repo_name, d in repos.items()
        }

    def _compute_coverage_trend(self, metrics: list[PRMetrics]) -> list[dict]:
        points = [
            {
                "pr_number": m.pr_number,
                "repo": m.repo,
                "date": m.pr_date.isoformat() if m.pr_date else None,
                "change_coverage": round(m.change_coverage * 100, 1),
                "testing_quality_score": m.testing_quality_score,
                "author": m.author,
            }
            for m in metrics
        ]
        points.sort(key=lambda x: x["date"] or "")
        return points
