## Context

The tool's pipeline (`PRAnalysisPipeline`) already follows a service-injection pattern: `GitHubService`, `JiraService`, `ChangeAnalyzer`, `TestDetector` are all constructed independently and composed in the pipeline. The AI layer (`ai_reporter.py`) receives a `PRMetrics` object and builds a prompt from it.

The Jira integration already authenticates via `JIRA_URL` + `JIRA_API_TOKEN` using Basic Auth over `requests`. Confluence is on the same Atlassian instance and uses the same credentials — no new auth mechanism needed.

Current constraint: the LLM prompt is built entirely from structured `PRMetrics` fields. There is no mechanism to inject free-text documentation into it.

## Goals / Non-Goals

**Goals:**
- Fetch Confluence pages linked to a Jira ticket and pass their content as context to the LLM
- Compute a `risk_level` (HIGH / MEDIUM / LOW) from static code signals, independent of AI availability
- Surface spec violations and risk level in all existing outputs (MCP tools, reports, epic summaries)
- Remain fully backwards compatible — feature is a no-op when `CONFLUENCE_TOKEN` is absent

**Non-Goals:**
- Indexing or caching the full Confluence space
- Parsing Confluence diagrams or image attachments (ERD images are out of scope; only text content)
- Building a custom UI or dashboard
- Replacing the existing `testing_quality_score` — risk level is additive

## Decisions

### 1. Confluence service follows the same pattern as JiraService

`ConfluenceService` is a plain class initialized with `base_url` and `token` from settings. It uses the existing `requests` dependency. Injected into `PRAnalysisPipeline` alongside `JiraService`.

**Why**: Consistent with the codebase's service injection pattern. Easy to mock in tests. No new architectural concept introduced.

**Alternative considered**: A standalone function module (no class). Rejected because the pipeline already uses class instances for all services, and a class allows holding the session and base URL once.

---

### 2. Document discovery: remoteLinks first, description URL extraction as fallback

Primary path: call `GET /rest/api/3/issue/{key}/remotelink` (already used by `jira_service.py` for other purposes) to find Confluence pages explicitly linked from the Jira ticket.

Fallback: extract Confluence URLs embedded in the ticket description text using a regex against the `CONFLUENCE_BASE_URL` domain.

**Why**: remoteLinks is reliable and structured. The fallback catches docs that teams link inline in the description without using Jira's formal link feature — common in practice.

**Alternative considered**: Searching Confluence by ticket key (`CQL: text ~ "CLOSE-12083"`). Rejected as primary because CQL text search returns too many false positives and is slow. Kept as a last-resort option configurable in `config.yaml`.

---

### 3. Content truncation strategy: priority order + char budget

Total char budget for Confluence context in the LLM prompt: **6 000 characters** (roughly 1 500 tokens, leaving room for diff and ticket description).

Priority order when multiple docs are found:
1. Pages explicitly linked to the ticket (remoteLinks)
2. Pages found via description URL extraction
3. ERD page for the domain (from `config.yaml` path mapping, if present)

Each page is truncated to `min(page_chars, remaining_budget)`. If a page exceeds its share, the first N characters are used with a `[truncated]` marker.

**Why**: The LLM prompt already contains the full diff and ticket description. Confluence content is supplementary context, not the primary signal. Exceeding the context window degrades all analysis quality.

**Alternative considered**: Summarizing each page with a separate LLM call before injecting. Rejected — doubles LLM calls and cost. The LLM can extract what's relevant from a truncated raw text.

---

### 4. Risk scoring: static heuristics always run; LLM signals are additive

`risk_analyzer.py` computes risk from the diff text alone, with no LLM dependency:

```
auth_signal        → +3 pts  (file names or patterns match auth/signoff/permission/guard)
untested_flags     → +2 pts  (feature flag in prod code with no toggle in test diff)
behavioral_ratio   → +2 pts  (>40% of added lines are conditional logic AND score < 6)
cross_domain       → +1 pt   (imports or references from sibling domain detected in diff)
role_gap           → +1–2 pts (entities/roles in prod diff not exercised in test diff)
```

When LLM output is available, structured fields (`spec_violations`, `risk_level_suggestion`) from the AI report can upgrade the computed level one step (LOW→MEDIUM or MEDIUM→HIGH), never downgrade.

Final: `HIGH` ≥ 5 pts, `MEDIUM` 3–4 pts, `LOW` < 3 pts.

**Why**: Risk scoring must work even without AI keys. Static heuristics on the diff are always available and provide immediate value. LLM refinement is a bonus, not a dependency.

**Alternative considered**: Risk level derived entirely from the LLM output. Rejected — makes risk scoring unavailable when no API key is configured, and LLMs can be inconsistent on classification tasks without structured output constraints.

---

### 5. No new config file format — env vars only for v1

`CONFLUENCE_BASE_URL` and `CONFLUENCE_TOKEN` added to `Settings` (pydantic-settings, `.env`). The optional `config.yaml` (domain path → page ID mappings) is deferred to a follow-up change.

**Why**: The config.yaml adds complexity (file discovery, schema validation, parsing) that is not needed to deliver the core value. Most teams can benefit from remoteLinks-based discovery without any per-repo config. The `config.yaml` feature is noted in Open Questions.

---

### 6. LLM prompt: inject Confluence content as a new context block, not replacing existing sections

The existing prompt structure (`_SYSTEM_PROMPT` + PR metrics block) is preserved. Confluence content is appended as a new section before the diff:

```
## Business specification context
<page title>
<truncated content>
...

Validate the implementation against these specifications. For each violation or gap, quote the spec and the relevant diff line.
```

**Why**: Minimal invasiveness — the existing prompt logic, section structure, and output format are unchanged. Confluence context is opt-in enrichment.

## Risks / Trade-offs

**Confluence API rate limits** → Mitigation: fetch is bounded to ≤5 pages per PR. Pages are not cached between runs in v1 (acceptable given low call frequency in current usage patterns).

**HTML content quality** → Confluence pages contain HTML, macros, and Jira-specific markup. Stripping produces readable but sometimes fragmented text. Mitigation: use `html.parser` (stdlib, no new dependency) to extract visible text; accept some noise as the LLM handles it well.

**Doc staleness** → A Confluence page linked to a ticket may be outdated relative to the actual implementation. Mitigation: the LLM prompt instructs the model to flag contradictions rather than assume the doc is ground truth.

**No ERD image parsing** → Architecture diagrams are often images in Confluence. Text-only extraction misses them. Mitigation: accepted as out of scope for v1. Teams can add text descriptions to their ERD pages as a workaround.

**Context window pressure** → Injecting 6 000 chars of Confluence content alongside a large diff may degrade output quality. Mitigation: the 6 000 char budget was chosen conservatively. If the diff exceeds the model's context, the existing diff-truncation logic (already present in `ai_reporter.py`) handles it.

## Open Questions

- Should `config.yaml` (domain path → Confluence page ID) be implemented in v1 or deferred? Currently deferred — revisit if teams report that remoteLinks discovery misses their key ERD pages.
- Should fetched Confluence content be persisted alongside `PRMetrics` for audit/replay? Currently not stored — adds storage complexity without clear immediate need.
- Should `risk_level` be included in the `testing_quality_score` blend or remain fully separate? Currently separate — mixing them would make the score harder to interpret.
