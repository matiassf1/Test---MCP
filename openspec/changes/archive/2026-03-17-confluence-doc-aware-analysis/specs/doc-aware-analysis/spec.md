## ADDED Requirements

### Requirement: Assemble analysis context from ticket and Confluence docs
The system SHALL build a context string combining the Jira ticket description and Confluence page content, respecting a total character budget of 6 000 characters, prioritizing remoteLink pages over description-extracted pages.

#### Scenario: Single Confluence page within budget
- **WHEN** one Confluence page (2 000 chars) is found for a ticket
- **THEN** the full page content is included in the context string

#### Scenario: Multiple pages exceeding budget
- **WHEN** three Confluence pages totaling 10 000 chars are found
- **THEN** pages are included in priority order until the 6 000 char budget is exhausted; each truncated page includes a `[truncated]` marker

#### Scenario: No Confluence pages available
- **WHEN** no Confluence pages are found for a ticket
- **THEN** the context string contains only the Jira ticket description; LLM prompt falls back to standard analysis

### Requirement: Inject Confluence context into the LLM prompt
The system SHALL prepend a `## Business specification context` section to the LLM prompt when Confluence content is available, instructing the model to validate the implementation against the specification and quote both spec and diff when flagging violations.

#### Scenario: Prompt with Confluence context
- **WHEN** Confluence content is available and an LLM key is configured
- **THEN** the AI report includes a `### Spec vs Implementation` section listing any contradictions between the spec and the diff

#### Scenario: Prompt without Confluence context
- **WHEN** no Confluence content is available
- **THEN** the prompt is identical to the existing prompt; no `## Business specification context` section is injected

### Requirement: Extract structured risk signals from LLM output
The system SHALL parse the LLM report to extract `spec_violations` (list of strings) and `risk_level_suggestion` (HIGH / MEDIUM / LOW) when the model produces a `### Spec vs Implementation` section.

#### Scenario: LLM flags a spec violation
- **WHEN** the AI report contains a `### Spec vs Implementation` section with at least one bullet item
- **THEN** `spec_violations` is populated with those items and stored in `PRMetrics`

#### Scenario: LLM finds no violations
- **WHEN** the AI report's `### Spec vs Implementation` section states no contradictions found
- **THEN** `spec_violations` is an empty list
