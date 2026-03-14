# Review: Workflow & Epic flows — optimizations and trade-offs

## 1. Current state: integrated flows

### 1.1 Workflow doc generation (`generate_workflow_docs`)

| Step | What it does |
|------|----------------|
| Input | `--epics` (comma-separated), optional `--repo`/`--org`, `--output`, `--title`, `--intro`, `--storage` |
| Jira | For each Epic: `fetch_issue(epic_key)` (summary, description, priority) + `fetch_epic_issues(epic_key)` (children with **description** via `_normalize_description`) |
| Optional PR layer | If `--repo` or `--org`: for each Epic calls `_discover_epic_prs`, then for each `(repo, pr_number)` loads `storage.load(pr_number)` and builds `prs_by_epic` (title, ticket, ai_summary) |
| Output | Single Markdown: Epic sections (summary, description, child tickets table + “Ticket descriptions”, optional “Implementation (PRs)” table) |

**Design choices today**

- Child tickets: Stories first, then Task, Bug (hardcoded `_CHILD_TYPE_ORDER`). Epic priority: Critical → High → Medium → Low.
- PRs: one table per Epic; no grouping by ticket inside the Epic (all PRs for that Epic in one list).
- Storage: `load(pr_number)` only — no `(repo, pr_number)` key.

---

### 1.2 Scope alignment (Epic report + PR report)

| Where | What |
|-------|------|
| **AI report (PR)** | Section “### 3. Scope vs ticket” in `ai_reporter`; prompt includes Jira summary + description; model flags aligned / out of scope / different from spec. |
| **Epic report** | “Scope alignment overview” table (PR, Ticket, Scope status); “Scope concerns” subsection with extracted text; “Areas for Improvement” includes “scope concerns” as a reason; PR Details include “Scope vs ticket” line. |
| **Extraction** | `_extract_scope_alignment(ai_report)`, `_scope_status(scope_text)` — heuristic (keywords + bullets). |

**Design choices today**

