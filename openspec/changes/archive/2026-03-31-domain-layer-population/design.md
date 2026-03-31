## Context

The domain knowledge pipeline (`src/domain_knowledge_pipeline.py`) exists and runs 5 phases (repo mining → Confluence mining → Jira mining → normalization → context generation), but phases 2 and 3 silently fail:

- **Confluence** (`search_pages_for_domain`): uses `CQL text ~ "term"` against `/rest/api/content/search`. When called from the pipeline with generic terms (e.g. "signoff", "checklist"), it returns 0 results because the CQL query is too narrow and does not target any specific Confluence space. The pipeline calls this method with file-path-derived terms rather than space-scoped queries.
- **Jira** (phase 3): the pipeline queries for issue type `Bug` and `Incident` only. The CLOSE project primary work items are `Story` and `Task`; bugs are rare. The query returns 0.
- **Feature flags**: Harness flag keys and custom `tlcModules` flags exist in the codebase (scattered across feature-flag service files, constants, and API gateway config) but are not mined. The `domain_context.md §4` is manually authored.
- **Repo prioritization**: no structured list of FloQast repos exists — the pipeline accepts a single `--repo` argument and has no concept of batch ordering.

All four gaps mean the domain layer is static and manually maintained, with stale/empty artifact files that undermine the tool's credibility with new team members.

## Goals / Non-Goals

**Goals:**
- Fix Confluence bulk mining: add `search_by_space` and `search_by_label` methods to `ConfluenceService`; update pipeline phase 2 to use space-scoped CQL
- Fix Jira bulk mining: expand issue type filter; add project-level bulk extraction to `jira-invariant-extractor`
- Add repo priority index: static YAML + discovery script that ranks FloQast repos by domain criticality and integration density
- Add feature flag extractor: grep-based scanner over GitHub file trees for Harness flag constants and `tlcModules` config entries; no Harness API dependency (optional)
- Add domain-context enrichment phase: merge mined artifacts into `domain_context.md` sections §1, §4, §6, §10 using append/replace logic
- Add `refresh_domain` CLI command: wraps all phases with FloQast-org defaults

**Non-Goals:**
- Real-time flag evaluation or Harness SDK integration (flag keys only, not runtime values)
- Changes to MCP tools, scoring engine, or report generation
- Automated CI/CD scheduling (scope: CLI command + README instructions for cron)
- Full rewrite of `domain_context.md` — enrichment is additive and does not overwrite existing manual content

## Decisions

### D1 — Confluence mining strategy: space-scoped CQL over keyword-only search

**Decision:** Add `search_by_space(space_key, query_terms, max_results)` and `search_by_label(label, max_results)` to `ConfluenceService`. Pipeline phase 2 calls `search_by_space` for each configured space in `CONFLUENCE_SPACES` (e.g. `ENG`, `CLOSE`, `ARCH`) plus the existing keyword fallback.

**Alternatives considered:**
- *Fix existing CQL query*: patching the existing method's query terms is insufficient — without a space scope, results from unrelated products pollute the output.
- *Confluence REST API v2*: more verbose, pagination differs; v1 CQL endpoint is stable and matches existing code patterns.

**Rationale:** Space-scoped CQL is the standard Confluence search pattern for bulk domain mining. Adding it as new methods (not replacing) preserves the existing ticket-linked fetch behavior for PR analysis.

### D2 — Jira bulk mining: broaden to Story/Task/Bug/Incident/Epic

**Decision:** Change the Jira mining JQL filter from `issuetype in (Bug, Incident)` to `issuetype in (Story, Task, Bug, Incident, Epic) AND project = {project}`. Add a `max_tickets` cap (default 100) with `ORDER BY updated DESC` to get recent tickets first.

**Alternatives considered:**
- *Keep Bug/Incident only*: the existing filter is correct in principle but FloQast's CLOSE project tracks domain rules in Stories and Epics, not bugs. Keeping the filter means 0 results indefinitely.
- *No type filter*: returns too many unrelated tickets (sub-tasks, ops tickets). Capped broad filter is the right balance.

### D3 — Feature flag extraction: static grep over GitHub, not Harness API

**Decision:** Implement `FeatureFlagExtractor` as a GitHub file tree scanner that searches for:
1. Harness flag key patterns: `FEATURE_FLAG_KEY = "close_..."`, `useFeatureFlag("close_...")`, flag constant files under `feature-flags/` or `constants/featureFlags.ts`
2. tlcModules patterns: `tlcModules["<module>"]`, `getTlcModule("<name>")`, module registry files

Output: `domain_knowledge/feature_flags.md` — a flat list of `flag-key → owning module → description (if found in comments)`.

