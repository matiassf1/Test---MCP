## ADDED Requirements

### Requirement: Merge mined artifacts into domain_context.md using guard markers
The system SHALL enrich `domain_context.md` by inserting or updating content inside `<!-- BEGIN MINED -->` / `<!-- END MINED -->` guard blocks within the relevant sections, without modifying any content outside those blocks.

#### Scenario: First enrichment run inserts guard blocks
- **WHEN** `DomainContextEnricher.enrich()` is called and a target section (e.g. `## 4. FEATURE FLAGS`) exists but has no guard block
- **THEN** a `<!-- BEGIN MINED -->\n<content>\n<!-- END MINED -->` block is appended at the end of that section, before the next `## ` header

#### Scenario: Subsequent enrichment run replaces guard block content
- **WHEN** a `<!-- BEGIN MINED -->` / `<!-- END MINED -->` block already exists in a section
- **THEN** the content between the markers is replaced with the new mined content; the markers themselves and all content outside the block are untouched

#### Scenario: Section not found in domain_context.md
- **WHEN** the enricher targets `## 10. REPO PRIORITY INDEX` but that section does not exist
- **THEN** the enricher appends the entire new section (header + guard block) at the end of the file

### Requirement: Enrich §4 Feature Flags with extracted flag keys
The system SHALL read `domain_knowledge/feature_flags.md` and insert a `### Mined Flags` subsection inside the §4 guard block with all extracted Harness and tlcModules keys.

#### Scenario: Feature flags inserted under §4
- **WHEN** `feature_flags.md` contains at least one Harness or tlcModules entry
- **THEN** the §4 guard block in `domain_context.md` contains a `### Harness Flags (mined)` and/or `### tlcModules (mined)` subsection with one bullet per unique key

#### Scenario: No flags found
- **WHEN** `feature_flags.md` is empty or missing
- **THEN** §4 guard block contains `(no flags extracted — run feature-flag-extractor to populate)` and no existing manually authored §4 content is modified

### Requirement: Enrich §6 Known Failure Patterns with Jira-mined patterns
The system SHALL read `domain_knowledge/jira_patterns.md` and append new patterns inside the §6 guard block that do not duplicate existing manually authored patterns.

#### Scenario: New patterns appended under §6
- **WHEN** `jira_patterns.md` contains patterns not already present in §6 by name
- **THEN** each new pattern is appended inside the §6 guard block in the standard `### Pattern: <Name>` format

#### Scenario: Duplicate pattern name suppressed
- **WHEN** a mined pattern has the same name (case-insensitive) as an existing manually authored pattern in §6
- **THEN** the mined version is skipped; a comment `<!-- mined duplicate: <name> suppressed -->` is written inside the guard block

### Requirement: Add §10 Repo Priority Index from mined index
The system SHALL insert a new `## 10. REPO PRIORITY INDEX` section into `domain_context.md` listing the top 10 repos from `repo_priority_index.yaml` with their priority, rationale, and domain areas.

#### Scenario: §10 written with top repos
- **WHEN** `repo_priority_index.yaml` contains at least one entry
- **THEN** `domain_context.md` ends with a new `## 10. REPO PRIORITY INDEX` section (inside guard block) listing the top 10 repos in ranked order

#### Scenario: Index YAML missing
- **WHEN** `repo_priority_index.yaml` does not exist
- **THEN** enricher skips §10 enrichment and logs `INFO: repo_priority_index.yaml not found — skipping §10`

### Requirement: Enrichment is idempotent
The system SHALL produce identical output when run twice on an unchanged set of mined artifacts.

#### Scenario: Re-run with same artifacts produces no diff
- **WHEN** all mined artifact files are unchanged and enrichment is run a second time
- **THEN** `domain_context.md` is byte-for-byte identical to the output of the first run
