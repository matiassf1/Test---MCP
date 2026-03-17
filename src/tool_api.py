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
    return backend.load(pr, repo=repo)


def get_pr_description_report(
    repo: str,
    pr: int,
    storage: Optional[StorageBackend] = None,
    run_analysis_if_missing: bool = True,
) -> dict[str, Any]:
    """Return a markdown snippet suitable for pasting into the PR description.

    Contains: testing quality score, coverage, test ratio, and AI analysis (if available).
    If metrics are not in storage and run_analysis_if_missing is True, runs analyze_pr first.

    Returns:
        - On success: {"markdown": "<markdown string>", "from_cache": bool}
        - On failure: {"error": "<message>"}
    """
    from src.report_generator import ReportGenerator

    backend = storage or _default_storage()
    all_metrics = backend.load_all()
    metrics = next((m for m in all_metrics if m.repo == repo and m.pr_number == pr), None)
    from_cache = metrics is not None
    if not metrics and run_analysis_if_missing:
        metrics = analyze_pr(repo=repo, pr=pr, storage=backend)
    if not metrics:
        return {
            "error": "No metrics for this PR. Run analyze_pr first or ensure run_analysis_if_missing is True.",
        }
    snippet = ReportGenerator().pr_description_snippet(metrics)
    return {"markdown": snippet, "from_cache": from_cache}


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

    avg_cov = sum(m.effective_coverage for m in author_metrics) / len(author_metrics)
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


def list_prs_by_jira_ticket(
    ticket_key: str,
    org: str,
    limit: int = 20,
) -> dict[str, Any]:
    """List merged PRs that mention the given Jira ticket (title, body, or branch).

    Returns a dict with:
      - ``prs`` — list of {repo, pr} for each PR found
      - ``total`` — length of that list
    Use with analyze_pr to process one-by-one, or analyze_pr_by_jira_ticket to analyze the first.
    """
    from src.github_service import GitHubService

    try:
        gh = GitHubService()
        pr_refs = gh.get_prs_mentioning_ticket(ticket_key=ticket_key, org=org, limit=limit)
        prs = [{"repo": repo, "pr": pr_number} for repo, pr_number in pr_refs]
        return {"ticket": ticket_key, "prs": prs, "total": len(prs)}
    except Exception as e:
        return {"ticket": ticket_key, "error": str(e), "prs": [], "total": 0}


def analyze_pr_by_jira_ticket(
    ticket_key: str,
    org: str,
    pr_index: int = 0,
    storage: Optional[StorageBackend] = None,
) -> dict[str, Any]:
    """Find merged PR(s) that mention the Jira ticket, analyze the one at pr_index (default first), and return metrics.

    Returns the same shape as analyze_pr (metrics + files_summary + ai_report) in key ``metrics``,
    plus ``repo`` and ``pr`` that were analyzed. If no PRs found: ``{ "error": "...", "ticket": "..." }``.
    """
    from src.github_service import GitHubService
    from src.pr_analysis_pipeline import PRAnalysisPipeline

    backend = storage or _default_storage()
    try:
        gh = GitHubService()
        pr_refs = gh.get_prs_mentioning_ticket(ticket_key=ticket_key, org=org, limit=10)
    except Exception as e:
        return {"error": str(e), "ticket": ticket_key}

    if not pr_refs:
        return {"error": f"No merged PRs found for ticket {ticket_key} in org {org}", "ticket": ticket_key}

    idx = max(0, min(pr_index, len(pr_refs) - 1))
    repo, pr_number = pr_refs[idx]
    pipeline = PRAnalysisPipeline(storage=backend)
    try:
        metrics = pipeline.analyze_pr(repo=repo, pr_number=pr_number)
        pipeline.save(metrics)
        return {
            "ticket": ticket_key,
            "repo": repo,
            "pr": pr_number,
            "metrics": _metrics_dict_for_ticket(metrics),
        }
    except Exception as e:
        return {"error": str(e), "ticket": ticket_key, "repo": repo, "pr": pr_number}


