## ADDED Requirements

### Requirement: Mine Jira project tickets across all relevant issue types
The system SHALL query a Jira project for recent tickets across issue types Story, Task, Bug, Incident, and Epic — replacing the current Bug/Incident-only filter that produces 0 results for the CLOSE project.

#### Scenario: Broad query returns tickets for CLOSE project
- **WHEN** `jira_domain_miner` is called with `project="CLOSE"` and no type filter override
- **THEN** a JQL query `project = CLOSE AND issuetype in (Story, Task, Bug, Incident, Epic) ORDER BY updated DESC` is issued and up to `max_tickets` (default 100) tickets are returned

#### Scenario: max_tickets cap respected with recency ordering
- **WHEN** the CLOSE project has 500+ tickets matching the query
- **THEN** only the 100 most recently updated are retrieved; `jira_patterns.md` includes a `Mined: <N> tickets (latest 100 of <total>)` header

#### Scenario: Custom issue type override
- **WHEN** `--jira-issue-types "Bug,Incident"` is passed explicitly to the CLI
- **THEN** the JQL filter uses the provided types instead of the default broad set

### Requirement: Extract failure patterns from mined tickets
The system SHALL pass retrieved ticket summaries and descriptions through the existing Jira mining LLM prompt and write the structured output to `domain_knowledge/jira_patterns.md`.

#### Scenario: Failure patterns extracted and written
- **WHEN** at least one ticket is retrieved
- **THEN** the LLM produces `## Failure Patterns` with named patterns (name, description, root cause, impact, example) and the output is written to `jira_patterns.md`

#### Scenario: No domain-relevant patterns found
- **WHEN** retrieved tickets are all process/ops tickets with no domain rule violations
- **THEN** `jira_patterns.md` contains `## Failure Patterns\n(no domain failure patterns identified in the mined tickets)` rather than an empty file

#### Scenario: LLM unavailable
- **WHEN** `AI_ENABLED=false`
- **THEN** ticket summaries are written as raw bullet list under `## Raw Ticket Summaries` without LLM pattern extraction

### Requirement: Record ticket metadata as sources
The system SHALL include a `## Sources` section in `jira_patterns.md` listing each mined ticket key, summary, type, and URL.

#### Scenario: Sources section written
- **WHEN** `jira_patterns.md` is generated with at least one ticket
- **THEN** `## Sources` lists each ticket as `- [<KEY>: <summary>](<jira_url>/browse/<KEY>) (type: <issuetype>)`

### Requirement: Scope mining to a date range
The system SHALL support `--since-days` (default 180) to limit mining to tickets updated within the given number of days.

#### Scenario: Date-scoped query applied
- **WHEN** `--since-days 90` is passed
- **THEN** JQL includes `AND updated >= -90d` and the `jira_patterns.md` header states `Mined: tickets updated in last 90 days`

#### Scenario: Default 180 days applied
- **WHEN** no `--since-days` flag is provided
- **THEN** JQL uses `AND updated >= -180d` as the default window
