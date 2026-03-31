## ADDED Requirements

### Requirement: Extract domain invariants from a batch of Jira tickets by project
The system SHALL support bulk extraction mode where a Jira project key and a list of ticket dictionaries (key + description) are passed in, returning a list of `JiraInvariantContext` objects — one per ticket — without requiring individual ticket key lookups.

#### Scenario: Batch extraction from project-level mining results
- **WHEN** `JiraInvariantExtractor.extract_batch(tickets)` is called with a list of `{"key": "CLOSE-123", "description": "..."}` dicts
- **THEN** each ticket is processed in order and a `JiraInvariantContext` (with `porting_signals` and `domain_constraints`) is returned for each; tickets with empty or None descriptions return empty `JiraInvariantContext` objects

#### Scenario: Batch with 100 tickets completes without error
- **WHEN** 100 tickets are passed to `extract_batch`
- **THEN** all 100 are processed; no exception is raised even if individual tickets have malformed or missing descriptions

#### Scenario: Deduplication across batch
- **WHEN** multiple tickets contain the same normative constraint sentence verbatim
- **THEN** the deduplicated set of `DomainConstraint` strings is returned across the batch via a `merge_batch` helper method; no duplicate constraint appears more than once in the merged result

### Requirement: Expose merged project-level domain constraints for pipeline consumption
The system SHALL provide a `merge_batch(contexts)` class method that aggregates a list of `JiraInvariantContext` objects into a single merged context with deduplicated constraints and all porting signals combined.

#### Scenario: Merged context used by domain knowledge pipeline
- **WHEN** the Jira domain miner calls `JiraInvariantExtractor.merge_batch(contexts)` after processing all project tickets
- **THEN** the resulting `JiraInvariantContext` has `domain_constraints` deduped by value and `porting_signals` deduped by phrase+context combination

#### Scenario: Empty batch merged
- **WHEN** `merge_batch([])` is called
- **THEN** an empty `JiraInvariantContext` is returned with empty lists for both fields
