## ADDED Requirements

### Requirement: Fetch Confluence pages linked to a Jira ticket
The system SHALL discover and retrieve Confluence pages associated with a Jira ticket by querying remoteLinks from the Jira API and extracting Confluence URLs from the ticket description text.

#### Scenario: Pages found via remoteLinks
- **WHEN** a Jira ticket has one or more remote links pointing to a Confluence page
- **THEN** the system retrieves the text content of each linked page (up to 5 pages)

#### Scenario: Pages found via description URL extraction
- **WHEN** a Jira ticket has no remoteLinks but its description contains Confluence URLs matching CONFLUENCE_BASE_URL
- **THEN** the system extracts those URLs and retrieves page content as a fallback

#### Scenario: No Confluence pages found
- **WHEN** a Jira ticket has no remoteLinks and no Confluence URLs in its description
- **THEN** the system returns an empty list without error

### Requirement: Retrieve Confluence page content as plain text
The system SHALL fetch the storage-format body of a Confluence page and convert it to readable plain text by stripping HTML tags, macros, and Jira-specific markup using only Python stdlib (`html.parser`).

#### Scenario: Page content successfully retrieved
- **WHEN** a valid Confluence page ID is provided
- **THEN** the system returns a plain-text string with HTML stripped and whitespace normalized

#### Scenario: Page returns non-200 status
- **WHEN** the Confluence API returns a 404 or 403 for a page ID
- **THEN** the system logs a warning and returns None for that page, continuing with remaining pages

### Requirement: Degrade gracefully when Confluence credentials are absent
The system SHALL skip all Confluence fetching when `CONFLUENCE_BASE_URL` or `CONFLUENCE_TOKEN` are not configured, returning an empty result without raising exceptions.

#### Scenario: Missing credentials
- **WHEN** `CONFLUENCE_BASE_URL` or `CONFLUENCE_TOKEN` is empty in settings
- **THEN** `ConfluenceService` methods return empty lists/None and log a debug message

### Requirement: Respect page fetch limit
The system SHALL fetch at most 5 Confluence pages per PR analysis to limit API calls and avoid rate limiting.

#### Scenario: More than 5 pages discovered
- **WHEN** a ticket has 8 remoteLinks pointing to Confluence pages
- **THEN** only the first 5 are fetched; the rest are skipped with a debug log
