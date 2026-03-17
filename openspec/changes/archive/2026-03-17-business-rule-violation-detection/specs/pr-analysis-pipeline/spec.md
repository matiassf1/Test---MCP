## ADDED Requirements

### Requirement: Pipeline runs business rule detection layers after diff analysis
The system SHALL execute all four business rule detection layers (copy detector, Jira invariant extractor, cross-repo sibling fetcher, test invariant validator) after `ChangeAnalyzer` and `TestDetector` have processed the diff, and before the AI reporter is called. Results SHALL be merged into a single `BusinessRuleContext` and passed to `ai_reporter`.

#### Scenario: All layers enabled
- **WHEN** a PR is analyzed with all four layers enabled and a Jira ticket is linked
- **THEN** `BusinessRuleContext` is populated with results from all four layers and injected into the LLM prompt

#### Scenario: Layer raises unexpected exception
- **WHEN** any single detection layer raises an unhandled exception
- **THEN** that layer's result is treated as empty; remaining layers continue; pipeline does not abort

### Requirement: BusinessRuleContext is merged into PRMetrics
The system SHALL store the following fields from `BusinessRuleContext` into `PRMetrics`:
- `copy_flags: list[dict]` — flagged near-duplicate pairs with guard info
- `jira_invariants: list[str]` — extracted domain constraints from ticket
- `test_invariants: list[str]` — derived always-true conditions from tests
- `business_rule_risks: list[str]` — final list of human-readable risk items (populated after LLM analysis)

#### Scenario: Metrics saved with business rule fields
- **WHEN** a PR is analyzed and copy flags or invariants are found
- **THEN** `PRMetrics` is persisted with populated `copy_flags`, `jira_invariants`, and `test_invariants`

## MODIFIED Requirements

### Requirement: Pipeline fetches Confluence docs after Jira ticket resolution
The system SHALL call `ConfluenceService.get_pages_for_ticket()` after the Jira ticket is resolved, when `CONFLUENCE_BASE_URL` and `CONFLUENCE_TOKEN` are configured, and pass the result to the AI reporter and risk analyzer. Business rule detection layers SHALL run in parallel with (or immediately after) the Confluence fetch, before the LLM call.

#### Scenario: Confluence enabled and ticket resolved
- **WHEN** a Jira ticket is found for the PR and Confluence credentials are configured
- **THEN** the pipeline fetches linked Confluence pages AND runs business rule detection before calling `ai_reporter`

#### Scenario: Confluence disabled
- **WHEN** Confluence credentials are not configured
- **THEN** the pipeline proceeds to business rule detection and then AI analysis with no Confluence context; no exception is raised
