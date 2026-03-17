## ADDED Requirements

### Requirement: Compute risk level from static heuristics without LLM dependency
The system SHALL compute `risk_level` (HIGH / MEDIUM / LOW) and `risk_points` from the PR diff alone, requiring no AI API key, using the following signals:

| Signal | Condition | Points |
|---|---|---|
| `auth_signal` | File name or diff contains auth/signoff/permission/guard/authorize patterns | +3 |
| `untested_flags` | Feature flag referenced in prod diff but not toggled in test diff | +2 |
| `behavioral_ratio` | >40% of added lines are conditional logic AND `testing_quality_score` < 6 | +2 |
| `cross_domain` | Diff imports or references patterns from a sibling domain | +1 |
| `role_gap` | ≥2 roles/entities in prod diff not present in test diff | +2; exactly 1 missing → +1 |

Thresholds: HIGH ≥ 5 pts, MEDIUM 3–4 pts, LOW < 3 pts.

#### Scenario: Authorization file with untested feature flag
- **WHEN** a PR modifies a file matching `*authorization*` and references a feature flag not toggled in any test file
- **THEN** `risk_points` = 5 (auth +3, flag +2), `risk_level` = HIGH

#### Scenario: Clean PR with no risk signals
- **WHEN** a PR modifies only configuration files with no conditional logic, no auth patterns, and no feature flags
- **THEN** `risk_points` = 0, `risk_level` = LOW

#### Scenario: Medium risk — behavioral change with moderate score
- **WHEN** a PR has 45% behavioral change ratio and `testing_quality_score` of 5.5 but no auth patterns or flag usage
- **THEN** `risk_points` = 2, `risk_level` = LOW (threshold not met for MEDIUM)

### Requirement: Produce a risk_factors list with concrete justification
The system SHALL populate `risk_factors` as a list of human-readable strings, one per triggered signal, each naming the signal and its evidence from the diff.

#### Scenario: Multiple signals triggered
- **WHEN** `auth_signal` and `untested_flags` both trigger
- **THEN** `risk_factors` contains at least two items, e.g. `"Authorization logic modified — signoffAuthorization.js"` and `"Feature flag 'close_entity-settings_separate-strict-sign-off' not toggled in tests"`

### Requirement: LLM risk suggestion can upgrade but not downgrade computed level
The system SHALL allow the LLM-extracted `risk_level_suggestion` to upgrade the static risk level by one step (LOW→MEDIUM, MEDIUM→HIGH) but SHALL NOT allow it to downgrade.

#### Scenario: LLM suggests higher risk
- **WHEN** static heuristics compute MEDIUM and the LLM suggests HIGH
- **THEN** final `risk_level` = HIGH

#### Scenario: LLM suggests lower risk
- **WHEN** static heuristics compute HIGH and the LLM suggests LOW
- **THEN** final `risk_level` = HIGH (static result preserved)

#### Scenario: No LLM available
- **WHEN** no AI key is configured and `ai_report` is None
- **THEN** `risk_level` is set from static heuristics only; no error is raised
