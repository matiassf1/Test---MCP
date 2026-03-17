## MODIFIED Requirements

### Requirement: Inject Confluence context into the LLM prompt
The system SHALL prepend a `## Business specification context` section to the LLM prompt when Confluence content is available, instructing the model to validate the implementation against the specification and quote both spec and diff when flagging violations.

#### Scenario: Prompt with Confluence context
- **WHEN** Confluence content is available and an LLM key is configured
- **THEN** the AI report includes a `### Spec vs Implementation` section listing any contradictions between the spec and the diff

#### Scenario: Prompt without Confluence context
- **WHEN** no Confluence content is available
- **THEN** the prompt is identical to the existing prompt; no `## Business specification context` section is injected

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

## ADDED Requirements

### Requirement: Inject business rule context into the LLM prompt
The system SHALL inject a `BusinessRuleContext` into the LLM prompt as structured sections when any detection layer produces results. The injection SHALL follow this order and format:
1. `## Jira Domain Constraints` — porting signals and normative constraints from the ticket
2. `## Test-Derived Domain Invariants` — always-true conditions from existing tests
3. `## Reference Implementations` — sibling module code for comparison
4. `## Ported Code Flags` — flagged near-duplicate blocks with differing guards

The LLM SHALL be explicitly instructed to: validate the implementation against each invariant, flag any production guard that contradicts a test-derived invariant, and identify guards copied from reference implementations that may not apply in the target domain.

#### Scenario: Invariants and copy flags both present
- **WHEN** `BusinessRuleContext` has test invariants and copy flags
- **THEN** the LLM prompt includes both `## Test-Derived Domain Invariants` and `## Ported Code Flags` sections, and the report includes a `### Business Rule Risks` section

#### Scenario: Only porting signal from Jira (no copy flags)
- **WHEN** `jira_invariants` has items but `copy_flags` is empty
- **THEN** only `## Jira Domain Constraints` is injected; no copy flags section is added

#### Scenario: All layers empty
- **WHEN** `BusinessRuleContext` is entirely empty
- **THEN** no additional sections are injected; prompt is unchanged

### Requirement: Total business rule context respects character budget
The system SHALL cap the total injected `BusinessRuleContext` content at 4 000 characters. Sections SHALL be truncated in reverse priority order: sibling refs first, then copy flags, then test invariants, then Jira constraints last.

#### Scenario: Budget exceeded
- **WHEN** combined business rule context exceeds 4 000 characters
- **THEN** the lowest-priority sections are truncated with a `[truncated]` marker until the budget is met

### Requirement: Extract business rule risks from LLM output
The system SHALL parse the `### Business Rule Risks` section from the AI report (when present) and populate `PRMetrics.business_rule_risks` with each bullet item as a string.

#### Scenario: LLM flags a domain guard mismatch
- **WHEN** the AI report contains `### Business Rule Risks` with at least one item
- **THEN** `business_rule_risks` is populated and stored in `PRMetrics`

#### Scenario: LLM finds no business rule issues
- **WHEN** the AI report has no `### Business Rule Risks` section
- **THEN** `business_rule_risks` is an empty list
