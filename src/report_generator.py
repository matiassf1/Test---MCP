from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.models import JiraIssue, PRMetrics, TeamSummary

REPORTS_DIR = Path("reports")

# For workflow doc: sort Epics by Jira priority (most important first)
_WORKFLOW_PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
# Within an Epic: principal workflows first (Story = main flow, Task/Bug = supporting).
# Covers common Jira type variants. Configurable via WORKFLOW_TYPE_ORDER env var (comma-sep).
import os as _os
_DEFAULT_CHILD_TYPE_ORDER = ["Story", "Task", "Sub-task", "Subtask", "Sub-Task", "Bug"]
_env_order = _os.environ.get("WORKFLOW_TYPE_ORDER", "")
_CHILD_TYPE_ORDER: dict[str, int] = {
    t.strip(): i
    for i, t in enumerate(
        _env_order.split(",") if _env_order.strip() else _DEFAULT_CHILD_TYPE_ORDER
    )
    if t.strip()
}


def _score_badge(score: float) -> str:
    """Return a short text badge for a testing quality score."""
    if score >= 8.0:
        return "Excellent"
    if score >= 6.0:
        return "Good"
    if score >= 4.0:
        return "Fair"
    return "Needs improvement"


def _score_display(m: PRMetrics) -> str:
    """Return score for display: 'Contract-only' when N/A, else the numeric score."""
    if getattr(m, "is_contract_only", False):
        return "Contract-only"
    return str(m.testing_quality_score)


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


def _sanitize_score_in_text(text: str, actual_score: float) -> str:
    """Replace misleading '10' or '10.00' or 'perfect score' in AI narrative with actual score when actual_score is not 10."""
    if not text or actual_score >= 9.99:
        return text
    score_str = f"{actual_score:.2f}"
    # "10.00" (standalone) -> actual score
    text = re.sub(r"\b10\.00\b", score_str, text)
    # "10/10" -> "9.30/10"
    text = re.sub(r"\b10/10\b", f"{score_str}/10", text)
    # "Score of 10" or "score of 10.00" -> score of 9.30 (use \g<1> so next digit isn't taken as group ref)
    text = re.sub(r"([Ss]core\s+of)\s+10(\.00)?\b", r"\g<1> " + score_str, text)
    # "Testing Quality Score 10" or "Quality Score of 10"
    text = re.sub(r"(Testing\s+Quality\s+[Ss]core\s+of?)\s*10(\.00)?\b", r"\g<1> " + score_str, text)
    # "perfect precomputed ... 10.00" -> remove "perfect", use actual score (\g<N> avoids \29 when score is 9.xx)
    text = re.sub(
        r"perfect\s+(precomputed\s+)?(Testing\s+Quality\s+[Ss]core\s+of?\s*)10(\.00)?\b",
        r"\g<1>\g<2>" + score_str,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"precomputed\s+Testing\s+Quality\s+[Ss]core\s+of\s+10\.00", f"precomputed Testing Quality Score of {score_str}", text)
    return text


# ---------------------------------------------------------------------------
# Robust AI-report section extraction (survives renumbering, e.g. ### 3. → ### 4.)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{2,3}\s+(?:\d+\.\s*)?(.+)$", re.MULTILINE)


def _find_section(text: str, keywords: list[str]) -> Optional[str]:
    """Find the body of a section whose heading contains ALL given keywords (case-insensitive).

    Returns the text between the matching heading and the next heading of equal or higher level,
    stripped and collapsed to a single string.
    """
    matches = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        heading_text = m.group(1).lower()
        if all(k in heading_text for k in keywords):
            start = m.end()
            level = m.group(0).count("#", 0, m.group(0).index(" "))
            end = len(text)
            for j in range(i + 1, len(matches)):
                next_level = matches[j].group(0).count("#", 0, matches[j].group(0).index(" "))
                if next_level <= level:
                    end = matches[j].start()
                    break
            return text[start:end].strip()
    return None


def _extract_ai_summary(ai_report: Optional[str], max_chars: int = 320) -> Optional[str]:
    """Extract the Summary section from an AI audit report."""
    if not ai_report or not ai_report.strip():
        return None
    text = ai_report.strip()
    body = _find_section(text, ["summary"])
    if body:
        summary = body.replace("\n", " ").strip()
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3].rsplit(" ", 1)[0] + "..."
        return summary
    # Fallback: first non-empty paragraph
    for para in text.split("\n\n"):
        para = para.strip()
        if para and not para.startswith("#") and not para.startswith("|"):
            para = para.replace("\n", " ").strip()
            if len(para) > max_chars:
                para = para[: max_chars - 3].rsplit(" ", 1)[0] + "..."
            return para
    return None


