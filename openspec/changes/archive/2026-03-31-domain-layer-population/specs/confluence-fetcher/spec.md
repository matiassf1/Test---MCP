## ADDED Requirements

### Requirement: Search Confluence pages by space key and query terms
The system SHALL provide a `search_by_space(space_key, query_terms, max_results)` method on `ConfluenceService` that issues a CQL space-scoped full-text search and returns a list of `ConfluencePage` objects.

#### Scenario: Space-scoped CQL returns pages
- **WHEN** `search_by_space("CLOSE", ["signoff", "locking"], max_results=20)` is called
- **THEN** a CQL query `space = "CLOSE" AND (text ~ "signoff" OR text ~ "locking") AND type = page` is issued and up to 20 pages with body content are returned

#### Scenario: Space key not found
- **WHEN** the CQL query returns 404 (space does not exist)
- **THEN** the method logs `WARNING: space <key> not found` and returns an empty list without raising

#### Scenario: More than max_results pages available
- **WHEN** the CQL query would return 50 pages but `max_results=20`
- **THEN** exactly 20 pages are returned; Confluence pagination is used to cap at `max_results` without fetching additional pages

### Requirement: Search Confluence pages by label
The system SHALL provide a `search_by_label(label, max_results)` method on `ConfluenceService` that returns all pages tagged with the given Confluence label.

#### Scenario: Label-tagged pages returned
- **WHEN** `search_by_label("domain-rules", max_results=10)` is called
- **THEN** a CQL query `label = "domain-rules" AND type = page` is issued and up to 10 pages are returned

#### Scenario: Label with no tagged pages
- **WHEN** no pages are tagged with the given label
- **THEN** an empty list is returned without error

#### Scenario: Credentials absent
- **WHEN** `CONFLUENCE_BASE_URL` or `CONFLUENCE_TOKEN` is not configured
- **THEN** both `search_by_space` and `search_by_label` return empty lists and log a debug message, matching existing graceful-degradation behavior
