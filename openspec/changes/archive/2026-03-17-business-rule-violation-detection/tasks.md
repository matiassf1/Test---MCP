## 1. Data Models

- [x] 1.1 Add `BusinessRuleContext` dataclass to `src/models.py` with fields: `copy_flags: list[dict]`, `jira_invariants: list[str]`, `test_invariants: list[str]`, `sibling_refs: list[dict]`
- [x] 1.2 Add fields to `PRMetrics`: `copy_flags`, `jira_invariants`, `test_invariants`, `business_rule_risks: list[str]`
- [x] 1.3 Add config fields to `src/config.py`: `enable_cross_repo_siblings: bool = True`, `enable_test_invariants: bool = True`, `test_invariant_threshold: float = 0.8`

## 2. Copy Detector

- [x] 2.1 Create `src/copy_detector.py` with `CopyDetector` class using `difflib.SequenceMatcher`
- [x] 2.2 Implement block extraction: split diff into contiguous non-trivial chunks ≥ 5 lines; normalize by stripping comments and collapsing whitespace
- [x] 2.3 Implement pairwise comparison across all files in the diff; flag pairs with similarity ≥ 0.75
- [x] 2.4 Implement guard extraction: regex for boolean guard expressions (`if (!x)`, `&& !x`, `|| x`) present in one block but absent/negated in the other; populate `differing_guards`
- [x] 2.5 Return empty list immediately when diff has fewer than 2 files with extractable blocks

## 3. Jira Invariant Extractor

- [x] 3.1 Create `src/jira_invariant_extractor.py` with `JiraInvariantExtractor` class
- [x] 3.2 Implement porting signal detection: case-insensitive regex scan for `parity`, `based on`, `ported from`, `similar to`, `replicate`, `match behavior`, `same as`, `mirror`; return `PortingSignal(phrase, context_sentence)`
- [x] 3.3 Implement domain constraint extraction: extract sentences containing `must`, `always`, `never`, `should not`, `shall`, `required`, `ensure`; include acceptance criteria bullets
- [x] 3.4 Return `JiraInvariantContext(porting_signals, domain_constraints)`; return empty context when description is None or empty

## 4. Cross-Repo Sibling Fetcher

- [x] 4.1 Create `src/cross_repo_fetcher.py` with `CrossRepoSiblingFetcher` class
- [x] 4.2 Implement module inference: detect common parent directory shared by ≥ 2 PR files; extract module segment and relative path per file
- [x] 4.3 Implement sibling discovery: list `<parent>/*/` directories using GitHub Trees API; exclude the source module
- [x] 4.4 Implement sibling file fetch: for each inferred relative path, attempt GitHub Contents API on up to 3 siblings; cap each file at 3 000 chars; handle 403/429 gracefully (log warning, return partial)
- [x] 4.5 Return empty `SiblingContext` immediately when `enable_cross_repo_siblings=False` or when no module structure is detected

## 5. Test Invariant Validator

- [x] 5.1 Create `src/test_invariant_validator.py` with `TestInvariantValidator` class
- [x] 5.2 Implement test file discovery: use existing `file_classification` to find test counterparts for each production file in the diff
- [x] 5.3 Implement property-value extraction: regex scan for `<property>: <literal>` and `<property>=<literal>` patterns inside `describe`/`it`/`test` blocks
- [x] 5.4 Implement frequency analysis: count unique property-value pairs per module across all test cases; promote to invariant when frequency ≥ `TEST_INVARIANT_THRESHOLD` AND ≥ 3 distinct test cases
- [x] 5.5 Return `TestInvariantContext(invariants)`; handle file read errors by logging and continuing; return empty context when `enable_test_invariants=False`

## 6. Pipeline Integration

- [x] 6.1 Wire all four detection layers into `src/pr_analysis_pipeline.py` after the diff analysis step and before the AI reporter call
- [x] 6.2 Merge layer results into a single `BusinessRuleContext` instance
- [x] 6.3 Catch exceptions from each layer individually; log and continue with empty partial result if any layer fails
- [x] 6.4 Store `copy_flags`, `jira_invariants`, `test_invariants` onto `PRMetrics` after merging

## 7. LLM Prompt Injection

- [x] 7.1 Add `_inject_business_rule_context(prompt, context)` function to `src/ai_reporter.py`
- [x] 7.2 Inject sections in priority order: Jira Domain Constraints → Test-Derived Invariants → Reference Implementations → Ported Code Flags
- [x] 7.3 Enforce 4 000-char total budget: truncate lowest-priority sections first (sibling refs → copy flags → test invariants → Jira constraints last)
- [x] 7.4 Instruct the LLM explicitly to flag any production guard that contradicts a test-derived invariant and to identify guards copied from sibling references that may not apply in the target domain
- [x] 7.5 Update `try_generate_report` to accept and pass `business_rule_context: BusinessRuleContext`

## 8. Business Rule Risk Extraction

- [x] 8.1 Add `_extract_business_rule_risks(ai_report)` to `src/report_generator.py` (parse `### Business Rule Risks` section from LLM output)
- [x] 8.2 Populate `PRMetrics.business_rule_risks` from extracted items after AI report is generated

## 9. Report Generation

- [x] 9.1 Add `_business_rule_risks_section(metrics)` renderer to `src/report_generator.py`; render `## Business Rule Risks` section with `[Copy Detected]`, `[Invariant Violation]`, `[Porting Signal]` prefixes when non-empty
- [x] 9.2 Add `BizRules` column to epic PR table: show `⚠️` when `business_rule_risks` is non-empty
- [x] 9.3 Include `business_rule_risks`, `copy_flags`, `jira_invariants`, `test_invariants` in all MCP tool response dicts that return PR metrics

## 10. Validation

- [x] 10.1 Re-run analysis on CLOSE-12083 (PR #4377): verify `copy_flags` detects the `signoffAuthorization.js` / `authorization.js` similarity
- [x] 10.2 Verify `jira_invariants` extracts "parity" signal from CLOSE-12083 ticket description
- [x] 10.3 Verify `test_invariants` derives `isWorkflow=true` (or equivalent) from checklist-client test files if present
- [x] 10.4 Verify `business_rule_risks` is populated in `PRMetrics` and appears in the markdown report
- [x] 10.5 Verify all new fields appear in the MCP tool JSON response