def _extract_ai_recommendations(ai_report: Optional[str], max_bullets: int = 4) -> list[str]:
    """Extract recommendation bullets from the Testing Recommendations section.

    Handles multi-level bullets: when a top-level ``- `` has indented sub-items
    (``  - ``), they are collapsed into a single string separated by "; ".
    """
    if not ai_report or not ai_report.strip():
        return []
    body = _find_section(ai_report, ["testing", "recommendation"])
    if body is None:
        body = _find_section(ai_report, ["recommendation"])
    if body is None:
        return []

    raw_lines = body.splitlines()
    bullets: list[str] = []
    current: list[str] = []

    def _flush() -> None:
        if not current:
            return
        merged = " ".join(current)
        if merged.startswith("**"):
            i = merged.find("**", 2)
            if i > 0:
                merged = merged[i + 2:].lstrip()
        if merged and len(merged) > 10:
            bullets.append(merged)

    for raw in raw_lines:
        stripped = raw.strip()
        is_top = raw.startswith("- ") or (not raw.startswith(" ") and stripped.startswith("- "))
        is_sub = not is_top and stripped.startswith("- ")
        if is_top:
            _flush()
            if len(bullets) >= max_bullets:
                break
            current = [stripped[2:].strip()]
        elif is_sub and current:
            current.append(stripped[2:].strip())
        elif stripped and current:
            current.append(stripped)

    if len(bullets) < max_bullets:
        _flush()

    return bullets[:max_bullets]


def _extract_scope_alignment(ai_report: Optional[str], max_chars: int = 800) -> Optional[str]:
    """Extract the Scope vs ticket section from an AI audit report."""
    if not ai_report or not ai_report.strip():
        return None
    body = _find_section(ai_report, ["scope"])
    if body is None:
        return None
    one = body.replace("\n", " ").strip()
    if not one:
        return None
    if len(one) > max_chars:
        one = one[: max_chars - 3].rsplit(" ", 1)[0] + "..."
    return one


def _scope_status(scope_text: Optional[str]) -> str:
    """Classify scope alignment: 'aligned' | 'partial' | 'issues' | 'no_ticket' | 'unknown'.

    Criteria (relaxed):
    - 'issues' = PR does something **contradictory** to the ticket (different intent, wrong approach).
    - 'partial' = PR is mostly aligned but adds unrelated extras (bugfixes, refactors) — fine, just noted.
    - 'aligned' = PR implements what the ticket asks, possibly with useful extras.

    The AI often uses "Out of scope:" / "Different from spec:" as template headings even when
    the content says "no unrelated changes" or "aligns with the scope". We parse the text
    after those phrases to avoid false positives.
    """
    if not scope_text or not scope_text.strip():
        return "unknown"
    lower = scope_text.lower()
    if "cannot assess" in lower or "no ticket context" in lower:
        return "no_ticket"

    _NEGATION_PHRASES = (
        "no unrelated", "no out-of-scope", "no scope creep",
        "no significant deviation", "aligns with", "aligned with",
        "no obvious", "none", "n/a", "not applicable",
        "no deviation", "no extra", "without scope creep",
    )

    def _phrase_is_negated(phrase: str) -> bool:
        """Check if the text following a heading phrase negates it (i.e. says 'nothing here')."""
        idx = lower.find(phrase)
        if idx < 0:
            return False
        after = lower[idx + len(phrase) : idx + len(phrase) + 200]
        return any(neg in after for neg in _NEGATION_PHRASES)

    has_contradicts = "contradicts" in lower or "contrary to" in lower or "opposite of" in lower
    if has_contradicts:
        return "issues"

    has_diff = "different from spec" in lower or "different from the spec" in lower
    if has_diff and not _phrase_is_negated("different from spec") and not _phrase_is_negated("different from the spec"):
        if "aligned" not in lower:
            return "issues"

    has_out = "out of scope" in lower or "out-of-scope" in lower
    out_negated = _phrase_is_negated("out of scope") or _phrase_is_negated("out-of-scope")

    if has_out and not out_negated and "aligned" not in lower:
        return "partial"

    if "aligned" in lower or "aligns" in lower:
        return "aligned"

    # If text discusses implementation details without flagging issues, treat as aligned
    _POSITIVE_SIGNALS = (
        "implements", "directly addresses", "correctly", "precisely",
        "matches the scope", "consistent with", "as described", "as specified",
        "no scope creep", "no unrelated", "without scope creep",
    )
    if any(sig in lower for sig in _POSITIVE_SIGNALS):
        return "aligned"

    return "unknown"


