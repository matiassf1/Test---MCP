## ADDED Requirements

### Requirement: PR report displays risk level badge alongside quality score
The system SHALL render a risk badge (`⚠️ HIGH`, `🔶 MEDIUM`, `✅ LOW`) next to the testing quality score in PR markdown reports and MCP tool responses when `risk_level` is present.

#### Scenario: HIGH risk PR report
- **WHEN** a PR has `risk_level = HIGH`
- **THEN** the report header shows `Score: 6.8 / 10 (Good) | Risk: ⚠️ HIGH`

#### Scenario: risk_level absent (legacy cached metrics)
- **WHEN** a PR was analyzed before this change and has no `risk_level` field
- **THEN** no risk badge is rendered; report format is unchanged

### Requirement: PR report includes risk factors section when risk is MEDIUM or HIGH
The system SHALL append a `## Risk Signals` section to PR markdown reports listing each item in `risk_factors` as a bullet when `risk_level` is MEDIUM or HIGH.

#### Scenario: Risk factors present
- **WHEN** `risk_factors` contains two items and `risk_level` is HIGH
- **THEN** the report includes a `## Risk Signals` section with two bullet points quoting the factors

#### Scenario: LOW risk — no risk section
- **WHEN** `risk_level` is LOW
- **THEN** no `## Risk Signals` section is added to the report

### Requirement: PR report includes spec violations section when violations are found
The system SHALL append a `## Spec Violations` section listing each `spec_violations` item when the list is non-empty.

#### Scenario: Violations found
- **WHEN** `spec_violations` contains items extracted from the LLM report
- **THEN** the PR report includes a `## Spec Violations` section with each violation as a bullet

### Requirement: Epic report includes risk column in PR table
The system SHALL add a `Risk` column to the epic PR table showing the risk badge for each PR.

#### Scenario: Epic with mixed risk levels
- **WHEN** an epic contains PRs with HIGH, MEDIUM, and LOW risk
- **THEN** the epic PR table shows the badge for each PR in the Risk column

### Requirement: MCP tool responses include risk fields
All MCP tool responses that return PR metrics (`analyze_pr`, `analyze_pr_by_jira_ticket`, `get_pr_metrics`, `batch_analyze_*`) SHALL include `risk_level`, `risk_points`, `risk_factors`, and `spec_violations` fields.

#### Scenario: Tool response with risk data
- **WHEN** a Cursor user calls `analyze_pr_by_jira_ticket` for a HIGH risk PR
- **THEN** the MCP response JSON includes `"risk_level": "HIGH"` and a populated `risk_factors` list
