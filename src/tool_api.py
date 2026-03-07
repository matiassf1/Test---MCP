from __future__ import annotations

"""Simple callable API surface for the PR analysis tool.

These functions expose the tool's capabilities as plain Python callables so
they can be consumed by:
- MCP tool definitions
- LangChain / agent tool wrappers
- Jupyter notebooks or scripts
- Direct programmatic use

All functions gracefully return ``None`` or empty structures on failure rather
than raising, consistent with the tool's reliability requirements.
"""

from typing import Any, Optional

from src.models import PRMetrics, TeamSummary
from src.storage import JSONStorage, StorageBackend, create_storage


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _default_storage() -> StorageBackend:
    return JSONStorage()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_pr(
    repo: str,
    pr: int,
    repo_path: Optional[str] = None,
    storage: Optional[StorageBackend] = None,
    use_cache: bool = False,
) -> Optional[PRMetrics]:
    """Fetch a GitHub PR, run the full analysis pipeline, persist metrics, and
    return the ``PRMetrics`` result.

    Args:
        repo:       GitHub repository in ``org/name`` format.
        pr:         Pull Request number.
        repo_path:  Local path to a checkout of the repo.  When provided,
                    pytest coverage is run to compute Change Coverage.
                    If omitted, coverage is skipped and reported as 0%.
        storage:    Storage backend instance.  Defaults to ``JSONStorage``.
        use_cache:  When ``True``, GitHub API responses are cached on disk to
                    avoid hitting rate limits when re-analyzing the same PRs.

    Returns:
        ``PRMetrics`` on success, or ``None`` if the GitHub fetch fails.
    """
    from src.pr_analysis_pipeline import PRAnalysisPipeline

    backend = storage or _default_storage()
    pipeline = PRAnalysisPipeline(storage=backend, use_cache=use_cache)
    try:
        metrics = pipeline.analyze_pr(repo=repo, pr_number=pr, repo_path=repo_path)
        pipeline.save(metrics)
        return metrics
    except Exception:
        return None


def get_pr_metrics(
    repo: str,
    pr: int,
    storage: Optional[StorageBackend] = None,
) -> Optional[PRMetrics]:
    """Load previously persisted metrics for a PR from storage.

    Returns ``None`` if the PR has not been analyzed yet.
    """
    backend = storage or _default_storage()
    return backend.load(pr)


def get_repo_summary(
    repo: str,
    since_days: int = 30,
    storage: Optional[StorageBackend] = None,
) -> TeamSummary:
    """Build a ``TeamSummary`` for a single repository from persisted metrics.

    Filters to PRs belonging to ``repo``.  If no metrics exist, returns an
    empty summary rather than raising.
    """
    from src.metrics_engine import MetricsEngine

    backend = storage or _default_storage()
    engine = MetricsEngine(storage=backend)
    all_metrics = engine.load_all_metrics()
    repo_metrics = [m for m in all_metrics if m.repo == repo]
    return engine.compute_team_summary(repo_metrics, repo=repo, since_days=since_days)


def get_author_summary(
    author: str,
    storage: Optional[StorageBackend] = None,
) -> dict[str, Any]:
    """Return aggregate statistics for a single author across all stored PRs.

    Returns a dict with keys:
      - ``author``
      - ``prs`` — total PR count
      - ``repos`` — list of distinct repos
      - ``avg_change_coverage_pct``
      - ``avg_testing_quality_score``
      - ``total_tests_added``
      - ``total_lines_modified``
      - ``pr_numbers`` — sorted list of analyzed PR numbers
    """
    backend = storage or _default_storage()
    all_metrics = backend.load_all()
    author_metrics = [m for m in all_metrics if m.author == author]

    if not author_metrics:
        return {
            "author": author,
            "prs": 0,
            "repos": [],
            "avg_change_coverage_pct": 0.0,
            "avg_testing_quality_score": 0.0,
            "total_tests_added": 0,
            "total_lines_modified": 0,
            "pr_numbers": [],
        }

    avg_cov = sum(m.change_coverage for m in author_metrics) / len(author_metrics)
    avg_quality = sum(m.testing_quality_score for m in author_metrics) / len(author_metrics)

    return {
        "author": author,
        "prs": len(author_metrics),
        "repos": sorted({m.repo for m in author_metrics}),
        "avg_change_coverage_pct": round(avg_cov * 100, 2),
        "avg_testing_quality_score": round(avg_quality, 2),
        "total_tests_added": sum(m.tests_added for m in author_metrics),
        "total_lines_modified": sum(m.lines_modified for m in author_metrics),
        "pr_numbers": sorted(m.pr_number for m in author_metrics),
    }


