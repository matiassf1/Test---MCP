## ADDED Requirements

### Requirement: Extract property-value pairs from test files for production files in the diff
For each production file modified in the PR, the system SHALL locate its test counterpart(s) using the existing `file_classification` module and scan their content for property-value literal patterns (e.g. `isWorkflow: true`, `isEnabled: false`, `type: "workflow"`) inside `describe`/`it`/`test` blocks.

#### Scenario: Test file found for production file
- **WHEN** `authorization.js` is modified and `authorization.test.js` exists in the repo
- **THEN** the validator scans `authorization.test.js` for property-value literals

#### Scenario: No test counterpart found
- **WHEN** a production file has no detectable test counterpart
- **THEN** no invariants are derived for that file; no error raised

### Requirement: Derive invariants from high-frequency property-value patterns
The system SHALL count occurrences of each unique property-value pair across all test cases (individual `it`/`test` blocks) for a given module. A pair SHALL be promoted to an invariant when it appears in ≥ 80% of test cases AND in at least 3 distinct test cases. The threshold SHALL be configurable via `TEST_INVARIANT_THRESHOLD` env var (default `0.8`).

#### Scenario: isWorkflow always true
- **WHEN** `isWorkflow: true` appears in 9 out of 10 test cases for a given module
- **THEN** `TestInvariant(property="isWorkflow", value="true", frequency=0.9, module="checklist-client")` is returned

#### Scenario: Insufficient test cases
- **WHEN** a module has fewer than 3 test cases
- **THEN** no invariants are derived for that module

#### Scenario: Mixed values — not an invariant
- **WHEN** `isWorkflow` is `true` in 5 cases and `false` in 5 cases
- **THEN** `isWorkflow` is NOT promoted to an invariant

### Requirement: Surface invariants as LLM validation context
The system SHALL return a `TestInvariantContext` dataclass with `invariants: list[TestInvariant]`. When non-empty, the pipeline SHALL include a `## Test-Derived Domain Invariants` section in the LLM prompt listing each invariant as: `"In <module> tests, <property> is always <value>"`.

#### Scenario: Invariant injected into LLM prompt
- **WHEN** `TestInvariantContext` contains `isWorkflow=true` for `checklist-client`
- **THEN** the LLM prompt includes `"In checklist-client tests, isWorkflow is always true"` and is instructed to flag any production guard that contradicts this invariant

#### Scenario: Feature disabled via config
- **WHEN** `ENABLE_TEST_INVARIANTS=false`
- **THEN** no test files are scanned and an empty `TestInvariantContext` is returned

### Requirement: Degrade gracefully on parse errors
The system SHALL catch all exceptions during test file scanning (file not found, encoding errors, malformed test syntax) and continue with partial results rather than propagating errors to the pipeline.

#### Scenario: Test file cannot be decoded
- **WHEN** a test file contains non-UTF-8 bytes
- **THEN** that file is skipped and a warning is logged; other test files continue to be processed
