## Why

The domain layer is the analytical foundation of the tool — it drives risk scoring, heuristic signals, and LLM prompt context — but it is critically underpopulated: Confluence and Jira mining both return 0 results, Harness feature flags and custom tlcModules flags are absent from the knowledge base, and there is no repo prioritization to guide future analysis. Populating it now, before wider team adoption, ensures that PR analysis produces accurate, FloQast-specific signals rather than generic ones.

## What Changes

- Fix broken Confluence bulk mining (wrong CQL endpoint or query construction); add space/label-based search alongside the existing ticket-linked page fetch
- Fix broken Jira bulk mining (issue type filter excludes most relevant tickets in project CLOSE); broaden to Story/Task/Bug/Incident and extract failure patterns
- Add a `repo-priority-index` — a structured, prioritized catalog of FloQast repos ordered by integration level, change frequency, and domain criticality
- Add a `feature-flag-extractor` that mines Harness feature flag keys and custom tlcModules flags from GitHub source code and maps them to owning modules/services
- Add a `domain-context-enrichment` pipeline phase that takes all mined artifacts and writes structured new sections into `domain_context.md` (§4 Feature Flags, §1 System Overview expansion, §6 Failure Patterns)
- Introduce a lightweight scheduled refresh mechanism (CLI command + cron entry) so the domain layer stays current without manual intervention

## Capabilities

### New Capabilities
- `repo-priority-index`: Catalog of FloQast GitHub repositories ranked by integration centrality, commit frequency, and domain rule density; provides the ordered queue for domain mining runs
- `feature-flag-extractor`: Mines Harness feature flag definitions (flag keys, environments, default values) and custom tlcModules flags from GitHub source across priority repos; maps flags to owning services/clients
- `confluence-domain-miner`: Bulk Confluence mining by space key, label, and keyword that fixes the current 0-result failure; produces structured `confluence_rules.md` with architecture diagrams, service contracts, and client/lambda rules
- `jira-domain-miner`: Bulk Jira mining across issue types (Story, Bug, Task, Incident, Epic) for project CLOSE that fixes the current 0-result failure; produces structured `jira_patterns.md` with recurring failure patterns and domain constraints
- `domain-context-enrichment`: Pipeline phase that merges all mined artifacts into `domain_context.md` — enriching §1 (System Overview), §4 (Feature Flags), §6 (Known Failure Patterns), and adding §10 (Repo Priority Index)

### Modified Capabilities
- `confluence-fetcher`: Add `search_by_space` and `search_by_label` search modes — currently the spec only requires ticket-linked page retrieval; the domain miner needs space-wide and label-filtered searches as first-class requirements
- `jira-invariant-extractor`: Extend to support project-level bulk extraction (not just individual ticket keys) so it can feed the domain miner without a separate code path

## Impact

- **`src/confluence_service.py`** — new search methods; CQL query fixes
- **`src/jira_service.py`** — broader issue type query; project-level search support
- **`src/domain_knowledge_pipeline.py`** — phases 2 and 3 rewritten; new phase 0 (repo index) and phase 5 (enrichment); new CLI flags
- **`src/config.py`** — new config keys: `CONFLUENCE_SPACES`, `FLOQAST_ORG`, `HARNESS_API_KEY` (optional), `DOMAIN_REFRESH_SCHEDULE`
- **`domain_knowledge/`** — `confluence_rules.md`, `jira_patterns.md`, `repo_priority_index.md`, `feature_flags.md` all populated from zero
- **`domain_context.md`** — §1, §4, §6 enriched; §10 added
- **`src/cli.py`** — new `refresh_domain` command that wraps the full pipeline with sane defaults for FloQast org
- No changes to MCP tools or scoring engine; domain layer is purely additive