def get_multi_repo_summary(
    repos: list[str],
    since_days: int = 30,
    storage: Optional[StorageBackend] = None,
) -> TeamSummary:
    """Build a combined ``TeamSummary`` across multiple repositories.

    Useful for organisation-wide dashboards or agent queries.
    """
    from src.metrics_engine import MetricsEngine

    backend = storage or _default_storage()
    engine = MetricsEngine(storage=backend)
    all_metrics = engine.load_all_metrics()
    filtered = [m for m in all_metrics if m.repo in repos]
    repo_label = ", ".join(sorted(repos))
    return engine.compute_team_summary(filtered, repo=repo_label, since_days=since_days)


def batch_analyze_author(
    author: str,
    org: str,
    since_days: int = 30,
    limit: int = 20,
    skip_existing: bool = True,
    storage: Optional[StorageBackend] = None,
) -> dict[str, Any]:
    """Discover and analyze all merged PRs by *author* across every repo in *org*.

    GitHub Search API is used to find PRs; each is then run through the full
    analysis pipeline.  Already-analyzed PRs are skipped by default
    (``skip_existing=True``) to avoid redundant API calls.

    Returns a dict with:
      - ``analyzed``   — list of {repo, pr, status} for PRs processed this run
      - ``skipped``    — count of PRs already in storage
      - ``failed``     — count of PRs that errored
      - ``total_found``— total PRs found on GitHub
    """
    from src.github_service import GitHubService
    from src.pr_analysis_pipeline import PRAnalysisPipeline

    backend = storage or _default_storage()
    existing_keys = {(m.repo, m.pr_number) for m in backend.load_all()}

    try:
        gh = GitHubService()
        pr_refs = gh.get_merged_prs_by_author_org(
            org=org, author=author, since_days=since_days, limit=limit
        )
    except Exception as e:
        return {"error": str(e), "analyzed": [], "skipped": 0, "failed": 0, "total_found": 0}

    analyzed = []
    skipped = 0
    failed = 0

    pipeline = PRAnalysisPipeline(storage=backend)

    for repo, pr_number in pr_refs:
        if skip_existing and (repo, pr_number) in existing_keys:
            skipped += 1
            continue
        try:
            metrics = pipeline.analyze_pr(repo=repo, pr_number=pr_number)
            pipeline.save(metrics)
            analyzed.append({"repo": repo, "pr": pr_number, "status": "ok",
                             "score": metrics.testing_quality_score})
        except Exception as e:
            failed += 1
            analyzed.append({"repo": repo, "pr": pr_number, "status": "error", "error": str(e)})

    return {
        "total_found": len(prs),
        "analyzed": analyzed,
        "skipped": skipped,
        "failed": failed,
    }
    return {
        "total_found": len(pr_refs),
        "analyzed": analyzed,
        "skipped": skipped,
        "failed": failed,
    }


def batch_analyze_repo(
    repo: str,
    since_days: int = 30,
    limit: int = 20,
    skip_existing: bool = True,
    storage: Optional[StorageBackend] = None,
) -> dict[str, Any]:
    """Discover and analyze all merged PRs in a single *repo* since *since_days* ago.

    Returns the same shape as ``batch_analyze_author``.
    """
    from src.github_service import GitHubService
    from src.pr_analysis_pipeline import PRAnalysisPipeline

    backend = storage or _default_storage()
    existing_keys = {(m.repo, m.pr_number) for m in backend.load_all()}

    try:
        gh = GitHubService()
        prs = gh.get_merged_prs_since(repo_name=repo, since_days=since_days)
    except Exception as e:
        return {"error": str(e), "analyzed": [], "skipped": 0, "failed": 0, "total_found": 0}

    prs = prs[:limit]
    analyzed = []
    skipped = 0
    failed = 0

    pipeline = PRAnalysisPipeline(storage=backend)

    for pr in prs:
        pr_number = pr.number
        if skip_existing and (repo, pr_number) in existing_keys:
            skipped += 1
            continue
        try:
            metrics = pipeline.analyze_pr(repo=repo, pr_number=pr_number)
            pipeline.save(metrics)
            analyzed.append({"repo": repo, "pr": pr_number, "status": "ok",
                             "score": metrics.testing_quality_score})
        except Exception as e:
            failed += 1
            analyzed.append({"repo": repo, "pr": pr_number, "status": "error", "error": str(e)})
