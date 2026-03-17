from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# force_terminal=True so output appears when run from non-TTY (e.g. some IDE terminals, CI)
console = Console(force_terminal=True)


# ---------------------------------------------------------------------------
# analyze_change command
# ---------------------------------------------------------------------------

def cmd_analyze_change(args: argparse.Namespace) -> int:
    """Fetch a PR, analyze it via PRAnalysisPipeline, and write reports."""
    repo: str = args.repo
    pr_number: int = args.pr
    repo_path: str = getattr(args, "repo_path", "") or ""
    storage_backend: str = getattr(args, "storage", "json")
    use_cache: bool = getattr(args, "cache", False)

    # Immediate feedback (works even if Rich is not rendering)
    print(f"Analyzing PR #{pr_number} in {repo}…", flush=True)

    from src.pr_analysis_pipeline import PRAnalysisPipeline
    from src.report_generator import ReportGenerator
    from src.storage import create_storage

    console.rule(f"[bold blue]Analyzing PR #{pr_number} in {repo}")

    storage = create_storage(storage_backend)
    pipeline = PRAnalysisPipeline(storage=storage, use_cache=use_cache)

    try:
        with console.status("Fetching PR and running analysis…"):
            metrics = pipeline.analyze_pr(
                repo=repo,
                pr_number=pr_number,
                repo_path=repo_path or None,
            )
    except Exception as exc:
        err = str(exc).strip()
        msg = (
            "PR or repo not found. Check repo name and PR number. If the repo is private, ensure GITHUB_TOKEN has access."
            if ("404" in err or "Not Found" in err)
            else "Access forbidden. GITHUB_TOKEN may lack scope or the repo may be private."
            if ("403" in err or "Forbidden" in err)
            else f"Analysis failed: {exc}"
        )
        print(f"Error: {msg}", file=sys.stderr, flush=True)
        console.print(f"[red]{msg}[/red]")
        return 1

    console.print(
        f"[green]✓[/green] PR fetched: [bold]{metrics.title}[/bold] by {metrics.author}"
    )

    if metrics.jira_ticket:
        console.print(f"[green]✓[/green] Jira ticket: {metrics.jira_ticket}", end="")
        if metrics.jira_issue:
            ji = metrics.jira_issue
            console.print(f" — [dim]{ji.issue_type or 'Issue'}[/dim]: {ji.summary or '—'}")
        else:
            console.print()
    else:
        console.print(
            "[yellow]No Jira ticket found in PR title, branch, or description.[/yellow]"
        )

    if not repo_path:
        if metrics.change_coverage > 0:
            console.print(
                "[green]✓[/green] Coverage fetched from GitHub Actions artifact "
                f"({metrics.change_coverage * 100:.0f}% change coverage)."
            )
        else:
            console.print(
                "[yellow]--repo-path not provided; tried GitHub Actions artifacts "
                "but none found. Coverage score uses 0%.[/yellow]"
            )

    metrics_path = pipeline.save(metrics)
    console.print(f"[green]✓[/green] Metrics saved → {metrics_path}")

    reporter = ReportGenerator()
    md_path, json_path = reporter.generate_pr_report(metrics)

    _print_pr_summary(metrics)
    _print_timings(pipeline.timings)

    console.print("\n[bold]Reports written:[/bold]")
    console.print(f"  {md_path}")
    console.print(f"  {json_path}")

    return 0


# ---------------------------------------------------------------------------
# pr_description_report command
# ---------------------------------------------------------------------------

def cmd_pr_description_report(args: argparse.Namespace) -> int:
    """Print markdown snippet for PR description (paste into GitHub PR body)."""
    from src.tool_api import get_pr_description_report
    from src.storage import create_storage

    repo: str = args.repo
    pr_number: int = args.pr
    run_analysis: bool = getattr(args, "run_analysis", True)
    storage_backend: str = getattr(args, "storage", "json")

    storage = create_storage(storage_backend)
    out = get_pr_description_report(
        repo=repo,
        pr=pr_number,
        storage=storage,
        run_analysis_if_missing=run_analysis,
    )
    if "error" in out:
        console.print(f"[red]{out['error']}[/red]")
        return 1
    markdown = out.get("markdown", "")
    from_cache = out.get("from_cache", False)
    if from_cache:
        console.print("[dim]Using cached metrics. Run analyze_change to refresh.[/dim]\n")
    console.print(Panel(markdown, title="Copy into PR description", border_style="green"))
    console.print("\n[dim]Paste the content above into your PR description (e.g. under \"Testing quality\").[/dim]")
    return 0