def workflow_doc_markdown(
    workflows: list[tuple[str, Optional[JiraIssue], list[JiraIssue]]],
    title: str = "Core Workflows",
    intro: Optional[str] = None,
    prs_by_epic: Optional[dict[str, list[tuple[str, int, str, Optional[str], Optional[str]]]]] = None,
) -> str:
    """Build a single Markdown doc for core workflows (Epics), ordered by priority.

    Each item in workflows is (epic_key, epic_issue, child_issues). Epic issue and
    children come from Jira (fetch_issue + fetch_epic_issues). Sorts by Epic
    priority (Critical first) then by epic_key.
    prs_by_epic: optional map epic_key -> list of (repo, pr_number, title, jira_ticket, ai_summary).
    """
    def sort_key(item: tuple[str, Optional[JiraIssue], list[JiraIssue]]) -> tuple[int, str]:
        _, epic, _ = item
        p = epic.priority if epic and epic.priority else None
        order = _WORKFLOW_PRIORITY_ORDER.get(p, 4)
        return (order, item[0])

    sorted_workflows = sorted(workflows, key=sort_key)
    lines = [
        f"# {title}",
        "",
        intro or "Workflows (Jira Epics) in priority order. Each section describes the Epic and its child tickets.",
        "",
        "---",
        "",
    ]
    for epic_key, epic_issue, child_issues in sorted_workflows:
        summary = epic_issue.summary if epic_issue else "—"
        priority = f" ({epic_issue.priority})" if epic_issue and epic_issue.priority else ""
        lines.append(f"## {epic_key} — {summary}{priority}")
        lines.append("")
        if epic_issue and epic_issue.description:
            lines.append(epic_issue.description.strip())
            lines.append("")
        lines.append("### Child tickets (core workflows)")
        lines.append("")
        if not child_issues:
            lines.append("_No child issues found._")
        else:
            # Principal workflows first: Story → Task → Bug → other (easy to interpret)
            def _child_sort_key(issue: JiraIssue) -> tuple[int, str]:
                t = (issue.issue_type or "").strip()
                order = _CHILD_TYPE_ORDER.get(t, len(_CHILD_TYPE_ORDER))
                return (order, issue.key)
            ordered = sorted(child_issues, key=_child_sort_key)
            lines.append("_Stories = main flows; Tasks/Bugs = supporting. Descriptions below complete the picture from the Epic._")
            lines.append("")
            # Build ticket→PRs lookup for linking
            ticket_prs: dict[str, list[tuple[str, int]]] = {}
            if prs_by_epic and epic_key in prs_by_epic:
                for _r, _pn, _t, _tk, _ai in (prs_by_epic.get(epic_key) or []):
                    if _tk:
                        ticket_prs.setdefault(_tk, []).append((_r, _pn))

            lines.append("| Key | Summary | Type | Status | PRs | Description (excerpt) |")
            lines.append("|-----|---------|------|--------|-----|------------------------|")
            for c in ordered:
                desc_excerpt = (c.description or "").strip()
                if len(desc_excerpt) > 200:
                    desc_excerpt = desc_excerpt[:197].rsplit(" ", 1)[0] + "..."
                desc_cell = (desc_excerpt or "—").replace("|", "\\|").replace("\n", " ")
                linked = ticket_prs.get(c.key, [])
                pr_links = ", ".join(f"[#{pn}](https://github.com/{r}/pull/{pn})" for r, pn in linked) if linked else "—"
                lines.append(f"| {c.key} | {c.summary or '—'} | {c.issue_type or '—'} | {c.status or '—'} | {pr_links} | {desc_cell} |")
            # Full descriptions for tickets that have one (so doc is self-contained)
            with_desc = [c for c in ordered if (c.description or "").strip()]
            if with_desc:
                lines.append("")
                lines.append("#### Ticket descriptions")
                lines.append("")
                for c in with_desc:
                    lines.append(f"**{c.key}** — {c.summary or c.key}")
                    lines.append("")
                    lines.append((c.description or "").strip())
                    lines.append("")
        # Implementation (PRs) — grouped by ticket when available
        if prs_by_epic and epic_key in prs_by_epic:
            pr_list = prs_by_epic.get(epic_key) or []
            if pr_list:
                # Group by ticket (ticket → list of PRs), then "—" for unlinked
                from collections import OrderedDict
                grouped: OrderedDict[str, list[tuple[str, int, str, Optional[str], Optional[str]]]] = OrderedDict()
                for entry in sorted(pr_list, key=lambda e: (e[3] or "~", e[0], e[1])):
                    key = entry[3] or "—"
                    grouped.setdefault(key, []).append(entry)
                lines.append("")
                lines.append("#### Implementation (PRs)")
                lines.append("")
                lines.append("| Ticket | PR | Repo | Title | AI summary |")
                lines.append("|--------|----|------|-------|-------------|")
                for tk, entries in grouped.items():
                    first = True
                    for repo, pr_number, pr_title, ticket, ai_sum in entries:
                        pr_url = f"https://github.com/{repo}/pull/{pr_number}"
                        title_cell = ((pr_title or "")[:80] + ("..." if len(pr_title or "") > 80 else "")).replace("|", "\\|").replace("\n", " ")
                        ai_cell = ((ai_sum or "—")[:100]).replace("|", "\\|").replace("\n", " ")
                        tk_cell = f"**{tk}**" if first else ""
                        first = False
                        lines.append(f"| {tk_cell} | [#{pr_number}]({pr_url}) | {repo} | {title_cell} | {ai_cell} |")
                lines.append("")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines).replace("\n\n\n", "\n\n")


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
    # Workflow docs (core workflows from Jira Epics)
    # ------------------------------------------------------------------

    def generate_workflow_doc(
        self,
        workflows: list[tuple[str, Optional[JiraIssue], list[JiraIssue]]],
        output_path: Path,
        title: str = "Core Workflows",
        intro: Optional[str] = None,
        prs_by_epic: Optional[dict[str, list[tuple[str, int, str, Optional[str], Optional[str]]]]] = None,
    ) -> Path:
        """Write a single Markdown doc listing workflows (Epics) in priority order.
        Each workflow section includes Epic summary, description, child tickets, and optionally PRs (repo, number, title, ticket, ai_summary).
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        md = workflow_doc_markdown(workflows, title=title, intro=intro, prs_by_epic=prs_by_epic)
        output_path.write_text(md, encoding="utf-8")
        return output_path

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
        scored = [m for m in all_metrics if not getattr(m, "is_contract_only", False)]
        scored_n = len(scored) or 1
        avg_score = round(sum(m.testing_quality_score for m in scored) / scored_n, 2)
        # Use AI-estimated coverage only (no mechanical/CI); average across PRs that have it
        cov_values = [_coverage_for_display(m) for m in all_metrics]
        avg_cov = sum(cov_values) / total if total else 0.0
        total_tests = sum(m.tests_added for m in all_metrics)
        badge = _score_badge(avg_score)
        summary = epic_issue.summary if epic_issue else None

        # Well-covered: score >= 8 and (coverage >= 85% or config-only)
        well_covered = [
            m
            for m in all_metrics
            if m.testing_quality_score >= 8.0
            and (_coverage_for_display(m) >= 0.85 or not m.has_testable_code)
        ]
        needs_work = []
        for m in all_metrics:
            reasons = []
            is_contract = getattr(m, "is_contract_only", False)
            if not is_contract and m.has_testable_code and m.tests_added == 0:
                reasons.append("no tests added (testable code)")
            if not is_contract and m.testing_quality_score < 6.0:
                reasons.append("low score (< 6)")
            if _coverage_for_display(m) < 0.5 and m.has_testable_code and not is_contract:
                reasons.append("low estimated coverage")
            scope_raw = _extract_scope_alignment(m.ai_report)
            scope_s = _scope_status(scope_raw) if scope_raw else "unknown"
            if scope_s == "issues":
                reasons.append("scope concerns (contradicts ticket intent)")
            if reasons:
                needs_work.append((m, "; ".join(reasons)))

        lines = [
            f"# Epic {epic_key}",
            "",
            "## Summary",
            "",
            "| Field | Value |",
            "|-------|--------|",
            f"| Epic | **{epic_key}** |",
            f"| Summary | {summary or '—'} |",
            f"| PRs analyzed | {total} |",
        ]
        if failed:
            lines.append(f"| PRs failed | {failed} |")
        lines += [
            f"| Avg Coverage (AI estimate) | {avg_cov * 100:.0f}% |",
            f"| Avg Testing Quality Score | **{avg_score} / 10** ({badge}) |",
            f"| Total tests added | {total_tests} |",
            "",
            "---",
            "",
            "## PR Table",
            "",
            "| PR | Repo | Ticket | Coverage (AI) | Score | Tests |",
            "|----|------|--------|---------------|-------|-------|",
        ]
        for m in sorted(all_metrics, key=lambda x: (x.repo, x.pr_number)):
            pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
            ticket = m.jira_ticket or "—"
            cov_str = _coverage_display_str(m)
            score_str = _score_display(m)
            lines.append(
                f"| [#{m.pr_number}]({pr_url}) | {m.repo} | {ticket} | {cov_str} | {score_str} | {m.tests_added} |"
            )

        # Scope alignment overview (from each PR's "Scope vs ticket" AI section)
        scope_data = []
        scope_concerns = []
        for m in all_metrics:
            raw = _extract_scope_alignment(m.ai_report)
            status = _scope_status(raw) if raw else "unknown"
            scope_data.append((m, raw, status))
            if status == "issues" and raw:
                scope_concerns.append((m, raw))
        if scope_data:
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## Scope alignment overview")
            lines.append("")
            lines.append("Comparison of each PR to its Jira ticket. **Issues** = PR contradicts the ticket intent. **Partial** = aligned with useful extras (bugfixes, refactors).")
            lines.append("")
            lines.append("| PR | Ticket | Scope |")
            lines.append("|----|--------|-------|")
            for m, raw, status in sorted(scope_data, key=lambda x: (x[0].repo, x[0].pr_number)):
                pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
                ticket = m.jira_ticket or "—"
                _SCOPE_CELLS = {
                    "aligned": "✅ Aligned",
                    "partial": "🔶 Partial",
                    "issues": "⚠️ Issues",
                    "no_ticket": "— No ticket context",
                }
                cell = _SCOPE_CELLS.get(status, "—")
                lines.append(f"| [#{m.pr_number}]({pr_url}) | {ticket} | {cell} |")
            if scope_concerns:
                lines.append("")
                lines.append("### Scope concerns (review recommended)")
                lines.append("")
                for m, raw in sorted(scope_concerns, key=lambda x: (x[0].repo, x[0].pr_number)):
                    pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
                    ticket = m.jira_ticket or "—"
                    lines.append(f"- **[{ticket}]({pr_url})** — #{m.pr_number} {m.repo}")
                    lines.append(f"  {raw}")
                    lines.append("")

        # Well-covered / well-tested tickets (with AI summary when available)
        if well_covered:
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## Well-covered tickets")
            lines.append("")
            lines.append("Tickets with strong test coverage (score ≥ 8, coverage ≥ 85% or N/A):")
            lines.append("")
            for m in sorted(well_covered, key=lambda x: (x.repo, x.pr_number)):
                pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
                ticket = m.jira_ticket or "—"
                cov_str = _coverage_display_str(m)
                one_line = _extract_ai_summary(m.ai_report, max_chars=600)
                if one_line:
                    one_line = _sanitize_score_in_text(one_line, m.testing_quality_score)
                lines.append(f"- **[{ticket}]({pr_url})** — #{m.pr_number} {m.repo} — Score {_score_display(m)}, Coverage {cov_str}")
                if one_line:
                    lines.append(f"  - {one_line}")
                lines.append("")

        # Areas for improvement (with AI summary and top recommendations)
        if needs_work:
            lines.append("---")
            lines.append("")
            lines.append("## Areas for Improvement")
            lines.append("")
            lines.append("PRs that should be reviewed (tests, score, or coverage):")
            lines.append("")
            for m, reason in sorted(needs_work, key=lambda x: (x[0].repo, x[0].pr_number)):
                pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
                ticket = m.jira_ticket or "—"
                lines.append(f"- **[#{m.pr_number} {m.repo}]({pr_url})** — {ticket} — *{reason}*")
                scope_note = _extract_scope_alignment(m.ai_report, max_chars=800)
                if scope_note and _scope_status(scope_note) == "issues":
                    lines.append(f"  - **Scope:** {scope_note}")
                ai_sum = _extract_ai_summary(m.ai_report, max_chars=600)
                if ai_sum:
                    ai_sum = _sanitize_score_in_text(ai_sum, m.testing_quality_score)
                    lines.append(f"  - **AI observation:** {ai_sum}")
                recs = _extract_ai_recommendations(m.ai_report, max_bullets=2)
                for rec in recs:
                    lines.append(f"  - *Recommendation:* {rec}")
                lines.append("")

        # General recommendations (aggregate from needs_work PRs that have AI reports)
        all_recs = []
        for m, _ in needs_work:
            recs = _extract_ai_recommendations(m.ai_report, max_bullets=1)
            if recs:
                all_recs.append((m, recs[0]))
        if all_recs:
            lines.append("---")
            lines.append("")
            lines.append("## General observations and recommendations")
            lines.append("")
            for m, rec in all_recs[:12]:  # cap to avoid huge report
                lines.append(f"- **#{m.pr_number} {m.repo}:** {rec}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## PR Details")
        lines.append("")
        for m in sorted(all_metrics, key=lambda x: (x.repo, x.pr_number)):
            pr_url = f"https://github.com/{m.repo}/pull/{m.pr_number}"
            ticket = m.jira_ticket or "—"
            cov_str = _coverage_display_str(m)
            detail_lines = [
                f"### [#{m.pr_number} {m.repo}]({pr_url})",
                "",
                f"- **Title:** {m.title}",
                f"- **Author:** {m.author}",
                f"- **Ticket:** {ticket}",
                f"- **Score:** {_score_display(m)} · **Coverage (AI):** {cov_str} · **Tests added:** {m.tests_added}",
            ]
            ai_sum = _extract_ai_summary(m.ai_report, max_chars=800)
            if ai_sum:
                ai_sum = _sanitize_score_in_text(ai_sum, m.testing_quality_score)
                detail_lines.append(f"- **AI summary:** {ai_sum}")
            scope_note = _extract_scope_alignment(m.ai_report, max_chars=800)
            if scope_note:
                detail_lines.append(f"- **Scope vs ticket:** {scope_note}")
            if not getattr(m, "is_contract_only", False) and m.has_testable_code and m.tests_added == 0:
                detail_lines.append("- ⚠️ No tests added for testable code.")
            if not getattr(m, "is_contract_only", False) and m.testing_quality_score < 6.0:
                detail_lines.append("- ⚠️ Low score — review test quality or coverage.")
            if _coverage_for_display(m) < 0.5 and m.has_testable_code and not getattr(m, "is_contract_only", False):
                detail_lines.append("- ⚠️ Low estimated coverage.")
            detail_lines.append("")
            lines.extend(detail_lines)
        return "\n".join(lines).replace("\n\n\n", "\n\n")

    def _pr_markdown(self, m: PRMetrics) -> str:
        change_cov_pct = f"{m.effective_coverage * 100:.0f}%"
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

        # Score display — N/A for config/i18n-only; neutral for contract-only
        if not m.has_testable_code:
            score_line = "| **Testing Quality Score** | **N/A** _(config/i18n-only PR)_ |"
        elif getattr(m, "is_contract_only", False):
            score_line = (
                "| **Testing Quality Score** | **N/A** _(contract-only; testing out of scope)_ |"
            )
        else:
            score_line = f"| **Testing Quality Score** | **{m.testing_quality_score} / 10** ({badge}) |"

        pairing_pct = f"{m.test_file_pairing_rate * 100:.0f}%"
        assertion_note = f"{m.assertion_count} lines"

        if getattr(m, "is_contract_only", False):
            contract_callout = (
                "\n"
                "> **Contract-only change.** This PR only adds or modifies API contracts (OpenAPI/schema, generated routes). "
                "Testing is typically added in follow-up PRs when business logic is implemented. "
                "Score is neutral (not penalized for no tests).\n"
            )
        else:
            contract_callout = ""

        lines += [
            "---",
            "",
            "## Quality Score",
            contract_callout,
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
        if getattr(m, "is_contract_only", False):
            lines.append("| Score basis | Contract-only — testing out of scope for this PR |")
        elif m.has_testable_code:
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
                cov = f"{m.effective_coverage * 100:.0f}%"
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
