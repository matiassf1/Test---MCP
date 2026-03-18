"""Contextual workflow analysis — richness / skip behavior."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.contextual_workflow_analysis import try_contextual_workflow_analysis
from src.models import FileChange, JiraIssue, PRMetrics, TestTypeCount


def _m(
    *,
    jira_ticket: Optional[str] = "CLOSE-1",
    jira_issue: Optional[JiraIssue] = None,
    repo_docs: str = "x" * 500,
) -> PRMetrics:
    fc = FileChange(
        filename="src/a.js",
        status="modified",
        additions=5,
        deletions=0,
        patch="+ok",
    )
    return PRMetrics(
        pr_number=1,
        author="a",
        title="[CLOSE-1] feature",
        repo="org/repo",
        pr_date=datetime.utcnow(),
        jira_ticket=jira_ticket,
        jira_issue=jira_issue,
        files_changed=1,
        lines_modified=5,
        lines_covered=0,
        change_coverage=0.0,
        production_lines_added=5,
        production_lines_modified=0,
        test_lines_added=0,
        test_code_ratio=0.0,
        testing_quality_score=5.0,
        tests_added=0,
        test_types=TestTypeCount(),
        file_changes=[fc],
        has_testable_code=True,
    )


def test_skip_when_no_ticket_and_no_docs():
    m = _m(jira_ticket=None, repo_docs="")
    m.jira_ticket = None
    m.title = "random chore"
    out = try_contextual_workflow_analysis(
        m, confluence_context="", epic_markdown="", repo_docs_markdown="", pr_description=""
    )
    assert out and "skipped" in out.lower()


def test_runs_path_when_jira_ticket_even_if_thin_docs():
    """With ticket linked, richness boost avoids skip (LLM may still return _not run_ without API keys)."""
    m = _m(jira_ticket="CLOSE-99", repo_docs="")
    out = try_contextual_workflow_analysis(m, repo_docs_markdown="")
    assert out is not None
    assert "skipped" not in (out or "").lower() or "not run" in (out or "").lower()
