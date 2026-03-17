## ADDED Requirements

### Requirement: Infer module name and relative path from PR file paths
The system SHALL extract the module name and relative path from each production file in the PR diff using path-based inference (no configuration required). The module SHALL be the path segment immediately following a common parent directory shared by multiple files (e.g. `ui/checklist-client/src/helpers/signoffs.js` → module `checklist-client`, relative `src/helpers/signoffs.js`).

#### Scenario: Files under ui/ with client subdirectory
- **WHEN** PR files include `ui/checklist-client/src/helpers/signoffs.js`
- **THEN** module is inferred as `checklist-client` and relative path as `src/helpers/signoffs.js`

#### Scenario: Files without a discoverable module structure
- **WHEN** PR files are all at the repo root (e.g. `main.py`, `config.py`)
- **THEN** sibling fetcher returns an empty context; no error raised

### Requirement: Discover sibling modules in the same repository
The system SHALL list sibling directories at the same parent level as the inferred module (e.g. all `ui/*/` directories) using the GitHub Trees API, and treat each sibling as a candidate reference implementation source.

#### Scenario: Multiple sibling modules found
- **WHEN** the repo contains `ui/checklist-client/`, `ui/recs-client/`, and `ui/www-close/`
- **THEN** all three are considered siblings of `checklist-client`

#### Scenario: Only one module at that level
- **WHEN** no siblings exist at the inferred parent level
- **THEN** sibling fetcher returns an empty context

### Requirement: Fetch equivalent file content from up to 3 siblings
For each inferred relative path, the system SHALL attempt to fetch the same path from up to 3 sibling modules using the GitHub Contents API. Each fetched file SHALL be capped at 3 000 characters. The total fetched content SHALL NOT exceed 9 000 characters across all siblings.

#### Scenario: Equivalent file exists in sibling
- **WHEN** `recs-client/src/helpers/signoffs.js` exists in the repo
- **THEN** its content (truncated at 3 000 chars) is included in the `SiblingRef` result

#### Scenario: Equivalent file missing in sibling
- **WHEN** the sibling module does not have the same relative path
- **THEN** that sibling is skipped silently; no error raised

#### Scenario: GitHub API rate limit hit (403 / 429)
- **WHEN** the GitHub API returns 403 or 429 during sibling fetch
- **THEN** fetcher returns whatever results were collected so far and logs a warning; pipeline continues without error

### Requirement: Return structured output capped by budget
The system SHALL return a `SiblingContext` dataclass with `refs: list[SiblingRef]`, where each `SiblingRef` has `module`, `relative_path`, `content`. When `ENABLE_CROSS_REPO_SIBLINGS=false`, the system SHALL return an empty `SiblingContext` immediately.

#### Scenario: Feature disabled via config
- **WHEN** `ENABLE_CROSS_REPO_SIBLINGS=false`
- **THEN** no GitHub API calls are made and an empty `SiblingContext` is returned
