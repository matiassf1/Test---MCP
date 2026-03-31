## 1. Config & Infrastructure

- [x] 1.1 Add `CONFLUENCE_SPACES`, `FLOQAST_ORG`, `HARNESS_API_KEY` (optional), and `DOMAIN_REFRESH_SCHEDULE` to `src/config.py` with defaults (`CONFLUENCE_SPACES="ENG,CLOSE"`, `FLOQAST_ORG="FloQastInc"`)
- [x] 1.2 Add the new config keys with documentation comments to `.env.example`
- [x] 1.3 Create `domain_knowledge/` output stubs: ensure `feature_flags.md`, `repo_priority_index.yaml` paths are referenced in config

## 2. ConfluenceService — search_by_space & search_by_label

- [x] 2.1 Add `search_by_space(space_key: str, query_terms: list[str], max_results: int = 20) -> list[ConfluencePage]` to `src/confluence_service.py`; CQL: `space = "<key>" AND (text ~ "t1" OR text ~ "t2") AND type = page`
- [x] 2.2 Add `search_by_label(label: str, max_results: int = 10) -> list[ConfluencePage]` to `src/confluence_service.py`; CQL: `label = "<label>" AND type = page`
- [x] 2.3 Both methods return `[]` and log debug when `not self._enabled` (match existing graceful-degradation pattern)
- [x] 2.4 Both methods log `WARNING: space/label <x> not found` on 404 and return `[]`
- [x] 2.5 Cap results at `max_results` using Confluence pagination `limit` param; do not fetch additional pages beyond cap

## 3. JiraService — broad project query

- [x] 3.1 Add `search_project_tickets(project: str, issue_types: list[str], max_tickets: int = 100, since_days: int = 180) -> list[dict]` to `src/jira_service.py`; returns list of `{"key", "summary", "description", "issuetype", "url"}`
- [x] 3.2 JQL: `project = <project> AND issuetype in (<types>) AND updated >= -<N>d ORDER BY updated DESC`; respect `max_tickets` via `maxResults` param
- [x] 3.3 Default `issue_types` = `["Story", "Task", "Bug", "Incident", "Epic"]`

## 4. JiraInvariantExtractor — batch mode

- [x] 4.1 Add `extract_batch(tickets: list[dict]) -> list[JiraInvariantContext]` class method to `src/jira_invariant_extractor.py`; iterates and calls existing `extract()` per ticket description
- [x] 4.2 Add `merge_batch(contexts: list[JiraInvariantContext]) -> JiraInvariantContext` class method; deduplicates `domain_constraints` by value and `porting_signals` by `phrase+context`
- [x] 4.3 Empty list input to `merge_batch` returns an empty `JiraInvariantContext` without error

## 5. Repo Priority Index Builder

- [x] 5.1 Create `scripts/build_repo_index.py` — queries `FLOQAST_ORG` GitHub org repos via `GitHubService`, collects commit count (last 90d) and contributor count per repo
- [x] 5.2 Implement scoring: commit_score (0–5) + contributor_score (0–3) + keyword_score (0–2, match `signoff|locking|checklist|authorization|close` in description/topics)
- [x] 5.3 Respect `--max-repos` flag (default 50); sleep 1s between repo calls; retry once on rate limit
- [x] 5.4 Write `domain_knowledge/repo_priority_index.yaml` — fields: `repo`, `priority`, `score`, `rationale`, `domain_areas[]`
- [x] 5.5 On re-run, preserve existing `manual_priority` fields from the YAML if present; do not overwrite them

## 6. Feature Flag Extractor

- [x] 6.1 Create `src/feature_flag_extractor.py` — `FeatureFlagExtractor` class with `extract(repos: list[str]) -> dict` that takes repo names from priority index
- [x] 6.2 Implement Harness flag grep: fetch file tree for each repo via GitHub API; for each TypeScript/JS file matching `**/featureFlag*`, `**/feature-flag*`, `**/constants/flag*` scan content for `"close_[a-z0-9_-]+"` pattern
- [x] 6.3 Implement usage-site grep: scan all `.ts`/`.js` files for `useFeatureFlag\(["']close_[^"']+["']\)` and `getFeatureFlag\(["']close_[^"']+["']\)` patterns
- [x] 6.4 Implement tlcModules grep: scan for `tlcModules\[["'][^"']+["']\]`, `getTlcModule\(["'][^"']+["']\)`, `isTlcModuleEnabled\(["'][^"']+["']\)` patterns
- [x] 6.5 Exclude test files: skip any file path containing `__tests__/`, `.test.ts`, `.spec.ts`, `.test.js`, `.spec.js`
- [x] 6.6 Write `domain_knowledge/feature_flags.md` — sections `## Harness Flags` and `## tlcModules`; format: `- <key>: owning module: <path>; seen in: <N> files`
- [x] 6.7 On incremental re-run: append new keys; update `seen in` count for existing keys; no duplicates

## 7. Confluence Domain Miner

- [x] 7.1 Create `src/confluence_domain_miner.py` — `ConfluenceDomainMiner` class wrapping `ConfluenceService.search_by_space` and `search_by_label`
- [x] 7.2 Implement `mine(spaces: list[str], query_terms: list[str], labels: list[str] = []) -> list[ConfluencePage]`; deduplicate by page ID; prioritize space-scoped results over label results
- [x] 7.3 Enforce 12 000 char content budget: include pages in priority order; truncate last page with `[truncated]` marker if needed
- [x] 7.4 Call existing Confluence mining LLM prompt (`_CONFLUENCE_MINING_SYSTEM`) with aggregated content; write structured output to `domain_knowledge/confluence_rules.md`
- [x] 7.5 When `AI_ENABLED=false`: write raw page titles + first 500 chars to `confluence_rules.md` without LLM summarization
- [x] 7.6 Append `## Sources` section to `confluence_rules.md`: `- [<title>](<url>) (space: <key>, id: <page_id>)` per page