def _print_pr_summary(m) -> None:
    from src.report_generator import _score_badge

    coverage_pct = f"{m.change_coverage * 100:.0f}%"
    ticket = m.jira_ticket or "—"
    date_str = m.pr_date.strftime("%Y-%m-%d") if m.pr_date else "—"
    badge = _score_badge(m.testing_quality_score)

    table = Table(box=box.ROUNDED, show_header=False, padding=(0, 1))
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")

    table.add_row("Author", m.author)
    table.add_row("Date", date_str)
    table.add_row("Ticket", ticket)

    if m.jira_issue:
        ji = m.jira_issue
        table.add_row("Issue type", ji.issue_type or "—")
        table.add_row("Issue status", ji.status or "—")

    table.add_row("Files changed", str(m.files_changed))
    table.add_row("Prod lines added", str(m.production_lines_added))
    table.add_row("Test lines added", str(m.test_lines_added))
    table.add_row("Test / Code ratio", f"{m.test_code_ratio:.2f}")
    table.add_row("Tests added", str(m.tests_added))
    table.add_row("Change Coverage", f"[bold green]{coverage_pct}[/bold green]")
    table.add_row(
        "Testing Quality Score",
        f"[bold yellow]{m.testing_quality_score} / 10[/bold yellow] ({badge})",
    )

    if m.overall_coverage is not None:
        table.add_row("Overall coverage", f"{m.overall_coverage:.1f}%")

    types = m.test_types
    if types.total():
        parts = []
        if types.unit:
            parts.append(f"unit: {types.unit}")
        if types.integration:
            parts.append(f"integration: {types.integration}")
        if types.e2e:
            parts.append(f"e2e: {types.e2e}")
        if types.unknown:
            parts.append(f"other: {types.unknown}")
        table.add_row("Test types", ", ".join(parts))

    console.print(Panel(table, title=f"[bold]PR #{m.pr_number}[/bold]", expand=False))


def _print_timings(timings: dict) -> None:
    if not timings:
        return

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Step", style="dim")
    table.add_column("ms", justify="right")
    table.add_column("", style="dim")

    step_labels = {
        "github_pr": "GitHub PR metadata",
        "github_files_and_jira": "Files + Jira (parallel)",
        "change_analysis": "Change analysis",
        "coverage": "Coverage",
        "metrics": "Metrics",
        "ollama": "Ollama AI",
    }

    for key, label in step_labels.items():
        val = timings.get(key)
        if val is None:
            continue
        note = " [dim](parallel)[/dim]" if key == "github_files_and_jira" else ""
        table.add_row(label, f"{val:.0f}", note)

    total = timings.get("total")
    if total is not None:
        table.add_section()
        table.add_row("[bold]total[/bold]", f"[bold]{total:.0f}[/bold]", "")

    console.print("\n[bold]Step timings (ms):[/bold]")
    console.print(table)


def _print_ai_analysis(ai) -> None:
    from rich.panel import Panel
    from rich.text import Text

    body = Text()
    body.append(f"{ai.assessment}\n\n", style="")
    body.append(f"AI Quality Score: ", style="bold")
    body.append(f"{ai.ai_quality_score} / 10\n", style="bold yellow")
    body.append(f"{ai.reasoning}\n", style="dim")

    if ai.untested_areas:
        body.append("\nUntested areas:\n", style="bold red")
        for area in ai.untested_areas:
            body.append(f"  • {area}\n", style="red")

    if ai.suggestions:
        body.append("\nSuggestions:\n", style="bold cyan")
        for s in ai.suggestions:
            body.append(f"  • {s}\n", style="cyan")

    console.print(Panel(body, title="[bold magenta]AI Analysis[/bold magenta]", expand=False))


# ---------------------------------------------------------------------------
# analyze_author command
# ---------------------------------------------------------------------------

