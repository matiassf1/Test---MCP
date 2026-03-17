## Context

The tool currently detects *testing quality* (coverage estimates, test/code ratio, risk heuristics) but has a blind spot: **semantic correctness of ported logic**. When a developer copies a pattern from one module to another (e.g. `recs-client` → `checklist-client`), guards that were valid in the source domain may be incorrect in the target domain. These bugs pass all tests — because the tests were also copied or don't exercise the wrong guard path — and only surface in production.

Four independent detection layers are added, each targeting a specific signal source. All are optional and degrade gracefully (return empty results) when their data source is unavailable.

## Goals / Non-Goals

**Goals:**
- Detect ported/copied code blocks within a PR diff and flag them for domain-adaptation review
- Extract domain constraints from Jira ticket descriptions (porting signals like "parity", "based on")
- Fetch sibling-module files from GitHub to give the LLM reference implementations
- Derive always-true invariants from existing test files to validate production guards
- Inject all findings into the LLM prompt alongside existing Confluence context
- Surface findings in a dedicated **Business Rule Risks** section in the PR report
- Remain fully agnostic — zero hardcoded domain terms, module names, or business rules

**Non-Goals:**
- Full AST-based semantic analysis (too complex, language-specific)
- Cross-org or cross-company repo access
- Auto-fixing mismatched guards
- Detecting bugs that require runtime execution to observe

## Decisions

### D1: Use difflib.SequenceMatcher for copy detection (not AST)

**Decision**: Use stdlib `difflib.SequenceMatcher` to compare normalized code blocks (strip comments, whitespace) across files in the diff. Flag pairs with similarity ≥ 0.75.

**Why over AST**: AST requires language-specific parsers (JS, TS, Python vary). difflib is language-agnostic, zero-dependency, and fast enough for diff-sized inputs. False positives are acceptable — the LLM does the final judgment.

**Threshold 0.75**: Empirically covers near-verbatim copies while excluding incidental similarity (e.g. two `if (!x)` lines).

---

### D2: Jira invariant extraction via regex + keyword scoring

**Decision**: Scan the ticket description for porting signal phrases (`parity`, `based on`, `similar to`, `ported from`, `replicate`, `match behavior`) using regex. Also extract explicit constraint statements (sentences containing `must`, `always`, `never`, `should not`) and pass them as a structured list to the LLM.

**Why not LLM-first**: Ticket descriptions are short and structured; regex is deterministic and free. LLM is used downstream to *interpret* the extracted constraints, not to find them.

---

### D3: Cross-repo sibling detection via path-based module inference

**Decision**: Infer the "module name" from file paths in the diff (e.g. `ui/checklist-client/src/helpers/signoffs.js` → module `checklist-client`, relative path `src/helpers/signoffs.js`). Discover sibling modules by listing `ui/*/` directories in the same repo. Fetch the same relative path from each sibling via GitHub API (contents endpoint). Cap at 3 sibling files, 3000 chars each.

**Why path-based inference**: Avoids needing any configuration or domain knowledge. The module boundary is wherever the path segment changes — fully agnostic.

**Why same repo only**: Cross-org fetches require additional auth scopes and latency. Sibling modules in the same repo are the most common source of ported patterns.

---

### D4: Test invariant extraction via frequency analysis

**Decision**: For each production file touched in the diff, find its test counterpart(s) (already resolved by `file_classification`). Scan all `describe`/`it`/`test` blocks in the repo's cached test files for the same module. Extract property-value pairs that appear in ≥ 80% of test cases for a given function (e.g. `isWorkflow: true` in 9/10 tests for `isAuthorizedForSignoff` → invariant). Surface as: `"In <module>, <property> is always <value> in tests"`.

**Why 80% threshold**: Guards against coincidental uniformity in small test suites while still catching genuine invariants. Configurable via `TEST_INVARIANT_THRESHOLD` env var (default `0.8`).

---

### D5: Injection order in LLM prompt

**Decision**: Inject in this order (most stable → most dynamic):
1. Confluence doc context (existing)
2. Jira invariants + porting signals
3. Test-derived invariants
4. Cross-repo sibling reference implementations
5. Copy-detection flags

**Why**: The LLM performs better when business context precedes code examples. Copy flags come last because they reference specific line ranges the LLM has already seen in the diff.

---

### D6: All layers return `BusinessRuleContext` dataclass

**Decision**: Each layer returns a `BusinessRuleContext` (dataclass with fields: `copy_flags`, `jira_invariants`, `sibling_refs`, `test_invariants`). The pipeline merges them and passes a single object to the prompt builder.

**Why**: Keeps `pr_analysis_pipeline.py` clean — one integration point regardless of which layers are enabled.

## Risks / Trade-offs

- **False positives from copy detection** → The LLM is explicitly prompted to confirm whether flagged similarity is a real domain mismatch, not just a structural one. Users see "possible domain adaptation issue" not "bug confirmed".
- **GitHub rate limiting for sibling fetches** → Cap at 3 siblings × 3 GitHub API calls. Falls back gracefully (empty sibling list) on 403/429. Can be disabled with `ENABLE_CROSS_REPO_SIBLINGS=false`.
- **Test invariant false positives in small test suites** → The 80% threshold with a minimum of 3 test cases prevents spurious invariants. If fewer than 3 tests exist for a function, invariant extraction is skipped.
- **Performance** → All four layers are I/O-bound (GitHub API, file reads). They run after the existing change analysis step and before the LLM call — adding ~1–3s in the common case. No blocking the pipeline.
- **Noise in the LLM prompt** → The injected context is budget-capped at 4000 chars total (shared across all four layers). Truncation uses priority order: Jira invariants → test invariants → copy flags → sibling refs.

## Migration Plan

1. Add four new Python modules under `src/`
2. Add `BusinessRuleContext` dataclass to `src/models.py` or a new `src/business_rule_context.py`
3. Wire into `pr_analysis_pipeline.py` after the existing Confluence fetch step
4. Update `src/ai_reporter.py` to call `_inject_business_rule_context()`
5. Update `src/report_generator.py` to render the **Business Rule Risks** section
6. Add `ENABLE_CROSS_REPO_SIBLINGS` and `ENABLE_TEST_INVARIANTS` to `src/config.py`
7. No database or schema migrations needed
8. Rollback: set both env vars to `false` to disable all new layers with zero code change

## Open Questions

- Should `TEST_INVARIANT_THRESHOLD` be exposed in the UI/MCP tool response, or kept internal?
- Should sibling refs be limited to files modified in the PR, or all files touched by the module? (Current decision: PR files only — revisit if signal is too narrow.)
