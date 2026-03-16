# Proposal: analyze-epic

## Why

Engineering managers and tech leads need to assess testing quality across an entire Jira Epic — not just individual PRs. Previously, to understand the testing health of a feature under an Epic, a user had to manually identify every child ticket, search GitHub for related PRs, and run `analyze_change` on each one. This was tedious and error-prone.

## What Changes

A new `analyze_epic` capability that, given a Jira Epic key and a GitHub scope (repo or org), automatically:
1. Fetches the Epic and its child tickets from Jira
2. Discovers all merged GitHub PRs that mention the Epic or any child ticket
3. Runs the full analysis pipeline on each PR
4. Returns a consolidated report with per-PR metrics and an aggregate summary

## Capabilities

### New
- **`analyze_epic`** (MCP tool + CLI command + `tool_api` callable) — full Epic-level report: child tickets, linked PRs with metrics and AI reports, aggregate quality score and test count

### Modified
- **`src/cli.py`** — new `analyze_epic` subcommand (`--epic`, `--repo` / `--org`)
- **`mcp_server.py`** — new MCP tool registration for `analyze_epic`
- **`src/github_service.py`** — new `get_prs_mentioning_ticket()` method using GitHub Search API
- **`src/jira_service.py`** — new `fetch_epic_issues()` method to retrieve child tickets

## Impact

- No breaking changes to existing tools or CLI commands
- Requires Jira credentials for child ticket enrichment (gracefully degrades if unavailable)
- Inherits existing AI/rate-limit configuration for per-PR analysis
- Persists metrics to the same `JSONStorage` backend as other analysis commands