def cmd_analyze_author(args: argparse.Namespace) -> int:
    """Fetch all merged PRs by an author and run the full analysis pipeline on each."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

    from src.github_service import GitHubService
    from src.metrics_engine import MetricsEngine
    from src.pr_analysis_pipeline import PRAnalysisPipeline
    from src.report_generator import ReportGenerator
    from src.storage import create_storage

    author: str = args.author
    since_days: int = _parse_since(args.since) or 30
    limit: int = args.limit
    storage_backend: str = getattr(args, "storage", "json")
    use_cache: bool = getattr(args, "cache", False)

    repo: str = getattr(args, "repo", "") or ""
    org: str = getattr(args, "org", "") or ""
    scope = f"org:{org}" if org else repo
    console.rule(f"[bold blue]Author Analysis — {author} @ {scope} — last {since_days}d")

    # ---- Discover PRs -------------------------------------------------------
    # pr_targets: list of (repo_full_name, pr_number)
    with console.status(f"Searching merged PRs by [bold]{author}[/bold]…"):
        try:
            gh = GitHubService()
            if org:
                pr_targets = gh.get_merged_prs_by_author_org(
                    org, author, since_days, limit=limit
                )
            else:
                prs = gh.get_merged_prs_by_author(repo, author, since_days, limit=limit)
                pr_targets = [(repo, pr.number) for pr in prs]
        except Exception as exc:
            console.print(f"[red]Failed to fetch PRs:[/red] {exc}")
            return 1

    if not pr_targets:
        console.print(
            f"[yellow]No merged PRs found for {author} in {scope} in the last {since_days}d.[/yellow]"
        )
        return 0

    console.print(f"[green]✓[/green] Found [bold]{len(pr_targets)}[/bold] merged PRs — starting analysis…\n")

    # ---- Analyze each PR ----------------------------------------------------
    storage = create_storage(storage_backend)
    pipeline = PRAnalysisPipeline(storage=storage, use_cache=use_cache)
    engine = MetricsEngine(storage=storage)
    reporter = ReportGenerator()

    all_metrics = []
    failed = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Analyzing PRs…", total=len(pr_targets))

        for pr_repo, pr_number in pr_targets:
            progress.update(task, description=f"[dim]{pr_repo}[/dim] PR #{pr_number}")
            try:
                metrics = pipeline.analyze_pr(repo=pr_repo, pr_number=pr_number)
                engine.save_pr_metrics(metrics)
                reporter.generate_pr_report(metrics)
                all_metrics.append(metrics)
            except Exception as exc:
                failed.append((pr_repo, pr_number, str(exc)))
            progress.advance(task)

    # ---- Results summary ----------------------------------------------------
    console.print()
    if failed:
        for pr_repo, pr_num, err in failed:
            console.print(f"  [yellow]{pr_repo} PR #{pr_num} skipped:[/yellow] {err}")

    if not all_metrics:
        console.print("[red]All PRs failed analysis.[/red]")
        return 1

    console.print(
        f"[green]✓[/green] Analyzed [bold]{len(all_metrics)}[/bold] PRs"
        + (f", [yellow]{len(failed)} skipped[/yellow]" if failed else "")
    )

    # ---- Author summary report ----------------------------------------------
    repos_in_summary = list({m.repo for m in all_metrics})
    summary_repo = repo or org
    summary = engine.compute_team_summary(
        all_metrics, repo=summary_repo, since_days=since_days, repos=repos_in_summary
    )
    md_path, json_path = reporter.generate_summary_report(summary)

    _print_author_summary(author, all_metrics)

    console.print("\n[bold]Individual PR reports written to:[/bold] reports/")
    console.print("\n[bold]Author summary:[/bold]")
    console.print(f"  {md_path}")
    console.print(f"  {json_path}")

    return 0


def _print_author_summary(author: str, metrics_list: list) -> None:
    from src.report_generator import _score_badge

    if not metrics_list:
        return

    # Exclude contract-only from averages (they use N/A, not a numeric score)
    scored = [m for m in metrics_list if not getattr(m, "is_contract_only", False)]
    n = len(scored) or 1
    avg_quality = sum(m.testing_quality_score for m in scored) / n
    avg_coverage = sum(m.effective_coverage for m in metrics_list) / len(metrics_list)
    total_tests = sum(m.tests_added for m in metrics_list)

    table = Table(box=box.ROUNDED, show_header=True, padding=(0, 1))
    table.add_column("PR", style="dim", justify="right")
    table.add_column("Title")
    table.add_column("Date", style="dim")
    table.add_column("Tests", justify="right")
    table.add_column("Cov%", justify="right")
    table.add_column("Score", justify="right")

    for m in sorted(metrics_list, key=lambda x: x.pr_date or "", reverse=True):
        date_str = m.pr_date.strftime("%Y-%m-%d") if m.pr_date else "—"
        cov = f"{m.effective_coverage * 100:.0f}%"
        if getattr(m, "is_contract_only", False):
            score_cell = "Contract-only"
        else:
            badge = _score_badge(m.testing_quality_score)
            score_cell = f"{m.testing_quality_score} ({badge})"
        table.add_row(
            f"#{m.pr_number}",
            m.title[:55] + ("…" if len(m.title) > 55 else ""),
            date_str,
            str(m.tests_added),
            cov,
            score_cell,
        )

    console.print(
        Panel(
            table,
            title=f"[bold]Merged PRs by {author}[/bold]  "
            f"avg quality [bold yellow]{avg_quality:.1f}/10[/bold yellow]  "
            f"avg coverage [bold green]{avg_coverage * 100:.0f}%[/bold green]  "
            f"total tests added [bold]{total_tests}[/bold]",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# generate_summary command
# ---------------------------------------------------------------------------

def cmd_generate_summary(args: argparse.Namespace) -> int:
    """Generate an aggregated summary (single or multi-repo)."""
    from src.change_analyzer import ChangeAnalyzer
    from src.jira_service import JiraService, extract_ticket
    from src.metrics_engine import MetricsEngine
    from src.report_generator import ReportGenerator
    from src.storage import create_storage
    from src.test_detector import TestDetector

    since_raw: str = args.since
    storage_backend: str = getattr(args, "storage", "json")
    use_cache: bool = getattr(args, "cache", False)
    repos_file: str = getattr(args, "repos", "") or ""
    single_repo: str = getattr(args, "repo", "") or ""

    since_days = _parse_since(since_raw)
    if since_days is None:
        console.print(
            f"[red]Invalid --since value:[/red] {since_raw!r}. Use e.g. '30d' or '7d'."
        )
        return 1

    repos = _resolve_repos(repos_file=repos_file, single_repo=single_repo)
    if not repos:
        console.print("[red]Provide either --repo org/project or --repos repos.yaml[/red]")
        return 1

    repo_label = repos[0] if len(repos) == 1 else f"{len(repos)} repos"
    console.rule(f"[bold blue]Team Summary — {repo_label} — last {since_days}d")

    storage = create_storage(storage_backend)
    engine = MetricsEngine(storage=storage)

    if getattr(args, "fetch", False):
        analyzer = ChangeAnalyzer()
        detector = TestDetector()
        jira_svc = JiraService()

        for repo in repos:
            with console.status(f"Fetching merged PRs for {repo}…"):
                try:
                    from src.github_service import GitHubService
                    gh = GitHubService()
                    prs = gh.get_merged_prs_since(repo, since_days)
                except Exception as exc:
                    console.print(f"[yellow]Skipping {repo}:[/yellow] {exc}")
                    continue

            console.print(f"[green]✓[/green] {len(prs)} merged PRs in {repo}")

            for pr in prs:
                with console.status(f"  Processing PR #{pr.number}…"):
                    try:
                        from src.github_service import GitHubService as GHS
                        file_changes = GHS().get_changed_files(pr)
                        production_changes = analyzer.filter_production_changes(file_changes)
                        test_file_changes = analyzer.filter_test_changes(file_changes)
                        test_files = detector.detect(file_changes)

                        lines_modified = analyzer.total_modified_lines(production_changes)
                        production_lines_added = analyzer.total_added_lines(production_changes)
                        test_lines_added = analyzer.total_added_lines(test_file_changes)

                        branch = getattr(pr.head, "ref", "") or ""
                        description = pr.body or ""
                        jira_ticket = extract_ticket(
                            title=pr.title, branch=branch, description=description
                        )
                        jira_issue = None
                        if jira_ticket and jira_svc.is_available():
                            try:
                                jira_issue = jira_svc.fetch_issue(jira_ticket)
                            except Exception:
                                pass

                        pr_date = (
                            getattr(pr, "merged_at", None)
                            or getattr(pr, "created_at", None)
                        )

                        metrics = engine.compute_pr_metrics(
                            pr_number=pr.number,
                            author=pr.user.login,
                            title=pr.title,
                            repo=repo,
                            file_changes=file_changes,
                            test_files=test_files,
                            lines_covered=0,
                            lines_modified=lines_modified,
                            jira_ticket=jira_ticket,
                            jira_issue=jira_issue,
                            pr_date=pr_date,
                            production_lines_added=production_lines_added,
                            test_lines_added=test_lines_added,
                        )
                        engine.save_pr_metrics(metrics)
                        console.print(f"  [dim]PR #{pr.number}[/dim] saved.")
                    except Exception as exc:
                        console.print(f"  [yellow]Skipped PR #{pr.number}:[/yellow] {exc}")

    # Load stored metrics and filter to requested repos
    all_metrics = engine.load_all_metrics()
    filtered = (
        [m for m in all_metrics if m.repo in repos] if len(repos) > 1 else all_metrics
    )

    if not filtered:
        console.print(
            "[yellow]No metrics found. Run analyze_change first, or use --fetch.[/yellow]"
        )
        return 1

    summary_repo = repos[0] if len(repos) == 1 else ", ".join(sorted(repos))
    summary = engine.compute_team_summary(
        filtered, repo=summary_repo, since_days=since_days, repos=repos
    )

    reporter = ReportGenerator()
    md_path, json_path = reporter.generate_summary_report(summary)

    _print_summary(summary)
    console.print("\n[bold]Reports written:[/bold]")
    console.print(f"  {md_path}")
    console.print(f"  {json_path}")

    return 0


def _print_summary(s) -> None:
    coverage_pct = f"{s.average_change_coverage * 100:.0f}%"

    table = Table(box=box.ROUNDED, show_header=False, padding=(0, 1))
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")

    table.add_row("Repos", ", ".join(s.repos) if s.repos else s.repo)
    table.add_row("PRs analyzed", str(s.prs_analyzed))
    table.add_row("Average Change Coverage", f"[bold green]{coverage_pct}[/bold green]")
    table.add_row(
        "Avg Testing Quality Score",
        f"[bold yellow]{s.average_testing_quality_score} / 10[/bold yellow]",
    )
    table.add_row("Total tests added", str(s.total_tests_added))

    if s.test_type_distribution:
        dist = ", ".join(
            f"{k}: {v * 100:.0f}%" for k, v in sorted(s.test_type_distribution.items())
        )
        table.add_row("Test type distribution", dist)

    if s.top_contributors:
        top = s.top_contributors[0]
        table.add_row(
            "Top contributor",
            f"{top['author']} ({top['prs']} PRs, quality {top['avg_testing_quality_score']})",
        )

    if s.by_issue_type:
        types_str = ", ".join(
            f"{k}: {v}" for k, v in sorted(s.by_issue_type.items(), key=lambda x: -x[1])
        )
        table.add_row("By issue type", types_str)

    console.print(Panel(table, title="[bold]Testing Summary[/bold]", expand=False))


# ---------------------------------------------------------------------------
# analyze_epic command
# ---------------------------------------------------------------------------

def cmd_analyze_epic(args: argparse.Namespace) -> int:
    """Given a Jira Epic key, find all child tickets, discover linked PRs, and analyze them."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

    from src.pr_analysis_pipeline import PRAnalysisPipeline
    from src.report_generator import ReportGenerator
    from src.storage import create_storage

    epic_key: str = args.epic.upper().strip()
    repo: str = getattr(args, "repo", "") or ""
    org: str = getattr(args, "org", "") or ""
    storage_backend: str = getattr(args, "storage", "json")
    use_cache: bool = getattr(args, "cache", False)
    scope = f"org:{org}" if org else repo

    console.rule(f"[bold blue]Epic Analysis — {epic_key} @ {scope}")

    # ---- 1. Discover PRs (Jira epic + children, then GitHub search) ---------
    with console.status(f"Fetching Epic [bold]{epic_key}[/bold] and discovering PRs…"):
        pr_targets, epic_issue = _discover_epic_prs(epic_key, repo, org)

    if epic_issue:
        console.print(
            f"[green]✓[/green] Epic: [bold]{epic_key}[/bold] — {epic_issue.summary or '—'}"
        )
    if not pr_targets:
        console.print(
            f"[red]No merged PRs found mentioning {epic_key} or its child tickets.[/red]"
        )
        return 1

    console.print(f"[green]✓[/green] {len(pr_targets)} unique PRs to analyze")

    # ---- 3. Analyze each PR -------------------------------------------------
    storage = create_storage(storage_backend)
    pipeline = PRAnalysisPipeline(storage=storage, use_cache=use_cache)
    reporter = ReportGenerator()
    all_metrics = []
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Analyzing PRs for {epic_key}…", total=len(pr_targets))
        for pr_repo, pr_number in pr_targets:
            progress.update(task, description=f"PR #{pr_number} in {pr_repo}")
            try:
                metrics = pipeline.analyze_pr(repo=pr_repo, pr_number=pr_number)
                pipeline.save(metrics)
                reporter.generate_pr_report(metrics)
                all_metrics.append(metrics)
            except Exception as exc:
                console.print(f"  [yellow]Skipped PR #{pr_number} ({pr_repo}):[/yellow] {exc}")
                failed += 1
            progress.advance(task)

    # ---- 4. Consolidated epic report ----------------------------------------
    if not all_metrics:
        console.print("[red]All PRs failed to analyze.[/red]")
        return 1

    _print_epic_summary(epic_key, epic_issue, all_metrics, failed)

    # Write markdown report to reports/epic_{key}_report.md
    try:
        report_path = reporter.generate_epic_report(epic_key, epic_issue, all_metrics, failed)
        console.print(f"[green]✓[/green] Report written → [bold]{report_path}[/bold]")
    except Exception as exc:
        console.print(f"[yellow]Could not write epic report:[/yellow] {exc}")

    return 0