**Alternatives considered:**
- *Harness API*: would give flag metadata (default on/off, environments, tags) but requires a Harness API key, adds an external dependency, and Harness rate-limits bulk queries. Flag keys from source are sufficient for the risk heuristics use case.
- *AST parsing*: too fragile across TypeScript, Python, and Go files in the org. Regex grep over file contents is robust enough for identifier extraction.

### D4 — Repo priority index: static YAML seeded by GitHub API metrics

**Decision:** `scripts/build_repo_index.py` queries the FloQast GitHub org for repos, ranks them by: (1) commit count last 90 days, (2) number of unique contributors, (3) presence of domain keywords (`signoff`, `locking`, `checklist`, `authorization`) in repo description/topics. Output: `domain_knowledge/repo_priority_index.yaml` — an ordered list with fields: `repo`, `priority`, `rationale`, `domain_areas[]`.

**Alternatives considered:**
- *Fully manual YAML*: faster to bootstrap but drifts immediately. Seeding from GitHub API + manual override annotations is sustainable.
- *Dependency graph analysis*: would require cloning all repos to build an import graph. Out of scope for this change.

### D5 — Domain-context enrichment: section-aware append with guard markers

**Decision:** `DomainContextEnricher` reads `domain_context.md`, locates sections by `## N.` header pattern, and either appends new entries (for §6 Failure Patterns, §4 Feature Flags) or rewrites sub-sections inside a `<!-- BEGIN MINED -->` / `<!-- END MINED -->` guard block so that manually authored content above the guard is never touched.

**Alternatives considered:**
- *Full LLM rewrite of domain_context.md*: risky — could overwrite carefully hand-tuned heuristics. Guard markers preserve manual content.
- *Separate file for mined content*: keeps `domain_context.md` clean but requires the heuristics engine to load two files; not worth the complexity.

### D6 — `refresh_domain` CLI command: thin wrapper, FloQast defaults

**Decision:** Add `refresh_domain` to `src/cli.py` with flags: `--jira-project` (default `CLOSE`), `--confluence-spaces` (default from `CONFLUENCE_SPACES` env), `--repos-file` (default `domain_knowledge/repo_priority_index.yaml`), `--enrich/--no-enrich`. Calls existing pipeline + new extractors in sequence.

## Risks / Trade-offs

- **Confluence space discovery** → the pipeline needs `CONFLUENCE_SPACES` configured. If not set, falls back to keyword-only search (existing behavior). Mitigation: default to `["~CLOSE", "ENG"]` which covers the most likely spaces; document in `.env.example`.
- **Jira broad query returns noise** → 100 tickets from CLOSE may include unrelated process tickets. Mitigation: the existing Jira mining LLM prompt already filters for domain-relevant content; noise is pruned at the LLM summarization step.
- **Feature flag grep produces false positives** → strings that look like flag keys but are tests or comments. Mitigation: filter out files under `__tests__/`, `*.test.ts`, `*.spec.ts`; require the key to match the `close_` or `tlcModules` prefix convention.
- **Enrichment guard markers conflict with manual edits** → if a developer manually edits content inside a `<!-- BEGIN MINED -->` block, the next enrichment run overwrites it. Mitigation: document that content inside guard blocks is machine-generated; manual additions go above the guard.
- **GitHub API rate limits during repo index build** → scanning all org repos for commit counts can hit secondary rate limits. Mitigation: `build_repo_index.py` uses `per_page=100` with a configurable `--max-repos` cap (default 50) and sleeps 1s between requests.

## Migration Plan

1. Add new methods to `ConfluenceService` and `JiraService` — no behavior change to existing paths
2. Add `FeatureFlagExtractor` and `RepoPriorityIndexBuilder` as standalone modules in `src/`
3. Update `DomainKnowledgePipeline.build()` to call new phases when inputs available; old phases still run
4. Add `DomainContextEnricher` with guard-marker support; run as optional final phase
5. Add `refresh_domain` CLI command
6. Run `python -m src.cli refresh_domain` manually to validate outputs
7. Review generated `domain_knowledge/*.md` and `domain_context.md` enrichments; commit to repo
8. Update `.env.example` with new keys; update README

No rollback required — all changes are purely additive. If enrichment produces bad output, delete the `<!-- BEGIN MINED --> ... <!-- END MINED -->` blocks and re-run with fixed prompts.

## Open Questions

- **Which Confluence spaces to target first?** — `ENG` and `CLOSE` are assumed but need confirmation against the actual Floqast Confluence structure. If spaces differ, `CONFLUENCE_SPACES` env var will need to be set explicitly.
- **Harness API key availability?** — If a Harness API key is available, phase 2 of the flag extractor could enrich keys with default-on/off values. Design supports this as an optional enhancement after the grep-based baseline is working.
- **tlcModules registry location?** — Exact file paths for the tlcModules registry (likely in `close` repo under `src/constants/` or a module-config file) need to be confirmed before writing the grep patterns.
