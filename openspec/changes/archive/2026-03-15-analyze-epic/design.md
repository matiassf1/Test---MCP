# Design: analyze-epic

## Technical Decisions

---

### Decision: Single function in `tool_api.py` as the canonical implementation

**Alternatives considered:**
- A dedicated `EpicAnalyzer` class (analogous to `PRAnalysisPipeline`)
- Inline logic in `mcp_server.py`

**Rationale:** The existing `tool_api.py` pattern — plain callables returning dicts or domain objects — already serves both MCP and CLI without a coordinator class. The Epic analysis is a composition of existing services (`JiraService`, `GitHubService`, `PRAnalysisPipeline`) with no novel state to manage, so a function is sufficient and consistent with the established pattern. A dedicated class would add indirection without benefit at this scope.

---

### Decision: Epic + child ticket keys are searched independently on GitHub

**Alternatives considered:**
- Search only the Epic key and rely on PRs referencing it directly
- Parse PR descriptions to infer Jira ticket relationships

**Rationale:** In practice, developers reference the child ticket (e.g. `PROJ-456`) in their PR, not the Epic (`PROJ-100`). Searching only the Epic key would miss the majority of related PRs. Searching each child key independently and deduplicating by `(repo, pr_number)` captures the full set correctly.

---

### Decision: `skip_existing` flag for incremental analysis

**Alternatives considered:**
- Always re-analyze every PR (fresh results every time)
- Automatic cache invalidation based on PR update timestamp

**Rationale:** Epics can have dozens of PRs. Re-running AI analysis on all of them is expensive (API calls, rate limits, latency). The `skip_existing` flag lets callers opt into incremental mode, reusing persisted metrics for already-analyzed PRs. Full re-analysis remains the default for accuracy.

---

### Decision: Batch delay via `_batch_delay()` helper inside `tool_api`

**Alternatives considered:**
- Pass delay configuration into `PRAnalysisPipeline`
- Implement a global rate-limiter class

**Rationale:** The delay is specific to the sequential batch pattern of Epic analysis (and `batch_analyze_*` functions), not a concern of the pipeline itself. A local helper reads `settings` and applies the delay only when an AI provider key is present, keeping the pipeline clean and the delay logic co-located with the batch loop.

---

### Decision: Graceful degradation when Jira is unavailable

**Alternatives considered:**
- Require Jira credentials as a hard dependency
- Return an error if Jira is not configured

**Rationale:** The primary value of `analyze_epic` is the PR analysis, not the Jira metadata. If Jira is unconfigured or unreachable, the tool falls back to searching GitHub for just the Epic key. `epic_summary` and `child_tickets` are `null`/empty, but the PR analysis proceeds. This makes the tool usable even for teams that don't use Jira.

---

### Decision: Response shape is a plain `dict`, not a Pydantic model

**Alternatives considered:**
- Add an `EpicReport` Pydantic model to `models.py`

**Rationale:** The Epic report is a composite of heterogeneous data (Jira metadata + list of per-PR dicts) that varies by what's available. A strict Pydantic model would require optional fields everywhere. The `tool_api` contract already uses `dict[str, Any]` for summary-style responses (`batch_analyze_*`, `list_prs_by_author`), so consistency favors staying with `dict` here.

---

### MCP tool exposure

The `analyze_epic` function is registered directly in `mcp_server.py` via `@mcp.tool()`, consistent with all other tools. No changes to the MCP transport layer.

### CLI command

The `analyze_epic` subcommand uses `--epic` (required), `--repo` / `--org` (mutually exclusive, required), plus the shared `--storage` and `--cache` flags. Output is rendered via `rich` console.
