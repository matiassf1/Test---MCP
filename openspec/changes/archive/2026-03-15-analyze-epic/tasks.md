# Tasks: analyze-epic

## Jira integration

- [x] 1.1 Add `fetch_epic_issues(epic_key)` to `JiraService` — returns list of child `JiraIssue` objects
- [x] 1.2 Add `is_available()` guard to `JiraService` — returns `False` when credentials are missing

## GitHub integration

- [x] 2.1 Add `get_prs_mentioning_ticket(key, repo, org, limit)` to `GitHubService` — uses GitHub Search API, returns list of `(repo, pr_number)` tuples
- [x] 2.2 Deduplicate discovered `(repo, pr_number)` pairs across all ticket keys

## Core capability

- [x] 3.1 Implement `analyze_epic()` in `src/tool_api.py`
- [x] 3.2 Fetch Epic metadata and child tickets from Jira (graceful degradation if unavailable)
- [x] 3.3 Search GitHub for merged PRs for each ticket key (Epic + children)
- [x] 3.4 Run `PRAnalysisPipeline.analyze_pr()` on each discovered PR
- [x] 3.5 Implement `skip_existing` path — load from storage instead of re-analyzing
- [x] 3.6 Implement `_batch_delay()` helper — delay between PRs when AI provider is configured
- [x] 3.7 Build aggregate `summary` dict (total_prs, failed, avg_testing_quality_score, total_tests_added)
- [x] 3.8 Handle `include_ai_report=False` — omit `ai_report` from PR entries

## MCP exposure

- [x] 4.1 Register `analyze_epic` as an MCP tool in `mcp_server.py`
- [x] 4.2 Add docstring describing parameters and response shape

## CLI

- [x] 5.1 Add `analyze_epic` subcommand to `src/cli.py` parser (`--epic`, `--repo`/`--org`, `--storage`, `--cache`)
- [x] 5.2 Implement `cmd_analyze_epic()` handler with `rich` output