def _discover_epic_prs(
    epic_key: str,
    repo: str,
    org: str,
) -> tuple[list[tuple[str, int]], object]:
    """Discover (pr_targets, epic_issue) for an epic. pr_targets = [(repo_full_name, pr_number), ...]."""
    from src.github_service import GitHubService
    from src.jira_service import JiraService

    jira_svc = JiraService()
    epic_issue = None
    child_issues = []

    if jira_svc.is_available():
        try:
            epic_issue = jira_svc.fetch_issue(epic_key)
            child_issues = jira_svc.fetch_epic_issues(epic_key)
        except Exception:
            pass

    gh = GitHubService()
    ticket_keys = [epic_key] + [ci.key for ci in child_issues]
    pr_set: dict[tuple[str, int], str] = {}

    for key in ticket_keys:
        try:
            pairs = gh.get_prs_mentioning_ticket(key, repo=repo, org=org, limit=30)
            for pair in pairs:
                if pair not in pr_set:
                    pr_set[pair] = key
        except Exception:
            pass

    return list(pr_set.keys()), epic_issue


def cmd_generate_workflow_docs(args: argparse.Namespace) -> int:
    """Generate a single Markdown doc of core workflows (Jira Epics), ordered by priority."""
    from pathlib import Path

    from src.jira_service import JiraService
    from src.models import JiraIssue, PRMetrics
    from src.report_generator import ReportGenerator, _extract_ai_summary
    from src.storage import create_storage

    epics_raw = (getattr(args, "epics", "") or "").strip()
    if not epics_raw:
        console.print("[red]--epics is required (comma-separated Epic keys).[/red]")
        return 1
    epic_keys = [k.upper().strip() for k in epics_raw.split(",") if k.strip()]
    if not epic_keys:
        console.print("[red]No valid Epic keys in --epics.[/red]")
        return 1
    output_path = Path(getattr(args, "output", "docs/core-workflows.md"))
    title = getattr(args, "title", "Core Workflows") or "Core Workflows"
    intro = getattr(args, "intro", "") or None
    repo = getattr(args, "repo", "") or ""
    org = getattr(args, "org", "") or ""
    storage_backend = getattr(args, "storage", "json")

    jira_svc = JiraService()
    if not jira_svc.is_available():
        console.print("[red]Jira is not configured. Set JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN.[/red]")
        return 1

    console.rule("[bold blue]Generate workflow docs[/bold blue]")
    console.print(f"Epics: {', '.join(epic_keys)}")
    workflows: list[tuple[str, Optional[JiraIssue], list[JiraIssue]]] = []
    for epic_key in epic_keys:
        with console.status(f"Fetching [bold]{epic_key}[/bold]…"):
            epic_issue = jira_svc.fetch_issue(epic_key)
            child_issues = jira_svc.fetch_epic_issues(epic_key) if jira_svc.is_available() else []
        workflows.append((epic_key, epic_issue, child_issues))
        if epic_issue:
            console.print(f"  [green]✓[/green] {epic_key} — {epic_issue.summary or '—'} ({len(child_issues)} children)")
        else:
            console.print(f"  [yellow]![/yellow] {epic_key} — not found or no access")

    prs_by_epic: Optional[dict[str, list[tuple[str, int, str, Optional[str], Optional[str]]]]] = None
    if repo or org:
        storage = create_storage(storage_backend)
        prs_by_epic = {}
        # Deduplicate: discover once per Epic, cache per (repo, pr_number) to avoid
        # redundant GitHub API calls and storage lookups when PRs span Epics.
        pr_cache: dict[tuple[str, int], Optional[PRMetrics]] = {}
        with console.status("Discovering PRs and loading from storage…"):
            for epic_key in epic_keys:
                pr_targets, _ = _discover_epic_prs(epic_key, repo, org)
                entries: list[tuple[str, int, str, Optional[str], Optional[str]]] = []
                for r, pn in pr_targets:
                    key = (r, pn)
                    if key not in pr_cache:
                        pr_cache[key] = storage.load(pn, repo=r)
                    m = pr_cache[key]
                    title_str = m.title if m else "—"
                    ticket = m.jira_ticket if m else None
                    ai_sum = _extract_ai_summary(m.ai_report, max_chars=200) if m and m.ai_report else None
                    entries.append((r, pn, title_str, ticket, ai_sum))
                if entries:
                    prs_by_epic[epic_key] = entries
        if prs_by_epic:
            total_prs = sum(len(v) for v in prs_by_epic.values())
            unique_prs = len(pr_cache)
            console.print(f"  [green]✓[/green] Found {total_prs} PR(s) ({unique_prs} unique) from storage for Implementation section")

    use_ai = getattr(args, "ai", False)

    if use_ai:
        from src.ai_reporter import synthesize_workflow_doc

        for epic_key, epic_issue, child_issues in workflows:
            children_data = [
                {
                    "key": c.key,
                    "summary": c.summary,
                    "description": c.description,
                    "issue_type": c.issue_type,
                    "status": c.status,
                }
                for c in child_issues
            ]
            pr_data = [
                {"repo": r, "pr_number": pn, "title": t, "ticket": tk, "ai_summary": ai}
                for r, pn, t, tk, ai in (prs_by_epic or {}).get(epic_key, [])
            ]
            with console.status(f"AI synthesizing workflow doc for [bold]{epic_key}[/bold]…"):
                md = synthesize_workflow_doc(
                    epic_key=epic_key,
                    epic_summary=epic_issue.summary if epic_issue else None,
                    epic_description=epic_issue.description if epic_issue else None,
                    children=children_data,
                    pr_summaries=pr_data,
                )
            if md:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(md, encoding="utf-8")
                console.print(f"[green]Wrote AI-synthesized workflow doc →[/green] {output_path}")
            else:
                console.print("[red]AI synthesis failed or AI not configured. Falling back to raw doc.[/red]")
                reporter = ReportGenerator()
                reporter.generate_workflow_doc(
                    workflows, output_path, title=title, intro=intro, prs_by_epic=prs_by_epic
                )
                console.print(f"[green]Wrote (raw) →[/green] {output_path}")
    else:
        reporter = ReportGenerator()
        reporter.generate_workflow_doc(
            workflows, output_path, title=title, intro=intro, prs_by_epic=prs_by_epic
        )
        console.print(f"[green]Wrote[/green] {output_path}")
    return 0


