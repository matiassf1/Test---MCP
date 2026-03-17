## ADDED Requirements

### Requirement: Detect near-duplicate code blocks within a PR diff
The system SHALL compare normalized code blocks across all files in the PR diff using `difflib.SequenceMatcher` and flag pairs with a similarity ratio ≥ 0.75 as potential ported code.

Normalization SHALL strip inline comments, collapse whitespace, and ignore blank lines before comparison. Code blocks SHALL be defined as contiguous non-trivial lines of ≥ 5 lines.

#### Scenario: Near-identical helper in two files
- **WHEN** `fileA.js` and `fileB.js` in the diff both contain a `canUserSign` function with 87% textual similarity
- **THEN** the copy detector returns a flag: `{ source_file, target_file, similarity, source_lines, target_lines }`

#### Scenario: Structurally similar but short blocks
- **WHEN** two files share a 3-line `if (!x) return false` block
- **THEN** no flag is raised (below the 5-line minimum)

#### Scenario: No similar code
- **WHEN** all files in the diff have pairwise similarity < 0.75
- **THEN** copy detector returns an empty list

### Requirement: Copy flags include guard and condition extraction
For each flagged pair, the system SHALL extract any boolean guard expressions (e.g. `!isWorkflow`, `if (flagEnabled)`) present in one block but absent or negated in the other, and include them in the flag as `differing_guards: list[str]`.

#### Scenario: Guard present in source, absent in target
- **WHEN** `recs-client/helpers/signoffs.js` has `if (!isWorkflow) return false` and the copied block in `checklist-client/helpers/signoffAuthorization.js` also has it
- **THEN** the flag includes `differing_guards: ["!isWorkflow"]` and `note: "guard may be domain-specific"`

#### Scenario: Identical guards in both files
- **WHEN** both files have the same guard expressions
- **THEN** `differing_guards` is an empty list

### Requirement: Degrade gracefully when diff is empty or single-file
The system SHALL return an empty flags list without raising an exception when the diff contains fewer than 2 files with extractable code blocks.

#### Scenario: Single-file PR
- **WHEN** a PR modifies only one file
- **THEN** copy detector returns `[]` immediately
