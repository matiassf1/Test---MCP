from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TestType(str, Enum):
    unit = "unit"
    integration = "integration"
    e2e = "e2e"
    unknown = "unknown"


class FileChange(BaseModel):
    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    modified_lines: list[int] = Field(default_factory=list)
    patch: Optional[str] = None


class TestFile(BaseModel):
    filename: str
    test_type: TestType
    is_new: bool  # True if added in this PR, False if modified
    lines_added: int = 0


class TestTypeCount(BaseModel):
    unit: int = 0
    integration: int = 0
    e2e: int = 0
    unknown: int = 0

    def total(self) -> int:
        return self.unit + self.integration + self.e2e + self.unknown


class JiraIssue(BaseModel):
    """Metadata fetched from Jira for a linked ticket."""

    key: str
    summary: Optional[str] = None
    description: Optional[str] = None   # Ticket body (plain text or stripped HTML); used for scope alignment
    issue_type: Optional[str] = None   # Bug, Story, Task, Epic…
    status: Optional[str] = None       # Open, In Progress, Done…
    priority: Optional[str] = None     # Critical, High, Medium, Low
    components: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class CoverageResult(BaseModel):
    """Result of a pytest coverage run."""

    ran_successfully: bool = False
    lines_covered: int = 0
    lines_modified: int = 0
    change_coverage: float = 0.0         # covered / modified (0.0–1.0)
    overall_percent: Optional[float] = None  # repo-wide %
    fallback_used: bool = False           # True when file-level fallback was applied
    error: Optional[str] = None

    # Explicit change-focused fields (mirrors lines_covered/lines_modified
    # but named to match the spec and make intent clear in reports)
    changed_lines: int = 0
    covered_changed_lines: int = 0
    changed_lines_coverage_percent: float = 0.0  # 0–100



class AuthorStats(BaseModel):
    """Per-author aggregated statistics for the team summary."""

    prs: int = 0
    avg_change_coverage: float = 0.0
    avg_testing_quality_score: float = 0.0
    tests_added: int = 0
    lines_modified: int = 0


class AIAnalysis(BaseModel):
    """Result of AIAnalyzer (Claude) qualitative assessment of PR test quality."""

    assessment: str = ""
    untested_areas: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    ai_quality_score: float = 0.0  # 0–10
    reasoning: str = ""


class PRMetrics(BaseModel):
    pr_number: int
    author: str
    title: str
    repo: str
    pr_date: Optional[datetime] = None

    # Jira
    jira_ticket: Optional[str] = None
    jira_issue: Optional[JiraIssue] = None

    # Code metrics
    files_changed: int
    lines_modified: int
    lines_covered: int
    change_coverage: float  # 0.0 to 1.0
    production_lines_added: int = 0
    production_lines_modified: int = 0
    test_lines_added: int = 0
    overall_coverage: Optional[float] = None  # repo-wide %
    test_code_ratio: float = 0.0              # test_lines_added / production_lines_added

    # Testing quality (0–10 composite score)
    testing_quality_score: float = 0.0

    # Test metrics
    tests_added: int
    test_types: TestTypeCount

    # Detail lists
    file_changes: list[FileChange] = Field(default_factory=list)
    test_files: list[TestFile] = Field(default_factory=list)

    # Test quality signals (computable from diffs without CI)
    test_file_pairing_rate: float = 0.0   # fraction of prod files that have a test counterpart
    assertion_count: int = 0              # count of assert/expect/toBe lines in test diffs
    has_testable_code: bool = True        # False for config/i18n-only PRs (no source code changed)
    is_modification_only: bool = False    # True when PR only modifies existing code (no new prod lines)

    # Free-form markdown report from local LLM via Ollama (populated when AI_ENABLED=true)
    ai_report: Optional[str] = None
    # Diff-heuristic coverage (0.0–1.0) derived from name-matching; always computed
    ai_estimated_coverage: Optional[float] = None
    # LLM-inferred coverage (0.0–1.0) — Ollama reads actual diffs and estimates a percentage
    # Only populated when AI_ENABLED=true and mechanical CI coverage is unavailable
    llm_estimated_coverage: Optional[float] = None
    # Qualitative 0–10 score from AIAnalyzer (Claude, FloQast-aligned); used to blend with formula score
    llm_quality_score: Optional[float] = None


class TeamSummary(BaseModel):
    repo: str
    since_days: int
    prs_analyzed: int

    average_change_coverage: float
    average_testing_quality_score: float = 0.0
    total_tests_added: int
    test_type_distribution: dict[str, float]  # fractions 0.0–1.0

    # Enriched summary fields
    top_contributors: list[dict[str, Any]] = Field(default_factory=list)
    by_author: dict[str, AuthorStats] = Field(default_factory=dict)
    by_issue_type: dict[str, int] = Field(default_factory=dict)
    by_repo: dict[str, dict[str, Any]] = Field(default_factory=dict)  # multi-repo breakdown
    coverage_trend: list[dict[str, Any]] = Field(default_factory=list)

    # When summarising multiple repositories, this lists all of them.
    # Single-repo analyses will have exactly one entry.
    repos: list[str] = Field(default_factory=list)

    pr_metrics: list[PRMetrics] = Field(default_factory=list)