def _metrics_dict_for_ticket(metrics) -> dict:
    """Same shape as _metrics_dict in MCP (for analyze_pr response)."""
    d = metrics.model_dump(exclude={"file_changes", "test_files"})
    d["files_summary"] = [
        {"file": fc.filename, "status": fc.status, "additions": fc.additions}
        for fc in (metrics.file_changes or [])
    ]
    return d


def analyze_epic(
    epic_key: str,
    org: str,
    repo: str = "",
    limit_per_ticket: int = 30,
    skip_existing: bool = False,
    include_ai_report: bool = True,
    storage: Optional[StorageBackend] = None,
) -> dict[str, Any]:
    """Map an Epic to its child tickets and linked PRs, analyze each PR, return a full report.

    Uses Jira to fetch Epic metadata and child issues (if configured); then GitHub Search
    to find merged PRs mentioning the Epic key or any child ticket; analyzes each PR and
    returns a consolidated report with metrics and optional ai_report per PR.

    Returns a dict with:
      - epic_key, epic_summary (from Jira if available)
      - child_tickets: list of { key, summary, issue_type, status } from Jira
      - prs_analyzed: list of { repo, pr, ticket_linked, title, metrics summary, ai_report? }
      - summary: { total_prs, failed, avg_testing_quality_score, total_tests_added, ... }
    """
    from src.github_service import GitHubService
    from src.jira_service import JiraService
    from src.pr_analysis_pipeline import PRAnalysisPipeline

    backend = storage or _default_storage()
    epic_key = epic_key.upper().strip()
    scope = f"repo:{repo}" if repo else f"org:{org}"

    # ---- 1. Epic + child tickets from Jira ----
    epic_issue = None
    child_issues: list[Any] = []
    try:
        jira_svc = JiraService()
        if jira_svc.is_available():
            epic_issue = jira_svc.fetch_issue(epic_key)
            child_issues = jira_svc.fetch_epic_issues(epic_key) or []
    except Exception:
        pass

    ticket_keys = [epic_key] + [getattr(ci, "key", str(ci)) for ci in child_issues]

    # ---- 2. Discover PRs via GitHub Search ----
    try:
        gh = GitHubService()
        pr_set: dict[tuple[str, int], str] = {}  # (repo, pr_number) -> ticket_key
        for key in ticket_keys:
            try:
                pairs = gh.get_prs_mentioning_ticket(
                    key, repo=repo, org=org, limit=limit_per_ticket
                )
                for (r, p) in pairs:
                    if (r, p) not in pr_set:
                        pr_set[(r, p)] = key
            except Exception:
                pass
        pr_targets = list(pr_set.keys())
    except Exception as e:
        return {
            "epic_key": epic_key,
            "error": str(e),
            "child_tickets": [],
            "prs_analyzed": [],
            "summary": {"total_prs": 0, "failed": 0},
        }

    if not pr_targets:
        return {
            "epic_key": epic_key,
            "epic_summary": epic_issue.summary if epic_issue else None,
            "child_tickets": [
                {"key": getattr(c, "key", ""), "summary": getattr(c, "summary", None), "issue_type": getattr(c, "issue_type", None), "status": getattr(c, "status", None)}
                for c in child_issues
            ],
            "prs_analyzed": [],
            "summary": {"total_prs": 0, "failed": 0, "message": "No merged PRs found for this Epic or its child tickets"},
        }

    existing_keys = {(m.repo, m.pr_number) for m in backend.load_all()}
    pipeline = PRAnalysisPipeline(storage=backend)

    def _batch_delay() -> None:
        try:
            from src.config import settings
            if getattr(settings, "openrouter_api_key", "") or getattr(settings, "openai_api_key", ""):
                import time
                delay = max(0.0, getattr(settings, "openrouter_batch_delay_seconds", 12.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            pass

    prs_analyzed: list[dict[str, Any]] = []
    failed = 0
    for (pr_repo, pr_number) in pr_targets:
        if skip_existing and (pr_repo, pr_number) in existing_keys:
            all_stored = backend.load_all()
            existing = next((m for m in all_stored if m.repo == pr_repo and m.pr_number == pr_number), None)
            if existing:
                prs_analyzed.append({
                    "repo": pr_repo, "pr": pr_number, "ticket_linked": pr_set[(pr_repo, pr_number)],
                    "title": existing.title, "author": existing.author,
                    "testing_quality_score": existing.testing_quality_score,
                    "llm_estimated_coverage": existing.llm_estimated_coverage,
                    "tests_added": existing.tests_added,
                    "ai_report": existing.ai_report if include_ai_report else None,
                })
                continue
        try:
            metrics = pipeline.analyze_pr(repo=pr_repo, pr_number=pr_number)
            pipeline.save(metrics)
            prs_analyzed.append({
                "repo": pr_repo, "pr": pr_number, "ticket_linked": pr_set[(pr_repo, pr_number)],
                "title": metrics.title, "author": metrics.author,
                "testing_quality_score": metrics.testing_quality_score,
                "llm_estimated_coverage": metrics.llm_estimated_coverage,
                "tests_added": metrics.tests_added,
                "ai_report": metrics.ai_report if include_ai_report else None,
            })
        except Exception as e:
            failed += 1
            prs_analyzed.append({
                "repo": pr_repo, "pr": pr_number, "ticket_linked": pr_set[(pr_repo, pr_number)],
                "status": "error", "error": str(e),
            })
        _batch_delay()

    total = len(prs_analyzed)
    successful = [p for p in prs_analyzed if "testing_quality_score" in p]
    avg_score = (sum(p["testing_quality_score"] for p in successful) / len(successful)) if successful else 0.0
    total_tests = sum(p.get("tests_added", 0) for p in successful)

    return {
        "epic_key": epic_key,
        "epic_summary": epic_issue.summary if epic_issue else None,
        "child_tickets": [
            {"key": getattr(c, "key", ""), "summary": getattr(c, "summary", None), "issue_type": getattr(c, "issue_type", None), "status": getattr(c, "status", None)}
            for c in child_issues
        ],
        "prs_analyzed": prs_analyzed,
        "summary": {
            "total_prs": total,
            "failed": failed,
            "avg_testing_quality_score": round(avg_score, 2),
            "total_tests_added": total_tests,
        },
    }


def list_prs_by_author(
    author: str,
    org: str,
    since_days: int = 90,
    limit: int = 50,
) -> dict[str, Any]:
    """List merged PRs by author in an org (no analysis). Use with analyze_pr to process one-by-one.

    Returns a dict with:
      - ``prs`` — list of {repo, pr} for each merged PR
      - ``total`` — length of that list
    """
    from src.github_service import GitHubService

    try:
        gh = GitHubService()
        pr_refs = gh.get_merged_prs_by_author_org(
            org=org, author=author, since_days=since_days, limit=limit
        )
        prs = [{"repo": repo, "pr": pr_number} for repo, pr_number in pr_refs]
        return {"prs": prs, "total": len(prs)}
    except Exception as e:
        return {"error": str(e), "prs": [], "total": 0}


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

    def _batch_delay() -> None:
        """Strictly sequential: extra delay between PRs when using OpenRouter to avoid 429."""
        try:
            from src.config import settings
            if getattr(settings, "openrouter_api_key", ""):
                import time
                delay = max(0.0, getattr(settings, "openrouter_batch_delay_seconds", 12.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            pass

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
        _batch_delay()

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

    def _batch_delay() -> None:
        try:
            from src.config import settings
            if getattr(settings, "openrouter_api_key", ""):
                import time
                delay = max(0.0, getattr(settings, "openrouter_batch_delay_seconds", 12.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            pass

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
        _batch_delay()
