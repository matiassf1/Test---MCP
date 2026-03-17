## ADDED Requirements

### Requirement: Configure Confluence integration via environment variables
The system SHALL read Confluence credentials exclusively from environment variables (`CONFLUENCE_BASE_URL`, `CONFLUENCE_TOKEN`) via the existing `Settings` (pydantic-settings). No code changes are required in analyzed repositories.

#### Scenario: Credentials present
- **WHEN** `CONFLUENCE_BASE_URL` and `CONFLUENCE_TOKEN` are set in `.env`
- **THEN** `ConfluenceService` initializes and fetching is enabled for all PR analyses

#### Scenario: Credentials absent
- **WHEN** either `CONFLUENCE_BASE_URL` or `CONFLUENCE_TOKEN` is empty or missing
- **THEN** Confluence fetching is silently skipped; all other analysis runs normally

### Requirement: Risk heuristics require no per-repo configuration
The system SHALL apply all static risk heuristics (auth signal, feature flag detection, behavioral ratio, role gap) using pattern matching on the PR diff without requiring any configuration file in the analyzed repository.

#### Scenario: No config file present
- **WHEN** a PR is analyzed and no `.testing-tool/config.yaml` exists in the repo
- **THEN** risk scoring runs with default heuristic patterns and produces a valid `risk_level`

### Requirement: Optional per-repo config for domain ERD page mapping
The system SHALL support an optional `.testing-tool/config.yaml` in analyzed repositories to declare Confluence space key, ERD label, and path-to-page-ID mappings. When present, it extends the default page discovery with domain-specific pages.

#### Scenario: config.yaml with path mapping present
- **WHEN** `.testing-tool/config.yaml` maps `"ui/checklist-client/"` to a Confluence page ID and the PR modifies files under that path
- **THEN** that page is fetched and included in the Confluence context (within the 6 000 char budget)

#### Scenario: config.yaml malformed or unreadable
- **WHEN** `.testing-tool/config.yaml` exists but contains invalid YAML
- **THEN** the system logs a warning and proceeds with remoteLinks discovery only; no exception is raised
