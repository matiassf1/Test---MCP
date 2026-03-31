## ADDED Requirements

### Requirement: Build a prioritized index of FloQast GitHub repositories
The system SHALL query the FloQast GitHub organization for all repositories and produce a ranked YAML index at `domain_knowledge/repo_priority_index.yaml`, ordered by domain criticality score.

#### Scenario: Index built from live GitHub org
- **WHEN** `build_repo_index.py` is run with a valid `GITHUB_TOKEN` and `FLOQAST_ORG`
- **THEN** the script fetches all non-archived repos, scores each one, and writes a sorted YAML file with fields: `repo`, `priority` (1=highest), `score`, `rationale`, `domain_areas[]`

#### Scenario: Max repos cap respected
- **WHEN** the org has more repos than `--max-repos` (default 50)
- **THEN** only the top 50 by commit activity in the last 90 days are scored and included

#### Scenario: GitHub API rate limit hit
- **WHEN** a secondary rate limit is encountered mid-scan
- **THEN** the script sleeps 1 second and retries once before logging a warning and continuing with the repos already fetched

### Requirement: Score repositories by domain criticality
The system SHALL compute a numeric score for each repo based on three weighted factors: commit frequency (last 90 days), unique contributors, and presence of domain keywords in repo description or topics.

#### Scenario: High-criticality repo detected
- **WHEN** a repo has >50 commits in 90 days, ≥3 contributors, and its description or topics contain at least one of `signoff`, `locking`, `checklist`, `authorization`, `close`
- **THEN** it receives a score ≥7 and `domain_areas` includes the matched keywords

#### Scenario: Low-activity repo
- **WHEN** a repo has <5 commits in 90 days and no domain keywords
- **THEN** it receives a score ≤2 and is placed at the end of the index

#### Scenario: Repo with domain keywords but low activity
- **WHEN** a repo matches domain keywords but has <5 commits
- **THEN** keyword match contributes +2 to score regardless of activity; the repo is still included

### Requirement: Support manual priority overrides
The system SHALL allow developers to annotate entries in `repo_priority_index.yaml` with a `manual_priority` field that, when present, overrides the computed score for ordering purposes.

#### Scenario: Manual override applied
- **WHEN** an entry in the YAML has `manual_priority: 1` and its computed score would rank it 15th
- **THEN** on the next `build_repo_index.py` run, the entry's position reflects `manual_priority` and a `rationale` note indicates it was manually pinned

#### Scenario: Re-run preserves manual overrides
- **WHEN** `build_repo_index.py` is run again after a developer added `manual_priority` to an entry
- **THEN** the field is preserved and not overwritten by the new computed score
