## Why

Static heuristics and LLM analysis catch *how* code is tested but miss *whether the code correctly implements domain business rules* — especially when logic is ported from one module/repo to another with guards that are semantically wrong in the target domain. This class of bug passes all tests yet breaks production (e.g., a `!isWorkflow` guard copied from `recs-client` to `checklist-client` where all items are always workflow items).

## What Changes

- **New**: Intra-PR copy detector — identify near-duplicate code blocks across files in the same diff and ask the LLM to verify that guards and conditions were correctly adapted to the target domain.
- **New**: Jira description invariant extractor — parse ticket text for "parity", "based on", "ported from", "similar to" signals and surface extracted domain constraints as LLM context.
- **New**: Cross-repo sibling fetcher — when a PR touches a named client module (e.g. `checklist-client`), fetch equivalent files from sibling modules via GitHub API and inject as "reference implementation" context so the LLM can spot unadapted guards.
- **New**: Test-derived invariant validator — scan existing test files in the PR's repo for always-true conditions (e.g. `isWorkflow: true` in every `checklist` test) and surface them as domain invariants for the LLM to validate against production code guards.
- **Modified**: `pr-analysis-pipeline` — wire all four detection layers into the analysis pipeline; inject their outputs into the LLM prompt alongside Confluence context.
- **Modified**: `doc-aware-analysis` — extend the LLM prompt to include cross-repo reference implementations and test-derived invariants as additional validation context.
- **Modified**: `report-generation` — add a **Business Rule Risks** section to the PR report; surface copy-detection flags, violated invariants, and mismatched guards as actionable findings.

All layers are fully agnostic — no hardcoded domain names, module names, or business terms.

## Capabilities

### New Capabilities
- `copy-detector`: Detect near-duplicate code blocks within a PR diff and flag them for domain-adaptation review
- `jira-invariant-extractor`: Extract domain constraints and porting signals from Jira ticket descriptions
- `cross-repo-sibling-fetcher`: Fetch equivalent files from sibling modules via GitHub API to use as reference implementations
- `test-invariant-validator`: Derive always-true domain conditions from existing test files and surface as invariants for LLM validation

### Modified Capabilities
- `pr-analysis-pipeline`: Wire the four new detection layers; inject outputs into LLM prompt
- `doc-aware-analysis`: Extend LLM prompt schema to include reference implementations and test-derived invariants
- `report-generation`: Add Business Rule Risks section with copy-detection flags and invariant violations

## Impact

- **New files**: `src/copy_detector.py`, `src/jira_invariant_extractor.py`, `src/cross_repo_fetcher.py`, `src/test_invariant_validator.py`
- **Modified files**: `src/pr_analysis_pipeline.py`, `src/ai_reporter.py`, `src/report_generator.py`
- **Dependencies**: No new external dependencies — uses existing GitHub API client (`PyGithub`) and regex/difflib from stdlib
- **Performance**: Cross-repo sibling fetch adds 1–3 GitHub API calls per analysis; test-invariant scan adds a pass over cached file contents — both bounded and optional (degrade gracefully if disabled or rate-limited)
- **Config**: New optional env vars `ENABLE_CROSS_REPO_SIBLINGS=true` and `ENABLE_TEST_INVARIANTS=true` (default `true` when GitHub token present)
