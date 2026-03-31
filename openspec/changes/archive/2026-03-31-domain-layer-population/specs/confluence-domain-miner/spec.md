## ADDED Requirements

### Requirement: Mine Confluence pages by space key and query terms
The system SHALL support bulk mining of a Confluence space using CQL space-scoped queries and write structured results to `domain_knowledge/confluence_rules.md`.

#### Scenario: Space-scoped search returns pages
- **WHEN** `confluence_domain_miner` is called with `space_key="CLOSE"` and `query_terms=["signoff", "authorization", "locking"]`
- **THEN** a CQL query of the form `space = "CLOSE" AND (text ~ "signoff" OR text ~ "authorization" OR text ~ "locking") AND type = page` is issued and up to `max_results` (default 20) pages are returned

#### Scenario: No pages found in space
- **WHEN** the CQL query returns 0 results for the given space and terms
- **THEN** the miner logs `WARNING: no pages found in space <key> for terms <terms>` and continues without error; `confluence_rules.md` receives a `(no pages found)` stub for that space

#### Scenario: Multiple spaces configured
- **WHEN** `CONFLUENCE_SPACES=ENG,CLOSE,ARCH` is configured
- **THEN** the miner runs one CQL query per space, aggregates all pages, deduplicates by page ID, and writes all results to `confluence_rules.md`

### Requirement: Mine Confluence pages by label
The system SHALL support fetching all pages with a given label across the entire Confluence instance.

#### Scenario: Label-based search returns tagged pages
- **WHEN** `search_by_label(label="domain-rules", max_results=10)` is called
- **THEN** a CQL query `label = "domain-rules" AND type = page` is issued and up to 10 pages are retrieved with full body content

#### Scenario: Label search combined with space mining
- **WHEN** both space-based and label-based mining are configured
- **THEN** results are merged and deduplicated by page ID before LLM summarization

### Requirement: Summarize mined pages into domain_knowledge/confluence_rules.md via LLM
The system SHALL pass retrieved page content through the existing Confluence mining LLM prompt and write the structured output to `domain_knowledge/confluence_rules.md`.

#### Scenario: Pages summarized into domain rule sections
- **WHEN** at least one Confluence page is retrieved
- **THEN** the LLM produces sections `## Domain Rules`, `## Roles`, `## Feature Flags`, `## Domain Differences` and these are written to `confluence_rules.md`

#### Scenario: Content exceeds LLM context budget
- **WHEN** the total content of retrieved pages exceeds 12 000 characters
- **THEN** pages are included in priority order (space-scoped first, then label-based) until the 12 000 char budget is exhausted; a `[truncated]` marker is appended

#### Scenario: LLM unavailable or disabled
- **WHEN** `AI_ENABLED=false` or no LLM key is configured
- **THEN** raw page titles and first 500 chars of content are written to `confluence_rules.md` as a best-effort plain-text dump without summarization

### Requirement: Persist raw page metadata alongside summaries
The system SHALL record page ID, title, space, and URL for each mined page in `confluence_rules.md` as a source reference block.

#### Scenario: Source references written
- **WHEN** `confluence_rules.md` is generated
- **THEN** a `## Sources` section at the end of the file lists each contributing page as `- [<title>](<url>) (space: <key>, id: <page_id>)`
