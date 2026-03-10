from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.models import JiraIssue, PRMetrics, TeamSummary

REPORTS_DIR = Path("reports")


def _score_badge(score: float) -> str:
    """Return a short text badge for a testing quality score."""
    if score >= 8.0:
        return "Excellent"
    if score >= 6.0:
        return "Good"
    if score >= 4.0:
        return "Fair"
    return "Needs improvement"


def _coverage_for_display(m: PRMetrics) -> float:
    """Return coverage value 0.0–1.0 for reports: prefer AI estimate, fallback to mechanical."""
    if m.llm_estimated_coverage is not None:
        return m.llm_estimated_coverage
    return m.change_coverage


def _coverage_display_str(m: PRMetrics) -> str:
    """Return coverage as string for report (e.g. '85%' or '—'); uses AI estimate when available."""
    v = _coverage_for_display(m)
    if v == 0.0 and m.llm_estimated_coverage is None and m.change_coverage == 0.0:
        return "—"
    return f"{v * 100:.0f}%"


class ReportGenerator:
    """Generates Markdown and JSON reports for PRs and team summaries."""

    def __init__(self) -> None:
        REPORTS_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # PR report
    # ------------------------------------------------------------------

    def pr_description_snippet(self, metrics: PRMetrics) -> str:
        """Return a compact markdown block suitable for pasting into the PR description.

        Includes: testing quality badge, key metrics table, and AI analysis (if available).
        Use with get_pr_description_report or after analyze_pr to get this text for the PR body.
        """
        badge = _score_badge(metrics.testing_quality_score)
        cov_str = _coverage_display_str(metrics)
        score_line = (
            f"**{metrics.testing_quality_score:.1f} / 10** ({badge})"
            if metrics.has_testable_code
            else "N/A (config/i18n-only)"
        )
        lines = [
            "## Testing quality",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Quality score | {score_line} |",
            f"| Coverage (est.) | {cov_str} |",
            f"| Test/code ratio | {metrics.test_code_ratio:.2f} |",
            f"| Tests added | {metrics.tests_added} |",
            "",
        ]
        if metrics.ai_report:
            lines += ["### AI analysis", "", metrics.ai_report.strip(), ""]
        return "\n".join(lines).strip()

    def generate_pr_report(self, metrics: PRMetrics) -> tuple[Path, Path]:
        """Write PR report files and return ``(md_path, json_path)``."""
        md_path = REPORTS_DIR / f"pr_{metrics.pr_number}_report.md"
        json_path = REPORTS_DIR / f"pr_{metrics.pr_number}_metrics.json"

        md_path.write_text(self._pr_markdown(metrics), encoding="utf-8")
        json_path.write_text(
            json.dumps(self._pr_json(metrics), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return md_path, json_path

    # ------------------------------------------------------------------
    # Epic report
    # ------------------------------------------------------------------

    def generate_epic_report(
        self,
        epic_key: str,
        epic_issue: Optional[JiraIssue],
        all_metrics: list[PRMetrics],
        failed: int = 0,
    ) -> Path:
        """Write an epic summary report (markdown) and return the file path."""
        REPORTS_DIR.mkdir(exist_ok=True)
        md_path = REPORTS_DIR / f"epic_{epic_key}_report.md"
        md_path.write_text(
            self._epic_markdown(epic_key, epic_issue, all_metrics, failed),
            encoding="utf-8",
        )
        return md_path

    def _epic_markdown(
        self,
        epic_key: str,
        epic_issue: Optional[JiraIssue],
        all_metrics: list[PRMetrics],
        failed: int = 0,
    ) -> str:
        total = len(all_metrics)
        avg_score = round(sum(m.testing_quality_score for m in all_metrics) / total, 2) if total else 0.0
        # Use AI-estimated coverage only (no mechanical/CI); average across PRs that have it
        cov_values = [_coverage_for_display(m) for m in all_metrics]
        avg_cov = sum(cov_values) / total if total else 0.0
        total_tests = sum(m.tests_added for m in all_metrics)
        badge = _score_badge(avg_score)
        summary = epic_issue.summary if epic_issue else None

        lines = [
            f"# Epic {epic_key}",
            "",
            "## Resumen",
            "",
            "| Campo | Valor |",
            "|-------|--------|",
            f"| Epic | **{epic_key}** |",
            f"| Summary | {summary or '—'} |",
            f"| PRs analizados | {total} |",
        ]
        if failed:
            lines.append(f"| PRs fallidos | {failed} |")
        lines += [
            f"| Avg Coverage (AI estimate) | {avg_cov * 100:.0f}% |",
            f"| Avg Testing Quality Score | **{avg_score} / 10** ({badge}) |",
            f"| Total tests añadidos | {total_tests} |",
            "",
            "---",
            "",
            "## Tabla de PRs",
            "",
            "| PR | Repo | Ticket | Coverage (AI) | Score | Tests |",
            "|----|------|--------|---------------|-------|-------|",
        ]
        for m in sorted(all_metrics, key=lambda x: (x.repo, x.pr_number)):
            pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
            ticket = m.jira_ticket or "—"
            cov_str = _coverage_display_str(m)
            lines.append(
                f"| [#{m.pr_number}]({pr_url}) | {m.repo} | {ticket} | {cov_str} | {m.testing_quality_score} | {m.tests_added} |"
            )

        # Casos a mejorar: PRs con score bajo, sin tests, o cobertura preocupante
        needs_work = []
        for m in all_metrics:
            reasons = []
            if m.has_testable_code and m.tests_added == 0:
                reasons.append("sin tests añadidos (código testeable)")
            if m.testing_quality_score < 6.0:
                reasons.append("score bajo (< 6)")
            if _coverage_for_display(m) < 0.5 and m.has_testable_code:
                reasons.append("cobertura estimada baja")
            if reasons:
                needs_work.append((m, "; ".join(reasons)))

        if needs_work:
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## Casos a mejorar")
            lines.append("")
            lines.append("PRs que conviene revisar (tests, score o cobertura):")
            lines.append("")
            for m, reason in sorted(needs_work, key=lambda x: (x[0].repo, x[0].pr_number)):
                pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
                ticket = m.jira_ticket or "—"
                lines.append(f"- **[#{m.pr_number} {m.repo}]({pr_url})** — {ticket} — *{reason}*")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## Detalle por PR")
        lines.append("")
        for m in sorted(all_metrics, key=lambda x: (x.repo, x.pr_number)):
            pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
            ticket = m.jira_ticket or "—"
            cov_str = _coverage_display_str(m)
            detail_lines = [
                f"### [#{m.pr_number} {m.repo}]({pr_url})",
                "",
                f"- **Título:** {m.title}",
                f"- **Autor:** {m.author}",
                f"- **Ticket:** {ticket}",
                f"- **Score:** {m.testing_quality_score} / 10 · **Coverage (AI):** {cov_str} · **Tests añadidos:** {m.tests_added}",
            ]
            if m.has_testable_code and m.tests_added == 0:
                detail_lines.append("- ⚠️ Sin tests añadidos para código testeable.")
            if m.testing_quality_score < 6.0:
                detail_lines.append("- ⚠️ Score bajo: revisar calidad o cobertura de tests.")
            if _coverage_for_display(m) < 0.5 and m.has_testable_code:
                detail_lines.append("- ⚠️ Cobertura estimada baja.")
            detail_lines.append("")
            lines.extend(detail_lines)
        return "\n".join(lines).replace("\n\n\n", "\n\n")

    def _pr_markdown(self, m: PRMetrics) -> str:
        change_cov_pct = f"{m.change_coverage * 100:.0f}%"
        ticket = m.jira_ticket or "—"
        date_str = m.pr_date.strftime("%Y-%m-%d") if m.pr_date else "—"
        types = m.test_types
        badge = _score_badge(m.testing_quality_score)

        pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
        lines = [
            f"# [PR #{m.pr_number}]({pr_url})",
            "",
            f"**Author:** {m.author}  ",
            f"**Date:** {date_str}  ",
            f"**Ticket:** {ticket}  ",
            f"**Repository:** {m.repo}",
            "",
        ]

        # Jira metadata block (only when available)
        if m.jira_issue:
            ji = m.jira_issue
            try:
                from src.config import settings
                jira_base = settings.jira_url.rstrip("/")
                jira_url = f"{jira_base}/browse/{ji.key}" if jira_base else ji.key
            except Exception:
                jira_url = ji.key
            lines += [
                "## Jira Issue",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| Key | [{ji.key}]({jira_url}) |",
                f"| Summary | {ji.summary or '—'} |",
                f"| Type | {ji.issue_type or '—'} |",
                f"| Status | {ji.status or '—'} |",
                f"| Priority | {ji.priority or '—'} |",
            ]
            if ji.components:
                lines.append(f"| Components | {', '.join(ji.components)} |")
            if ji.labels:
                lines.append(f"| Labels | {', '.join(ji.labels)} |")
            lines.append("")

        # Score display — N/A for config/i18n-only PRs
        if not m.has_testable_code:
            score_line = "| **Testing Quality Score** | **N/A** _(config/i18n-only PR)_ |"
        else:
            score_line = f"| **Testing Quality Score** | **{m.testing_quality_score} / 10** ({badge}) |"

        pairing_pct = f"{m.test_file_pairing_rate * 100:.0f}%"
        assertion_note = f"{m.assertion_count} lines"

        lines += [
            "---",
            "",
            "## Quality Score",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            score_line,
            f"| Test / Code ratio | {m.test_code_ratio:.2f} |",
            f"| Test file pairing | {pairing_pct} _(prod files with a test counterpart)_ |",
            f"| Assertion lines | {assertion_note} |",
            "",
            "## Code Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Files changed | {m.files_changed} |",
            f"| Production lines added | {m.production_lines_added} |",
            f"| Production lines modified | {m.production_lines_modified} |",
            f"| Test lines added | {m.test_lines_added} |",
            "",
            "## Coverage Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Changed lines | {m.lines_modified} |",
            f"| Covered changed lines | {m.lines_covered} |",
            f"| **Change Coverage** | **{change_cov_pct}** |",
        ]

        if m.overall_coverage is not None:
            lines.append(f"| Overall repo coverage | {m.overall_coverage:.1f}% |")

        if m.ai_estimated_coverage is not None:
            ai_cov_pct = f"{m.ai_estimated_coverage * 100:.0f}%"
            note = " _(no CI data)_" if m.change_coverage == 0.0 else ""
            lines.append(f"| Diff-estimated coverage | {ai_cov_pct}{note} |")

        if m.llm_estimated_coverage is not None:
            llm_pct = f"{m.llm_estimated_coverage * 100:.0f}%"
            lines.append(
                f"| AI-estimated coverage | **{llm_pct}** "
                "_(LLM inference from diffs — not CI data)_ |"
            )

        # Show which branch of the quality score formula was used
        if m.has_testable_code:
            if m.change_coverage > 0.0:
                lines.append("| Score basis | Real CI coverage |")
            elif m.ai_estimated_coverage is not None:
                if m.is_modification_only:
                    lines.append(
                        "| Score basis | Diff heuristic + ratio + pairing "
                        "_(modification-only: existing test coverage not visible without CI)_ |"
                    )
                else:
                    lines.append("| Score basis | Diff heuristic + ratio + pairing |")
            elif m.test_lines_added > 0:
                lines.append("| Score basis | Ratio + pairing _(no coverage data)_ |")
            elif m.is_modification_only:
                lines.append(
                    "| Score basis | ⚠️ Modification-only PR — "
                    "coverage of changed lines requires CI instrumentation |"
                )
            else:
                lines.append("| Score basis | No tests |")

        lines += [
            "",
            "## Test Breakdown",
            "",
            f"| Test files touched | {m.tests_added} |",
            "|--------------------|---|",
        ]

        if types.total() == 0:
            lines.append("")
            lines.append("_No tests detected in this PR._")
        else:
            if types.unit:
                lines.append(f"| unit | {types.unit} |")
            if types.integration:
                lines.append(f"| integration | {types.integration} |")
            if types.e2e:
                lines.append(f"| e2e | {types.e2e} |")
            if types.unknown:
                lines.append(f"| other | {types.unknown} |")

        lines += [
            "",
            "## Files Changed",
            "",
            "| File | Status | Lines Modified |",
            "|------|--------|---------------|",
        ]
        for fc in m.file_changes:
            lines.append(f"| `{fc.filename}` | {fc.status} | {len(fc.modified_lines)} |")

        if m.test_files:
            lines += [
                "",
                "## Test Files",
                "",
                "| File | Type | New? | Lines Added |",
                "|------|------|------|-------------|",
            ]
            for tf in m.test_files:
                new_label = "yes" if tf.is_new else "no"
                lines.append(
                    f"| `{tf.filename}` | {tf.test_type.value} | {new_label} | {tf.lines_added} |"
                )

        # Ollama AI report section (only when available)
        if m.ai_report:
            lines += [
                "",
                "---",
                "",
                "## AI Testing Quality Analysis",
                "",
                m.ai_report,
            ]

        lines.append("")
        return "\n".join(lines)

    def _pr_json(self, m: PRMetrics) -> dict:
        jira_data = None
        if m.jira_issue:
            ji = m.jira_issue
            jira_data = {
                "key": ji.key,
                "summary": ji.summary,
                "issue_type": ji.issue_type,
                "status": ji.status,
                "priority": ji.priority,
                "components": ji.components,
                "labels": ji.labels,
            }

        return {
            "pr_number": m.pr_number,
            "author": m.author,
            "title": m.title,
            "date": m.pr_date.isoformat() if m.pr_date else None,
            "repo": m.repo,
            "jira_ticket": m.jira_ticket,
            "jira_issue": jira_data,
            "quality": {
                "testing_quality_score": m.testing_quality_score if m.has_testable_code else None,
                "badge": _score_badge(m.testing_quality_score) if m.has_testable_code else "N/A",
                "has_testable_code": m.has_testable_code,
                "test_code_ratio": round(m.test_code_ratio, 3),
                "test_file_pairing_rate": round(m.test_file_pairing_rate, 3),
                "assertion_count": m.assertion_count,
            },
            "code_metrics": {
                "files_changed": m.files_changed,
                "production_lines_added": m.production_lines_added,
                "production_lines_modified": m.production_lines_modified,
                "test_lines_added": m.test_lines_added,
            },
            "coverage_metrics": {
                "changed_lines": m.lines_modified,
                "covered_changed_lines": m.lines_covered,
                "change_coverage_pct": round(m.change_coverage * 100, 2),
                "overall_coverage_pct": (
                    round(m.overall_coverage, 2) if m.overall_coverage is not None else None
                ),
                "ai_estimated_coverage_pct": (
                    round(m.ai_estimated_coverage * 100, 2)
                    if m.ai_estimated_coverage is not None else None
                ),
                "llm_estimated_coverage_pct": (
                    round(m.llm_estimated_coverage * 100, 2)
                    if m.llm_estimated_coverage is not None else None
                ),
            },
            "test_metrics": {
                "tests_added": m.tests_added,
                "test_types": {
                    "unit": m.test_types.unit,
                    "integration": m.test_types.integration,
                    "e2e": m.test_types.e2e,
                    "unknown": m.test_types.unknown,
                },
            },
            "ai_report": m.ai_report,
        }

    # ------------------------------------------------------------------
    # Team summary report
    # ------------------------------------------------------------------

    def generate_summary_report(self, summary: TeamSummary) -> tuple[Path, Path]:
        """Write summary report files and return ``(md_path, json_path)``."""
        md_path = REPORTS_DIR / "team_summary.md"
        json_path = REPORTS_DIR / "team_summary.json"

        md_path.write_text(self._summary_markdown(summary), encoding="utf-8")
        json_path.write_text(
            json.dumps(self._summary_json(summary), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return md_path, json_path

    def _summary_markdown(self, s: TeamSummary) -> str:
        coverage_pct = f"{s.average_change_coverage * 100:.0f}%"
        period = f"Last {s.since_days} days" if s.since_days else "All time"

        # Repo label: single repo or comma-separated list
        repo_label = s.repo if len(s.repos) <= 1 else ", ".join(sorted(s.repos))

        lines = [
            "# Testing Summary",
            "",
            f"**Repository:** {repo_label}  ",
            f"**Period:** {period}",
            "",
            "---",
            "",
            "## Overview",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| PRs analyzed | {s.prs_analyzed} |",
            f"| Average Change Coverage | **{coverage_pct}** |",
            f"| Avg Testing Quality Score | **{s.average_testing_quality_score} / 10** |",
            f"| Total tests added | {s.total_tests_added} |",
            "",
            "## Test Type Distribution",
            "",
        ]

        if not s.test_type_distribution:
            lines.append("_No test data available._")
        else:
            for test_type, fraction in sorted(s.test_type_distribution.items()):
                pct = f"{fraction * 100:.0f}%"
                lines.append(f"- {test_type}: {pct}")

        # Multi-repo breakdown (only shown when more than one repo)
        if len(s.repos) > 1 and s.by_repo:
            lines += [
                "",
                "## Breakdown by Repository",
                "",
                "| Repository | PRs | Avg Coverage | Avg Quality Score | Tests Added |",
                "|------------|-----|--------------|-------------------|-------------|",
            ]
            for repo_name, stats in sorted(s.by_repo.items()):
                lines.append(
                    f"| {repo_name} | {stats['prs']} | {stats['avg_change_coverage_pct']}%"
                    f" | {stats['avg_testing_quality_score']} | {stats['tests_added']} |"
                )

        # Top contributors
        if s.top_contributors:
            lines += [
                "",
                "## Top Contributors",
                "",
                "| Author | PRs | Avg Change Coverage | Avg Quality Score | Tests Added |",
                "|--------|-----|---------------------|-------------------|-------------|",
            ]
            for c in s.top_contributors[:10]:
                lines.append(
                    f"| {c['author']} | {c['prs']} | {c['avg_change_coverage']}%"
                    f" | {c['avg_testing_quality_score']} | {c['tests_added']} |"
                )

        # Breakdown by Jira issue type
        if s.by_issue_type:
            lines += [
                "",
                "## Breakdown by Issue Type",
                "",
                "| Issue Type | PRs |",
                "|------------|-----|",
            ]
            for issue_type, count in sorted(s.by_issue_type.items(), key=lambda x: -x[1]):
                lines.append(f"| {issue_type} | {count} |")

        # Per-author stats
        if s.by_author:
            lines += [
                "",
                "## Per-Author Stats",
                "",
                "| Author | PRs | Avg Coverage | Avg Quality | Tests Added | Lines Modified |",
                "|--------|-----|--------------|-------------|-------------|----------------|",
            ]
            for author, stats in sorted(
                s.by_author.items(), key=lambda x: x[1].prs, reverse=True
            ):
                cov = f"{stats.avg_change_coverage * 100:.0f}%"
                lines.append(
                    f"| {author} | {stats.prs} | {cov} | {stats.avg_testing_quality_score}"
                    f" | {stats.tests_added} | {stats.lines_modified} |"
                )

        # Per-PR breakdown
        if s.pr_metrics:
            lines += [
                "",
                "## Per-PR Breakdown",
                "",
                "| PR | Repo | Author | Ticket | Type | Lines Modified | Change Coverage | Quality | Tests Added |",
                "|----|------|--------|--------|------|---------------|-----------------|---------|-------------|",
            ]
            for m in sorted(s.pr_metrics, key=lambda x: x.pr_number):
                ticket = m.jira_ticket or "—"
                issue_type = (
                    m.jira_issue.issue_type if m.jira_issue and m.jira_issue.issue_type else "—"
                )
                cov = f"{m.change_coverage * 100:.0f}%"
                pr_link = f"[#{m.pr_number}](https://github.com/{m.repo}/pull/{m.pr_number})"
                lines.append(
                    f"| {pr_link} | {m.repo} | {m.author} | {ticket} | {issue_type}"
                    f" | {m.lines_modified} | {cov} | {m.testing_quality_score} | {m.tests_added} |"
                )

        lines.append("")
        return "\n".join(lines)

    def _summary_json(self, s: TeamSummary) -> dict:
        return {
            "repo": s.repo,
            "repos": s.repos,
            "since_days": s.since_days,
            "prs_analyzed": s.prs_analyzed,
            "average_change_coverage_pct": round(s.average_change_coverage * 100, 2),
            "average_testing_quality_score": s.average_testing_quality_score,
            "total_tests_added": s.total_tests_added,
            "test_type_distribution": {
                k: round(v * 100, 2) for k, v in s.test_type_distribution.items()
            },
            "top_contributors": s.top_contributors[:10],
            "by_issue_type": s.by_issue_type,
            "by_repo": s.by_repo,
            "coverage_trend": s.coverage_trend,
            "by_author": {
                author: {
                    "prs": stats.prs,
                    "avg_change_coverage_pct": round(stats.avg_change_coverage * 100, 2),
                    "avg_testing_quality_score": stats.avg_testing_quality_score,
                    "tests_added": stats.tests_added,
                    "lines_modified": stats.lines_modified,
                }
                for author, stats in s.by_author.items()
            },
            "prs": [
                {
                    "pr_number": m.pr_number,
                    "repo": m.repo,
                    "author": m.author,
                    "date": m.pr_date.isoformat() if m.pr_date else None,
                    "jira_ticket": m.jira_ticket,
                    "jira_issue_type": (
                        m.jira_issue.issue_type
                        if m.jira_issue and m.jira_issue.issue_type
                        else None
                    ),
                    "lines_modified": m.lines_modified,
                    "change_coverage_pct": round(m.change_coverage * 100, 2),
                    "testing_quality_score": m.testing_quality_score,
                    "tests_added": m.tests_added,
                }
                for m in sorted(s.pr_metrics, key=lambda x: x.pr_number)
            ],
        }
