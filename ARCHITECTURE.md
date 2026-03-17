# Architecture

## Overview

The PR Testing Impact Analyzer is a **monolithic Python service** with two consumption interfaces:

1. **MCP server** (`mcp_server.py`) — exposes all capabilities as MCP tools for AI agents (Cursor, Claude Desktop, or any MCP-compatible client)
2. **CLI** (`src/cli.py`) — direct command-line access for scripting and CI integration

Both interfaces delegate to the same `tool_api.py` callable surface, which in turn drives the `PRAnalysisPipeline`.

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│  MCP Client │────▶│  mcp_server.py  (FastMCP, stdio/SSE)     │
└─────────────┘     └─────────────────┬────────────────────────┘
                                       │
┌─────────────┐     ┌──────────────────▼────────────────────────┐
│     CLI     │────▶│  src/tool_api.py  (plain Python callables) │
└─────────────┘     └─────────────────┬────────────────────────┘
                                       │
                    ┌──────────────────▼────────────────────────┐
                    │  src/pr_analysis_pipeline.py              │
                    │  (orchestrator — dependency injection)    │
                    └──────┬───────┬───────┬────────┬───────────┘
                           │       │       │        │
                    GitHub  Jira  Change  Coverage  Metrics
                    Service Svc   Analyzer Runner   Engine
```

## Modules / Layers

### Entry Points

| File | Role |
|---|---|
| `mcp_server.py` | FastMCP server. Wraps `tool_api` functions as MCP tools. Supports both stdio (local) and HTTP/SSE (remote) transports. |
| `src/cli.py` | `argparse` + `rich` CLI. Four commands: `analyze_change`, `analyze_author`, `analyze_epic`, `generate_summary`. |

### API Surface

**`src/tool_api.py`** — the single callable boundary shared by MCP and CLI. All public functions return domain objects or `None` (never raise). This makes them safe for agent tool use.

### Core Pipeline

**`src/pr_analysis_pipeline.py`** — `PRAnalysisPipeline` orchestrates a PR analysis in six steps:

1. Fetch PR metadata from GitHub (`GitHubService`)
2. Extract and enrich Jira ticket (`JiraService`)
3. Analyse changed files — split production vs test (`ChangeAnalyzer`)
4. Detect and classify test files by type (`TestDetector`)
5. Run coverage (optional — only when `repo_path` is provided or a CI provider is configured)
6. Compute and persist `PRMetrics` (`MetricsEngine`, `StorageBackend`)

All dependencies are injected into the constructor, with sensible defaults. This enables easy unit testing with mocks.

### Domain Models

**`src/models.py`** — Pydantic v2 models:

| Model | Purpose |
|---|---|
| `PRMetrics` | Complete analysis result for one PR |
| `TeamSummary` | Aggregated stats across PRs / authors / repos |
| `FileChange` | A single changed file with diff metadata |
| `TestFile` | A detected test file with type classification |
| `CoverageResult` | Output of a coverage run (lines covered/modified) |
| `AIAnalysis` | Qualitative LLM assessment (score, suggestions, untested areas) |
| `JiraIssue` | Jira ticket metadata (type, status, priority, components) |
| `AuthorStats` | Per-author aggregated statistics |

### External Integrations

**`src/github_service.py`** — wraps `PyGithub`. Fetches PR metadata, file diffs, and raw patches. An optional `CachedGitHubService` wrapper (`src/cache.py`) persists responses to disk to avoid rate-limit exhaustion.

**`src/jira_service.py`** — connects to Jira REST API. Extracts ticket keys from PR titles/branches, fetches issue metadata. Used for Epic analysis (child tickets + linked PRs).

### Analysis Layer

**`src/change_analyzer.py`** — parses file diffs to split changes into production vs test, count modified lines, and detect generated files (excluded from scoring).

**`src/test_detector.py`** — classifies test files by type (`unit`, `integration`, `e2e`, `unknown`) using filename conventions and path heuristics.

**`src/artifact_coverage.py`** — fetches pytest coverage from GitHub Actions artifacts (JSON reports uploaded by CI) when a local `repo_path` is not available.

**`src/coverage_providers/`** — pluggable external coverage providers:
- `codecov_provider.py` — Codecov API
- `sonar_provider.py` — SonarQube/SonarCloud API
- `jest_runner.py` / `jest_artifact_provider.py` — Jest coverage support

### Scoring

**`src/metrics_engine.py`** — `_compute_testing_quality_score()` produces a **0–10 composite score** with four branches depending on available data:

| Branch | Formula |
|---|---|
| A — LLM coverage available | `llm_cov × 0.85 × 0.45 + test_ratio × 0.35 + pairing × 0.20` |
| B — CI coverage only | `ci_cov × 0.5 + test_ratio × 0.3 + pairing × 0.2` |
| C — Diff-heuristic estimate | `diff_est × 0.7 × 0.35 + test_ratio × 0.4 + pairing × 0.25` |
| D — No coverage data | `test_ratio + pairing` only |

The score is clamped to `[0, 10]`. LLM estimates are preferred over mechanical CI coverage when both are present.

### AI Layer

**`src/ai_analyzer.py`** — `AIAnalyzer` reads actual code diffs and produces a qualitative `AIAnalysis` (0–10 `ai_quality_score`, `untested_areas`, `suggestions`). Aligned with FloQast testing standards: meaningful tests over metric inflation, behavior-focused, Arrange-Act-Assert.

**`src/ai_reporter.py`** — generates a free-form Markdown report per PR using an LLM. Truncates patches to `3000` chars/file and caps at 5 production files to stay within context limits.

**AI provider chain** (first configured wins):
1. Direct OpenAI (`OPENAI_API_KEY`)
2. OpenRouter (`OPENROUTER_API_KEY`) — with sequential rate-limit management (configurable delays, 429 backoff)
3. Anthropic Claude (`ANTHROPIC_API_KEY`)
4. Ollama (local, default model `llama3.1`)

### Storage

**`src/storage.py`** — `StorageBackend` protocol with `JSONStorage` implementation. Persists `PRMetrics` as `metrics/pr_<number>.json`. `create_storage()` factory allows future backends.

### Report Generation

**`src/report_generator.py`** — renders `PRMetrics` as a rich Markdown report. Used by the CLI's `analyze_change` command.

## Configuration

All settings live in `src/config.py` as a `pydantic-settings` `Settings` class. Values are read from environment variables or a `.env` file. Key groups:

- **GitHub**: `GITHUB_TOKEN`
- **Jira**: `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`
- **AI**: `AI_ENABLED`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, rate-limit tuning fields
- **Coverage**: `CODECOV_TOKEN`, `SONAR_TOKEN`, `SONAR_URL`, `SONAR_PROJECT_KEY`

## Development Conventions

- **No exceptions from `tool_api`** — all public functions return `None` or empty structures on failure
- **Dependency injection** in `PRAnalysisPipeline` — services are injected, not imported globally, so unit tests can substitute mocks
- **Generated files excluded** from all scoring — detected by path segments (`/generated/`, `/__generated__/`) and suffixes (`.generated.ts`, `_pb2.py`, etc.)
- **Pydantic v2** for all data — use `model_dump()`, not `.dict()`
- **`from __future__ import annotations`** at the top of every module