## 8. Jira Domain Miner

- [x] 8.1 Create `src/jira_domain_miner.py` — `JiraDomainMiner` class using `JiraService.search_project_tickets` + `JiraInvariantExtractor.extract_batch` + `merge_batch`
- [x] 8.2 Implement `mine(project: str, issue_types: list[str] | None = None, max_tickets: int = 100, since_days: int = 180) -> JiraInvariantContext`
- [x] 8.3 Pass ticket summaries + descriptions through existing Jira mining LLM prompt (`_JIRA_MINING_SYSTEM`); write to `domain_knowledge/jira_patterns.md`
- [x] 8.4 When 0 tickets found: write `(no domain failure patterns identified)` stub instead of empty file
- [x] 8.5 When `AI_ENABLED=false`: write raw ticket summaries as bullet list under `## Raw Ticket Summaries`
- [x] 8.6 Append `## Sources` section: `- [<KEY>: <summary>](<url>) (type: <issuetype>)` per ticket
- [x] 8.7 Add `Mined: <N> tickets (latest <cap> of <total>) updated in last <days> days` header to output

## 9. Domain Context Enricher

- [x] 9.1 Create `src/domain_context_enricher.py` — `DomainContextEnricher` class that reads/writes `domain_context.md`
- [x] 9.2 Implement guard-block detection: regex to find `<!-- BEGIN MINED -->` / `<!-- END MINED -->` within a named section (`## N. TITLE`)
- [x] 9.3 Implement `_insert_or_replace_guard(section_header: str, content: str)` — appends guard block if absent; replaces existing guard block content if present; never touches content outside guard
- [x] 9.4 Implement `enrich_feature_flags()` — reads `feature_flags.md`; inserts/updates §4 guard block with `### Harness Flags (mined)` and `### tlcModules (mined)` subsections
- [x] 9.5 Implement `enrich_failure_patterns()` — reads `jira_patterns.md`; appends new patterns to §6 guard block; suppresses duplicates by name (case-insensitive) with comment marker
- [x] 9.6 Implement `enrich_repo_index()` — reads `repo_priority_index.yaml`; creates/updates `## 10. REPO PRIORITY INDEX` section with top-10 repos
- [x] 9.7 If a target section does not exist, append it at end of file (header + guard block)
- [x] 9.8 Verify idempotency: running `enrich()` twice on unchanged inputs produces no file diff

## 10. Domain Knowledge Pipeline — wire new phases

- [x] 10.1 Update `DomainKnowledgePipeline.build()` to call `ConfluenceDomainMiner.mine()` in phase 2 (replace existing keyword-only Confluence call) using `settings.confluence_spaces`
- [x] 10.2 Update phase 3 to call `JiraDomainMiner.mine()` (replace existing Bug/Incident-only Jira call)
- [x] 10.3 Add optional phase 0: if `repos_file` arg provided, load `repo_priority_index.yaml`; otherwise use single `--repo` arg (backward compatible)
- [x] 10.4 Add optional phase 5b (enrichment): call `DomainContextEnricher.enrich()` after context generation when `--enrich` flag is set (default True)
- [x] 10.5 Add optional phase 5c (feature flags): call `FeatureFlagExtractor.extract()` when `repos_file` is provided

## 11. CLI — refresh_domain command

- [x] 11.1 Add `refresh_domain` subcommand to `src/cli.py` with flags: `--jira-project` (default `CLOSE`), `--confluence-spaces` (default from `settings.confluence_spaces`), `--repos-file` (default `domain_knowledge/repo_priority_index.yaml`), `--since-days` (default 180), `--enrich/--no-enrich` (default enrich), `--max-tickets` (default 100)
- [x] 11.2 Command calls: `build_repo_index.py` (if `--repos-file` not present), then `DomainKnowledgePipeline.build()` with new args, then `FeatureFlagExtractor`, then `DomainContextEnricher`
- [x] 11.3 Print summary at end: files written, pages/tickets mined, flags extracted, sections enriched

## 12. Validation & Documentation

- [x] 12.1 Run `python -m src.cli refresh_domain --jira-project CLOSE --confluence-spaces CLOSE,ENG` and verify `confluence_rules.md` and `jira_patterns.md` are populated (not empty stubs)
- [ ] 12.2 Inspect `domain_knowledge/feature_flags.md` — confirm Harness `close_*` keys and tlcModules entries present (pending --extract-flags run)
- [x] 12.3 Inspect `domain_context.md` — confirm §4, §6 guard blocks present; §10 added
- [x] 12.4 Re-run `refresh_domain` — confirm `domain_context.md` is unchanged (idempotency check via `git diff`)
- [x] 12.5 Update README with `refresh_domain` usage and cron setup instructions (e.g. `0 9 * * 1 cd /path && python -m src.cli refresh_domain`)
- [x] 12.6 Update `AUTHORING_DOMAIN_CONTEXT.md` with note that §4, §6, §10 guard blocks are machine-managed; manual edits must go above the `<!-- BEGIN MINED -->` marker