def cmd_regenerate_epic_report(args: argparse.Namespace) -> int:
    """Regenerate only the epic markdown report from stored metrics (no re-analysis)."""
    from src.report_generator import ReportGenerator
    from src.storage import create_storage

    epic_key = (getattr(args, "epic", "") or "").upper().strip()
    repo = getattr(args, "repo", "") or ""
    org = getattr(args, "org", "") or ""
    storage_backend = getattr(args, "storage", "json")
    scope = f"org:{org}" if org else repo

    if not epic_key:
        console.print("[red]--epic is required.[/red]")
        return 1

    console.rule(f"[bold blue]Regenerate Epic Report — {epic_key} @ {scope}")

    # ---- 1. Discover PRs (same as analyze_epic) ----------------------------
    with console.status("Discovering PRs for epic…"):
        pr_targets, epic_issue = _discover_epic_prs(epic_key, repo, org)

    if not pr_targets:
        console.print("[red]No PRs found for this epic. Check --repo/--org and Jira.[/red]")
        return 1

    console.print(f"[green]✓[/green] {len(pr_targets)} PRs linked to epic")

    # ---- 2. Load metrics from storage --------------------------------------
    storage = create_storage(storage_backend)
    all_stored = storage.load_all()
    pr_target_set = set(pr_targets)
    all_metrics = [m for m in all_stored if (m.repo, m.pr_number) in pr_target_set]

    missing = [(r, n) for r, n in pr_targets if (r, n) not in {(m.repo, m.pr_number) for m in all_metrics}]
    failed = len(missing)

    if not all_metrics:
        console.print(
            "[red]No stored metrics for any of the PRs. Run [bold]analyze_epic[/bold] first.[/red]"
        )
        return 1

    if missing:
        console.print(f"[yellow]Missing metrics for {len(missing)} PRs (will show as failed in report):[/yellow]")
        for r, n in missing[:10]:
            console.print(f"  [dim]#{n} {r}[/dim]")
        if len(missing) > 10:
            console.print(f"  [dim]… and {len(missing) - 10} more[/dim]")

    # ---- 3. Generate report ------------------------------------------------
    reporter = ReportGenerator()
    try:
        report_path = reporter.generate_epic_report(epic_key, epic_issue, all_metrics, failed)
        console.print(f"[green]✓[/green] Report written → [bold]{report_path}[/bold]")
    except Exception as exc:
        console.print(f"[red]Failed to write report:[/red] {exc}")
        return 1

    return 0


