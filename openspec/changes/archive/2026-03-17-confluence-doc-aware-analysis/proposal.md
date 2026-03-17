## Why

The PR analysis tool currently evaluates test quality and code structure but lacks the ability to validate implementation against business specifications. This causes it to miss behavioral regressions that are correct code but wrong behavior — a class of bugs that only becomes visible when the output is compared against ERDs, PRDs, and acceptance criteria documented in Confluence.

## What Changes

- New `confluence_service.py` to fetch and parse Confluence pages linked to a Jira ticket, including domain ERDs and PRDs
- New `risk_analyzer.py` with agnostic heuristics for authorization signals, feature flag coverage, behavioral change ratio, and role/entity gap detection — fully driven by doc context, no hardcoded domain knowledge
- Enriched LLM prompt in `ai_reporter.py` to include relevant Confluence content when available, shifting the AI report from "code quality narrative" to "spec vs implementation validation"
- New `risk_level` field (`HIGH` / `MEDIUM` / `LOW`) added to `PRMetrics`, computed from static signals and LLM output — separate from `testing_quality_score`
- Optional `config.yaml` per repo to map Confluence space, ERD labels, and path-to-page mappings — tool degrades gracefully when absent
- Updated MCP tool responses and report generator to surface `risk_level` and `spec_violations`

## Capabilities

### New Capabilities

- `confluence-fetcher`: Fetches Confluence pages linked to a Jira ticket (via remoteLinks and inline URLs in description), retrieves page content as plain text, and supports label-based ERD/PRD search within a space
- `doc-aware-analysis`: Assembles analysis context from ticket + Confluence docs + diff and passes it to the LLM with a spec-validation prompt; extracts structured output (risk level, spec violations, untested scenarios)
- `risk-scoring`: Computes `risk_level` from static heuristics (auth signal, feature flag gaps, behavioral change ratio) combined with LLM-extracted signals; produces a `risk_factors` list with concrete justification
- `agnostic-config`: Optional `config.yaml` per repo declaring Confluence space, ERD label, and domain path mappings; tool works without it using safe defaults

### Modified Capabilities

- `pr-analysis-pipeline`: `analyze_pr` now optionally fetches Confluence docs and runs risk scoring; `PRMetrics` gains `risk_level`, `risk_points`, `risk_factors`, `spec_violations`
- `report-generation`: PR reports and epic reports surface `risk_level` badge and `spec_violations` section; MCP tool responses include risk fields

## Impact

- **New files**: `src/confluence_service.py`, `src/risk_analyzer.py`
- **Modified files**: `src/pr_analysis_pipeline.py`, `src/ai_reporter.py`, `src/models.py`, `src/report_generator.py`, `src/tool_api.py`, `src/config.py`
- **New env vars**: `CONFLUENCE_BASE_URL`, `CONFLUENCE_TOKEN` (optional — feature disabled when absent)
- **New optional file**: `.testing-tool/config.yaml` in analyzed repos
- **Dependencies**: no new Python packages required (Confluence REST API uses same `requests` already present)
- **Backwards compatible**: all new fields are optional; existing behavior unchanged when Confluence credentials are not configured
