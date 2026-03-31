## ADDED Requirements

### Requirement: Extract Harness feature flag keys from GitHub source files
The system SHALL scan the file trees of priority repos (from `repo_priority_index.yaml`) for Harness feature flag key identifiers and produce a flat list of unique flag keys with their owning module.

#### Scenario: Flag key found in TypeScript constant file
- **WHEN** a file matches the pattern `**/featureFlags.ts`, `**/feature-flags.ts`, or `**/constants/flags*` and contains a string assignment matching `"close_[a-z0-9_-]+"` or `'close_[a-z0-9_-]+'`
- **THEN** each matched key is extracted, deduplicated, and recorded with the containing file path as owning module context

#### Scenario: Flag key found in hook/component usage
- **WHEN** a file contains `useFeatureFlag("close_...")`, `getFeatureFlag('close_...')`, or `featureFlagClient.variation("close_...", ...)` patterns
- **THEN** the key is extracted; if the same key was already found in a constants file, the constants file takes precedence as owning module

#### Scenario: Test files excluded
- **WHEN** a file path contains `__tests__/`, `.test.ts`, `.spec.ts`, `.test.js`, or `.spec.js`
- **THEN** flag keys found in that file are NOT included in the output

#### Scenario: No flag files found in repo
- **WHEN** a repo contains no files matching flag patterns
- **THEN** the extractor records 0 flags for that repo and continues without error

### Requirement: Extract custom tlcModules flag entries
The system SHALL scan for FloQast-specific `tlcModules` feature toggle patterns and extract module name keys with their usage context.

#### Scenario: tlcModules usage detected
- **WHEN** a file contains `tlcModules["<key>"]`, `tlcModules['<key>']`, `getTlcModule("<key>")`, or `isTlcModuleEnabled("<key>")` patterns
- **THEN** each unique `<key>` is extracted and recorded as a `tlcModules` flag with the file path as owning module

#### Scenario: Module registry file detected
- **WHEN** a file path matches `**/tlcModules*`, `**/module-registry*`, or `**/moduleConfig*` and contains object key definitions
- **THEN** top-level string keys are extracted as canonical module names; these take precedence over usage-site extractions for the owning module field

### Requirement: Write structured feature flag output to domain_knowledge/feature_flags.md
The system SHALL write all extracted flags to `domain_knowledge/feature_flags.md` in a format compatible with the domain context §4 Feature Flags section.

#### Scenario: Output file written with Harness and tlcModules sections
- **WHEN** extraction completes across all priority repos
- **THEN** `feature_flags.md` is written with two sections: `## Harness Flags` and `## tlcModules`, each with a bullet per unique key: `- <key>: owning module: <path>; seen in: <N> files`

#### Scenario: Incremental re-run merges with existing output
- **WHEN** `feature_flags.md` already exists and extraction is re-run
- **THEN** new keys are appended; existing keys have their `seen in` count updated; no duplicates are written

### Requirement: Degrade gracefully when GitHub access is unavailable
The system SHALL skip flag extraction for any repo that returns a non-200 status when fetching the file tree, logging a warning per repo.

#### Scenario: Repo file tree fetch fails
- **WHEN** the GitHub API returns 403 or 404 for a repo's tree endpoint
- **THEN** the extractor logs `WARNING: skipping <repo> — tree fetch failed (403)` and moves to the next repo