def _print_epic_summary(epic_key, epic_issue, all_metrics, failed: int) -> None:
    from src.report_generator import _score_badge

    total = len(all_metrics)
    avg_score = round(sum(m.testing_quality_score for m in all_metrics) / total, 2) if total else 0
    avg_cov = sum(m.change_coverage for m in all_metrics) / total if total else 0
    total_tests = sum(m.tests_added for m in all_metrics)
    badge = _score_badge(avg_score)

    summary_table = Table(box=box.ROUNDED, show_header=False, padding=(0, 1))
    summary_table.add_column("Key", style="bold cyan")
    summary_table.add_column("Value")

    summary_table.add_row("Epic", epic_key)
    if epic_issue and epic_issue.summary:
        summary_table.add_row("Summary", epic_issue.summary)
    summary_table.add_row("PRs analyzed", str(total))
    if failed:
        summary_table.add_row("PRs failed", f"[yellow]{failed}[/yellow]")
    summary_table.add_row("Avg Change Coverage", f"[bold green]{avg_cov * 100:.0f}%[/bold green]")
    summary_table.add_row(
        "Avg Testing Quality Score",
        f"[bold yellow]{avg_score} / 10[/bold yellow] ({badge})",
    )
    summary_table.add_row("Total tests added", str(total_tests))

    console.print(Panel(summary_table, title=f"[bold]Epic {epic_key}[/bold]", expand=False))

    # Per-PR breakdown table
    pr_table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    pr_table.add_column("PR", justify="right")
    pr_table.add_column("Repo")
    pr_table.add_column("Ticket")
    pr_table.add_column("Coverage", justify="right")
    pr_table.add_column("Score", justify="right")
    pr_table.add_column("Tests", justify="right")

    for m in sorted(all_metrics, key=lambda x: x.pr_number):
        cov = f"{m.change_coverage * 100:.0f}%"
        ticket = m.jira_ticket or "—"
        pr_table.add_row(
            f"#{m.pr_number}",
            m.repo,
            ticket,
            cov,
            str(m.testing_quality_score),
            str(m.tests_added),
        )

    console.print(pr_table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_since(value: str) -> int | None:
    """Parse '30d', '7d', etc. and return number of days."""
    match = re.fullmatch(r"(\d+)d", value.strip().lower())
    if not match:
        return None
    return int(match.group(1))


def _resolve_repos(repos_file: str, single_repo: str) -> list[str]:
    """Return the list of repositories to analyse.

    Priority: ``--repos`` YAML file > ``--repo`` single value.
    """
    if repos_file:
        return _load_repos_yaml(repos_file)
    if single_repo:
        return [single_repo]
    return []


def _load_repos_yaml(path: str) -> list[str]:
    """Parse a repos.yaml file and return the list of repo strings."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        console.print(
            "[red]PyYAML is required for --repos. Install it: pip install pyyaml[/red]"
        )
        return []
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        repos = data.get("repos", [])
        return [str(r) for r in repos if r]
    except Exception as exc:
        console.print(f"[red]Failed to load {path}:[/red] {exc}")
        return []


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _add_storage_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--storage",
        choices=["json", "sqlite"],
        default="json",
        help="Storage backend: 'json' (default) or 'sqlite'",
    )


def _add_cache_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cache",
        action="store_true",
        default=False,
        help="Cache GitHub API responses to disk (reduces rate-limit risk)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-analyzer",
        description="PR Testing Impact Analyzer",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze_change
    p_analyze = sub.add_parser("analyze_change", help="Analyze a single PR")
    p_analyze.add_argument("--repo", required=True, help="GitHub repo, e.g. org/project")
    p_analyze.add_argument("--pr", required=True, type=int, help="PR number")
    p_analyze.add_argument(
        "--repo-path",
        default="",
        help="Local path to repo clone for running coverage (optional)",
    )
    _add_storage_arg(p_analyze)
    _add_cache_arg(p_analyze)

    # pr_description_report
    p_desc = sub.add_parser(
        "pr_description_report",
        help="Print markdown report to paste into PR description",
    )
    p_desc.add_argument("--repo", required=True, help="GitHub repo, e.g. org/project")
    p_desc.add_argument("--pr", required=True, type=int, help="PR number")
    p_desc.add_argument(
        "--no-analyze",
        action="store_true",
        dest="no_run_analysis",
        help="Do not run analyze_pr if metrics missing; fail instead",
    )
    p_desc.set_defaults(run_analysis=True)
    _add_storage_arg(p_desc)

    # analyze_author
    p_author = sub.add_parser(
        "analyze_author", help="Analyze all merged PRs by a specific author"
    )
    scope_group = p_author.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--repo", help="Single repo, e.g. org/project")
    scope_group.add_argument("--org", help="GitHub org — scans ALL repos in the org")
    p_author.add_argument("--author", required=True, help="GitHub username")
    p_author.add_argument(
        "--since",
        default="30d",
        help="Time window, e.g. '30d' or '90d' (default: 30d)",
    )
    p_author.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max PRs to analyze (default: 200)",
    )
    _add_storage_arg(p_author)
    _add_cache_arg(p_author)

    # analyze_epic
    p_epic = sub.add_parser(
        "analyze_epic",
        help="Analyze all PRs linked to a Jira Epic",
    )
    p_epic.add_argument("--epic", required=True, help="Jira Epic key, e.g. CLOSE-1234")
    epic_scope = p_epic.add_mutually_exclusive_group(required=True)
    epic_scope.add_argument("--repo", help="Single GitHub repo, e.g. org/project")
    epic_scope.add_argument("--org", help="GitHub org — search across all repos")
    _add_storage_arg(p_epic)
    _add_cache_arg(p_epic)

    # regenerate_epic_report
    p_regen = sub.add_parser(
        "regenerate_epic_report",
        help="Regenerate epic markdown report from stored metrics (no re-analysis)",
    )
    p_regen.add_argument("--epic", required=True, help="Jira Epic key, e.g. CLOSE-1234")
    regen_scope = p_regen.add_mutually_exclusive_group(required=True)
    regen_scope.add_argument("--repo", help="Single GitHub repo, e.g. org/project")
    regen_scope.add_argument("--org", help="GitHub org — same scope as when you ran analyze_epic")
    _add_storage_arg(p_regen)

    # generate_workflow_docs
    p_wf = sub.add_parser(
        "generate_workflow_docs",
        help="Generate a single Markdown doc of core workflows (Jira Epics) in priority order",
    )
    p_wf.add_argument(
        "--epics",
        required=True,
        help="Comma-separated Epic keys, e.g. CLOSE-8615,OTHER-123",
    )
    wf_scope = p_wf.add_mutually_exclusive_group(required=False)
    wf_scope.add_argument("--repo", help="Single GitHub repo — discover PRs and add Implementation (PRs) from storage")
    wf_scope.add_argument("--org", help="GitHub org — discover PRs across repos and add Implementation (PRs) from storage")
    p_wf.add_argument(
        "--output",
        default="docs/core-workflows.md",
        help="Output path for the workflow doc (default: docs/core-workflows.md)",
    )
    p_wf.add_argument("--title", default="Core Workflows", help="Document title")
    p_wf.add_argument(
        "--intro",
        default="",
        help="Optional intro paragraph (replaces default)",
    )
    p_wf.add_argument(
        "--ai",
        action="store_true",
        help="Use AI to synthesize a user-story-based workflow doc (requires AI configured)",
    )
    _add_storage_arg(p_wf)

    # generate_summary
    p_summary = sub.add_parser("generate_summary", help="Generate aggregated team summary")
    repo_group = p_summary.add_mutually_exclusive_group(required=True)
    repo_group.add_argument("--repo", help="Single GitHub repo, e.g. org/project")
    repo_group.add_argument(
        "--repos", metavar="FILE", help="Path to repos.yaml for multi-repo analysis"
    )
    p_summary.add_argument(
        "--since",
        default="30d",
        help="Time window for the summary, e.g. '30d' (default: 30d)",
    )
    p_summary.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch and analyze merged PRs from GitHub before summarizing",
    )
    _add_storage_arg(p_summary)
    _add_cache_arg(p_summary)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze_change":
        return cmd_analyze_change(args)
    elif args.command == "pr_description_report":
        # --no-analyze sets no_run_analysis=True, so run_analysis = not args.no_run_analysis
        args.run_analysis = not getattr(args, "no_run_analysis", False)
        return cmd_pr_description_report(args)
    elif args.command == "analyze_author":
        return cmd_analyze_author(args)
    elif args.command == "analyze_epic":
        return cmd_analyze_epic(args)
    elif args.command == "regenerate_epic_report":
        return cmd_regenerate_epic_report(args)
    elif args.command == "generate_workflow_docs":
        return cmd_generate_workflow_docs(args)
    elif args.command == "generate_summary":
        return cmd_generate_summary(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
