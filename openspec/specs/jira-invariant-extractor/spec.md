## ADDED Requirements

### Requirement: Detect porting signals in Jira ticket descriptions
The system SHALL scan the Jira ticket description for porting signal phrases using case-insensitive regex and return a `PortingSignal` when found. Signal phrases SHALL include: `parity`, `based on`, `ported from`, `similar to`, `replicate`, `match behavior`, `same as`, `mirror`.

#### Scenario: Ticket mentions parity
- **WHEN** the description contains "ensure parity between Folders, Checklist, and Reconciliations pages"
- **THEN** a `PortingSignal` is returned with `phrase: "parity"` and the surrounding sentence as context

#### Scenario: No porting signal
- **WHEN** the description contains no porting signal phrases
- **THEN** an empty list is returned; no error raised

#### Scenario: Multiple signals
- **WHEN** the description contains both "based on recs-client" and "ensure parity"
- **THEN** both signals are returned as separate `PortingSignal` items

### Requirement: Extract domain constraint statements from ticket descriptions
The system SHALL extract sentences containing normative constraint keywords (`must`, `always`, `never`, `should not`, `shall`, `required`, `ensure`) from the ticket description and return them as a list of `DomainConstraint` strings.

#### Scenario: Constraint sentence extracted
- **WHEN** the description contains "Ensure the user has not already signed off"
- **THEN** `DomainConstraint("Ensure the user has not already signed off")` is returned

#### Scenario: Acceptance criteria parsed
- **WHEN** the description has an "Acceptance criteria" section with bulleted normative items
- **THEN** each normative bullet is extracted as a separate `DomainConstraint`

#### Scenario: Description is empty or None
- **WHEN** the Jira issue has no description
- **THEN** both porting signals and domain constraints return empty lists; no exception raised

### Requirement: Return structured output for downstream consumption
The system SHALL return a `JiraInvariantContext` dataclass with fields `porting_signals: list[PortingSignal]` and `domain_constraints: list[str]`, used by the pipeline to build the LLM prompt context.

#### Scenario: Non-empty result injected into prompt
- **WHEN** `JiraInvariantContext` contains at least one constraint or signal
- **THEN** the pipeline includes a `## Jira Domain Constraints` section in the LLM prompt