- Section number is fixed (“### 3. Scope vs ticket”); if report structure changes, extraction can break.
- Scope status is keyword-based; no confidence or nuance (e.g. “partially aligned”).

---

### 1.3 Epic report (`analyze_epic` / `regenerate_epic_report`)

- Discovery: `_discover_epic_prs(epic_key, repo, org)` → Jira Epic + children, GitHub search by ticket keys.
- Metrics: from pipeline (analyze) or storage (regenerate).
- Report: Summary, PR Table, Scope alignment overview, Well-covered, Areas for Improvement, General recommendations, PR Details.

---

## 2. Friction points and risks

| Issue | Impact | Where |
|-------|--------|--------|
| **Storage keyed by `pr_number` only** | With `--org`, multiple repos can have the same PR number; `load(pr_number)` returns a single record. Workflow doc and regenerate can show wrong repo/title or duplicate the same PR. | `storage.py`, `cmd_generate_workflow_docs`, `cmd_regenerate_epic_report` |
| **Duplicate PR discovery** | For N Epics with `--repo`/`--org`, we call `_discover_epic_prs` N times; same PR can appear in several Epics and be fetched multiple times from GitHub. | `cmd_generate_workflow_docs` |
| **Fragile section markers** | Scope, Summary, Recommendations depend on exact “### 3.”, “### 1. Summary”, “### 8. Testing Recommendations”. Renumbering or prompt change breaks extraction. | `report_generator.py` (`_extract_scope_alignment`, `_extract_ai_summary`, `_extract_ai_recommendations`) |
| **Workflow doc: PRs not grouped by ticket** | Implementation table lists all PRs for the Epic; no “per ticket” view. Harder to see which PR implements which Story/Task. | `workflow_doc_markdown` |
| **Heuristic scope status** | “aligned” vs “issues” is keyword + bullet; can misclassify (e.g. “Aligned with one out-of-scope fix”). | `_scope_status` |
| **Child type order hardcoded** | Only Story/Task/Bug; other types (Subtask, Sub-task) fall to “other”. | `_CHILD_TYPE_ORDER` |

---

## 3. Optimizations and improvements (with trade-offs)

### 3.1 Storage: support `(repo, pr_number)` as key

**Change:** Add composite key (e.g. `(repo, pr_number)` for SQLite; directory/file `repo/pr_N.json` for JSON). New API: `load(repo, pr_number)` and optionally `load(pr_number)` for backward compatibility (e.g. single-repo default).

| Pros | Cons |
|------|------|
| Correct behavior with `--org` and multiple repos; no wrong/missing PR in workflow doc or Epic report. | Breaking change for existing storage (migration or new “v2” schema); CLI and callers must pass `repo` where needed. |
| One source of truth per PR across Epics. | Slightly more complex storage API. |

**Recommendation:** Plan as a **v2 storage** (new path or schema) and migrate callers (e.g. `regenerate_epic_report`, `generate_workflow_docs`) to use `(repo, pr_number)` when loading; keep `load(pr_number)` for single-repo or legacy.

---

### 3.2 Workflow doc: optional “PRs per ticket” view

**Change:** When building `prs_by_epic`, group by `jira_ticket` (from metrics). In the doc, under each Epic, add a subsection “Implementation by ticket” (or keep a single table but add a “Ticket” column and sort by ticket). Optionally, under “Child tickets”, add a line “PRs: #123, #456” per child when we have matches.

| Pros | Cons |
|------|------|
| Clearer mapping: which PRs implement which Story/Task. | Slightly more logic and section nesting; need to handle PRs with no/multiple tickets. |
| Aligns with “core workflows = children of Epic”. | |

**Recommendation:** **Low effort.** Add “Implementation (PRs)” table sorted by ticket (or grouped); optionally add “PRs” cell/link next to each child in the child table when we have data.

---

### 3.3 Extraction: robust section detection

**Change:** Instead of fixed “### 3. Scope vs ticket”, search for headings that contain “Scope” and “ticket” (e.g. regex or normalized title). Same idea for Summary and Recommendations (e.g. “Summary”, “Testing Recommendations”). Prefer structure (heading level + title) over exact numbering.

| Pros | Cons |
|------|------|
| Survives renumbering (e.g. 3 → 4) or small prompt wording changes. | Slightly more complex; possible false positives if multiple sections match. |
| Fewer silent breakages when prompt evolves. | |

**Recommendation:** **Medium effort.** Implement for Scope first (most critical for Epic), then Summary and Recommendations. Keep fallback to current markers for old reports.

---

### 3.4 Scope status: optional LLM or structured output

**Change:** Either (a) ask the model to output a structured “scope_status” (e.g. aligned / issues / no_ticket) in addition to free text, or (b) keep heuristic but add “partial” or “unknown” and use it in the Epic report (e.g. “⚠️ Review” instead of binary Issues/Aligned).

| Pros | Cons |
|------|------|
| (a) More reliable than keyword parsing. (b) Safer than forcing binary. | (a) Requires prompt + response parsing change; possible extra token/cost. (b) Heuristic still imperfect. |
| Fewer misclassifications. | |

**Recommendation:** **Defer** until scope section is heavily used. Short term: document heuristic limits; optionally add “partial” in `_scope_status` when text is ambiguous.

---

### 3.5 Deduplicate PR discovery when multiple Epics

**Change:** When `generate_workflow_docs` is called with several Epics and `--repo`/`--org`, discover PRs once per `(repo, pr_number)` (e.g. set or dict), then map each PR to Epics via ticket (Epic key or child key). Build `prs_by_epic` from that map.

| Pros | Cons |
|------|------|
| Fewer GitHub API calls; consistent view of “which PR belongs to which Epic”. | Need to map ticket → Epic (ticket can be Epic key or child key; children already tell us Epic). |
| Faster when many Epics. | |

**Recommendation:** **Medium effort.** Implement when workflow doc is used with 3+ Epics or when rate limits matter. Requires resolving ticket → Epic (from Jira children or from PR title/branch).

---

### 3.6 Child type order configurable or extended

**Change:** Make `_CHILD_TYPE_ORDER` configurable (e.g. env or config file) or add common types (Subtask, Sub-task, etc.) so “principal” workflows are still listed first.

| Pros | Cons |
|------|------|
| Adapts to Jira project types without code change. | More config to maintain; default must stay sensible. |
| Fewer “other” at the end. | |

**Recommendation:** **Low effort.** Add 1–2 common types (e.g. `Subtask`) with order after Task; defer full configurability until needed.

---

### 3.7 Single “Epic + workflow doc” flow

**Change:** New command or flag, e.g. `analyze_epic --output-workflow-doc`, or `generate_workflow_docs --epic X --repo R` (single Epic) that (1) runs discovery + analysis (or uses storage) and (2) writes both Epic report and workflow doc (Epic + children + PRs) to chosen paths.

| Pros | Cons |
|------|------|
| One invocation for “full Epic view” (testing + scope + workflow doc). | More moving parts; need clear semantics (e.g. “always use storage for PR list”). |
| Better UX for “document this Epic”. | |

**Recommendation:** **Optional.** Add only if the team often wants both artifacts from one run; otherwise keep `analyze_epic` + `generate_workflow_docs --epics X --org Y` as two steps.

---

## 4. Suggested order of work (after review)

| Priority | Item | Effort | Trade-off |
|----------|------|--------|-----------|
| **P1** | Document storage limitation (pr_number only) in TEAM-INTRODUCTION or WORKFLOW-DOCS-DESIGN; recommend single-repo or one Epic at a time when using PR layer. | Low | No code change; avoids wrong expectations. |
| **P2** | Workflow doc: group or sort “Implementation (PRs)” by ticket; optionally link PRs to child rows. | Low | Clearer workflow narrative; minimal risk. |
| **P3** | Extraction: robust section detection for “Scope vs ticket” (and optionally Summary / Recommendations). | Medium | More resilient to prompt changes; keep fallback. |
| **P4** | Storage v2: composite key `(repo, pr_number)` + migration path. | High | Fixes multi-repo correctness; plan breaking change. |
| **P5** | Deduplicate PR discovery when generating workflow docs for multiple Epics. | Medium | Fewer API calls; needs ticket→Epic mapping. |
| **P6** | Scope status: add “partial”/“unknown” and/or document heuristic limits. | Low | Better honesty in report; no model change yet. |
| **P7** | Child type order: add Subtask (and optionally make configurable). | Low | Better ordering in some Jira setups. |

---

## 5. Summary

- **Workflow doc:** Epic + children (with descriptions) + optional PR table is coherent; main gaps are storage key (multi-repo) and PR↔ticket grouping.
- **Scope alignment:** Extraction and heuristic status work but are brittle (section numbers) and coarse (binary status); robustness and optional nuance are the next steps.
- **Epic report:** Reuse of `_discover_epic_prs` and scope extraction is good; same storage limitation applies.

Recommended next step after review: **implement P1 (docs) + P2 (PRs by ticket)** as quick wins; then decide whether to invest in P3 (extraction) and P4 (storage) based on usage (multi-repo, many Epics, prompt churn).
