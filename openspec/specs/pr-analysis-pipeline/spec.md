## ADDED Requirements

### Requirement: Pipeline fetches Confluence docs after Jira ticket resolution
The system SHALL call `ConfluenceService.get_pages_for_ticket()` after the Jira ticket is resolved, when `CONFLUENCE_BASE_URL` and `CONFLUENCE_TOKEN` are configured, and pass the result to the AI reporter and risk analyzer.

#### Scenario: Confluence enabled and ticket resolved
- **WHEN** a Jira ticket is found for the PR and Confluence credentials are configured
- **THEN** the pipeline fetches linked Confluence pages before calling `ai_reporter` and `risk_analyzer`

#### Scenario: Confluence disabled
- **WHEN** Confluence credentials are not configured
- **THEN** the pipeline proceeds to AI analysis with no Confluence context; no exception is raised

### Requirement: Pipeline runs risk scoring after diff analysis
The system SHALL call `risk_analyzer.compute_risk()` after `ChangeAnalyzer` and `TestDetector` have processed the diff, and before `MetricsEngine` finalizes the `PRMetrics` object, so that `risk_level`, `risk_points`, and `risk_factors` are included in the saved metrics.

#### Scenario: Risk scoring runs on every PR
- **WHEN** any PR is analyzed (regardless of AI key availability)
- **THEN** `PRMetrics` is saved with `risk_level`, `risk_points`, and `risk_factors` populated

## MODIFIED Requirements

### Requirement: PRMetrics includes risk and spec violation fields
`PRMetrics` SHALL include the following additional optional fields:
- `risk_level: Optional[str]` — HIGH / MEDIUM / LOW (None if not yet scored)
- `risk_points: int` — raw score from static heuristics (default 0)
- `risk_factors: list[str]` — human-readable justifications (default [])
- `spec_violations: list[str]` — items extracted from LLM `### Spec vs Implementation` section (default [])

#### Scenario: PR analyzed without AI
- **WHEN** a PR is analyzed with no AI key configured
- **THEN** `risk_level`, `risk_points`, and `risk_factors` are set; `spec_violations` is an empty list

#### Scenario: PR analyzed with AI and Confluence context
- **WHEN** a PR is analyzed with an AI key and Confluence pages available
- **THEN** all four fields are populated; `spec_violations` may contain LLM-extracted items
