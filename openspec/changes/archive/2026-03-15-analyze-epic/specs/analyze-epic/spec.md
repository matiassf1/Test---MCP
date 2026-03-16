# Spec: analyze-epic

## Overview

The `analyze_epic` capability maps a Jira Epic to all related merged PRs on GitHub and produces a consolidated testing quality report.

---

### Requirement: Epic metadata enrichment

The system MUST fetch Epic metadata (summary, status) from Jira when Jira credentials are configured.

#### Scenario: Jira credentials available

WHEN `analyze_epic` is called with a valid Epic key and Jira is configured
THEN the response includes `epic_summary` populated from Jira

#### Scenario: Jira credentials absent

WHEN Jira is not configured (empty `JIRA_URL` or `JIRA_API_TOKEN`)
THEN `epic_summary` is `null` and processing continues without error

---

### Requirement: Child ticket discovery

The system MUST fetch all child tickets of the Epic from Jira and include them in the response.

#### Scenario: Epic has child tickets

WHEN the Epic has child issues in Jira
THEN `child_tickets` contains each child with `key`, `summary`, `issue_type`, and `status`

#### Scenario: Epic has no child tickets

WHEN the Epic has no children
THEN `child_tickets` is an empty list and PR discovery proceeds using the Epic key alone

---

### Requirement: PR discovery via GitHub Search

The system MUST search GitHub for merged PRs mentioning the Epic key or any of its child ticket keys.

#### Scenario: PRs found

WHEN GitHub Search returns PRs mentioning the Epic or child keys
THEN each unique `(repo, pr_number)` pair is included exactly once in the analysis queue

#### Scenario: No PRs found

WHEN no merged PRs are found for the Epic or its children
THEN the response contains an empty `prs_analyzed` list and a descriptive message in `summary`

#### Scenario: Scope is a single repo

WHEN `repo` is provided
THEN search is scoped to `repo:<org>/<name>`

#### Scenario: Scope is an org

WHEN `org` is provided and `repo` is empty
THEN search is scoped to `org:<org>` across all repos

---

### Requirement: Per-PR analysis

The system MUST run the full `PRAnalysisPipeline` on each discovered PR.

#### Scenario: PR analysis succeeds

WHEN a PR is successfully analyzed
THEN its entry in `prs_analyzed` includes `title`, `author`, `testing_quality_score`, `llm_estimated_coverage`, `tests_added`, and optionally `ai_report`

#### Scenario: PR analysis fails

WHEN a PR analysis throws an exception
THEN its entry has `status: "error"` and `error` with the exception message, and `failed` counter increments; processing continues for remaining PRs

#### Scenario: skip_existing is enabled

WHEN `skip_existing=True` and a `(repo, pr_number)` pair already exists in storage
THEN the stored metrics are used directly without re-running the pipeline

---

### Requirement: Aggregate summary

The system MUST compute aggregate statistics across all successfully analyzed PRs.

#### Scenario: Summary computation

WHEN at least one PR is successfully analyzed
THEN `summary.avg_testing_quality_score` is the mean of all `testing_quality_score` values (rounded to 2 decimal places)
AND `summary.total_tests_added` is the sum of `tests_added` across successful PRs

#### Scenario: All PRs failed

WHEN every PR fails analysis
THEN `avg_testing_quality_score` is `0.0` and `total_tests_added` is `0`

---

### Requirement: AI report inclusion

The system MUST respect the `include_ai_report` flag.

#### Scenario: include_ai_report is True (default)

WHEN `include_ai_report=True`
THEN each PR entry includes `ai_report` (may be `null` if AI is disabled)

#### Scenario: include_ai_report is False

WHEN `include_ai_report=False`
THEN `ai_report` is omitted from all PR entries

---

### Requirement: Rate-limit management between PRs

The system MUST insert a configurable delay between consecutive PR analyses when an AI provider is configured.

#### Scenario: OpenRouter or OpenAI key configured

WHEN `OPENROUTER_API_KEY` or `OPENAI_API_KEY` is set
THEN a delay of `openrouter_batch_delay_seconds` (default: 12s) is applied between each PR

#### Scenario: No AI provider configured

WHEN neither key is set
THEN no delay is applied between PRs
