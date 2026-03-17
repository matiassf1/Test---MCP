## 1. Models & Config

- [x] 1.1 Add `confluence_base_url: str = ""` and `confluence_token: str = ""` to `Settings` in `src/config.py`
- [x] 1.2 Add `risk_level: Optional[str] = None`, `risk_points: int = 0`, `risk_factors: list[str] = []`, and `spec_violations: list[str] = []` to `PRMetrics` in `src/models.py`

## 2. ConfluenceService

- [x] 2.1 Create `src/confluence_service.py` with `ConfluenceService` class initialized with `base_url` and `token`; return empty results and log debug when credentials are absent
- [x] 2.2 Implement `get_pages_for_ticket(ticket_key) -> list[ConfluencePage]`: call Jira `GET /rest/api/3/issue/{key}/remotelink`, filter links whose URL matches `confluence_base_url`, extract page IDs
- [x] 2.3 Implement URL extraction fallback: parse ticket description text with regex for Confluence URLs when remoteLinks returns 0 results
- [x] 2.4 Implement `get_page_content(page_id) -> Optional[str]`: call `GET /wiki/rest/api/content/{id}?expand=body.storage`, strip HTML with `html.parser`, normalize whitespace; return None on 404/403 with a warning log
- [x] 2.5 Enforce max 5 pages per PR: slice the discovered page list before fetching; log a debug message when pages are skipped

## 3. RiskAnalyzer

- [x] 3.1 Create `src/risk_analyzer.py` with `compute_risk(metrics: PRMetrics, prod_diff: str, test_diff: str) -> tuple[str, int, list[str]]` returning `(risk_level, risk_points, risk_factors)`
- [x] 3.2 Implement `_auth_signal(prod_diff, files_summary)`: match file names and diff content against auth/signoff/permission/guard/authorize patterns; return `(triggered: bool, evidence: str)`
- [x] 3.3 Implement `_flag_signal(prod_diff, test_diff)`: extract feature flag identifiers from prod diff; check if any appear in test diff; return list of untested flag names
- [x] 3.4 Implement `_behavioral_ratio(prod_diff)`: count added lines matching conditional patterns (if/else/return/&&/||/ternary) divided by total added lines
- [x] 3.5 Implement `_role_gap(prod_diff, test_diff)`: extract role/entity string literals from prod diff; check coverage in test diff; return missing role names
- [x] 3.6 Implement point accumulation and threshold logic: HIGH ≥ 5, MEDIUM 3–4, LOW < 3; build `risk_factors` list with one human-readable string per triggered signal
- [x] 3.7 Implement LLM upgrade logic: accept optional `llm_risk_suggestion: Optional[str]`; allow one-step upgrade (LOW→MEDIUM, MEDIUM→HIGH); never downgrade

## 4. Doc-Aware Analysis Context

- [x] 4.1 Add `build_confluence_context(pages: list[ConfluencePage], budget: int = 6000) -> str` in `src/confluence_service.py`: concatenate pages in priority order, truncate each to remaining budget, append `[truncated]` marker when cut
- [x] 4.2 Add `_inject_confluence_context(prompt: str, context: str) -> str` in `src/ai_reporter.py`: prepend `## Business specification context` block before the diff section when `context` is non-empty
- [x] 4.3 Add `_extract_spec_violations(ai_report: str) -> list[str]` in `src/report_generator.py`: parse `### Spec vs Implementation` section bullets from the LLM report; return empty list when section is absent

## 5. Pipeline Integration

- [x] 5.1 Inject `ConfluenceService` into `PRAnalysisPipeline.__init__` with a default that reads from `settings`; make it optional (None disables fetching)
- [x] 5.2 Add Confluence fetch step in `PRAnalysisPipeline.analyze()` after Jira ticket resolution: call `confluence_service.get_pages_for_ticket()` when credentials are configured, build context string, store in a local variable
- [x] 5.3 Pass Confluence context string to `ai_reporter` call so it can inject it into the prompt
- [x] 5.4 Add risk scoring step after `ChangeAnalyzer` + `TestDetector`: call `compute_risk()` with prod diff and test diff; assign results to `metrics.risk_level`, `metrics.risk_points`, `metrics.risk_factors`
- [x] 5.5 After AI report is generated, call `_extract_spec_violations()` and assign to `metrics.spec_violations`; apply LLM risk upgrade if `risk_level_suggestion` is found in the report

## 6. Report & Output

- [x] 6.1 Update `_score_badge` / report header in `src/report_generator.py` to render risk badge alongside score: `Score: X / 10 (Fair) | Risk: ⚠️ HIGH`; skip badge when `risk_level` is None
- [x] 6.2 Add `## Risk Signals` section to PR markdown report when `risk_level` is MEDIUM or HIGH and `risk_factors` is non-empty
- [x] 6.3 Add `## Spec Violations` section to PR markdown report when `spec_violations` is non-empty
- [x] 6.4 Add `Risk` column to epic PR table in `_epic_markdown()` showing the risk badge per PR
- [x] 6.5 Include `risk_level`, `risk_points`, `risk_factors`, `spec_violations` in all MCP tool responses that return PR metrics (`analyze_pr`, `analyze_pr_by_jira_ticket`, `get_pr_metrics`, `batch_analyze_*`)

## 7. Verification

- [x] 7.1 Test with CLOSE-12083 (PR #4377): verify `risk_level = HIGH` is computed from static heuristics without AI key
- [x] 7.2 Test with a no-risk PR (e.g. CLOSE-12510 / PR #124): verify `risk_level = LOW` and no `## Risk Signals` section in report
- [x] 7.3 Test graceful degradation: unset `CONFLUENCE_BASE_URL` and verify analysis completes normally with `spec_violations = []`
- [ ] 7.4 Test Confluence fetch with a real ticket that has remoteLinks: verify page content appears in the LLM prompt context
