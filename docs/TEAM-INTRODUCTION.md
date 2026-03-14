# PR Test Coverage & Quality Tool — Team Introduction

A short guide to the **PR / Epic test coverage and quality analysis** tool: what it does, how to use it, current limitations, and where we want to take it.

---

## What it is

A tool that:

- **Analyzes GitHub PRs** (and optionally Jira Epics) for **test coverage and testing quality**.
- Uses **AI** (OpenAI, OpenRouter, or local Ollama) to read code diffs and test files and produce:
  - A **testing quality score** (0–10).
  - An **estimated coverage** for changed code (when mechanical coverage is not available).
  - A **structured audit report**: summary, metrics, integrity assessment, coverage quality, test design, risks, and concrete recommendations.
- Can **link PRs to Jira tickets** and **aggregate by Epic**, so you can see how well an entire feature (Epic) is tested across all its PRs.

It is built as an **MCP (Model Context Protocol) server** so Cursor (or other MCP clients) can call it, and also exposes a **CLI** for local runs and CI.

---

## Features

| Feature | Description |
|--------|-------------|
| **Single PR analysis** | Run analysis on one PR: metrics, score, AI narrative report, optional markdown for PR description. |
| **Analysis by author** | Analyze all merged PRs by a GitHub user in a time window (single repo or whole org). |
| **Epic-level analysis** | Given a Jira Epic key, find child tickets, discover linked PRs across repos, analyze them, and produce a consolidated Epic report (well-covered tickets, areas for improvement, general recommendations). |
| **Jira + GitHub integration** | Extracts ticket keys from PR title/branch/description; fetches Jira issue metadata; uses it for context and for Epic rollups. |
| **AI narrative report** | Per-PR markdown report with: Summary, Metrics table, Testing Integrity, Coverage Quality, Test Design, Risk Analysis, Testing Recommendations (aligned with FloQast testing standards). |
| **PR description snippet** | Generate a compact testing-quality block (score, coverage, ratio, tests added, AI summary) to paste into the PR description. |
| **Team summary** | Aggregate metrics across PRs (by repo, author, time window) for trend views. |

### How it runs

- **CLI** (local or CI): `python -m src.cli analyze_change --repo org/repo --pr 123`; `analyze_epic --epic CLOSE-1234 --org FloQastInc`; etc.
- **MCP** (Cursor): Connect to the pr-analysis MCP server; use tools like `analyze_pr`, `list_prs_by_author`, `get_pr_description_report`.

### What you need

- **GitHub token** (for PR metadata and file diffs).
- **OpenAI API key** (recommended) or OpenRouter / Anthropic / Ollama for AI report and coverage estimate.
- **Jira** (optional): URL + API token for ticket metadata and Epic child issues.
- **Optional:** `MCP_AUTH_SECRET` if the MCP server is exposed and you want API-key protection.

---

## Purpose and value

1. **Visibility at Epic level**  
   Answer: “How well is this Epic tested?” — one report with all linked PRs, scores, coverage estimates, and which tickets are well covered vs need attention.

2. **Consistency with FloQast standards**  
   The AI prompts are aligned with **floqast-testing-standards** and **react-testing-standards** (e.g. 90% target for new code, meaningful tests over coverage inflation, Jest + Enzyme, no RTL by default unless requested).

3. **Actionable feedback**  
   Reports include concrete recommendations (“verify that X is covered; if not, add…”), risk bullets, and design notes (e.g. component vs container testing), so teams know what to improve.

4. **Works without mechanical coverage**  
   Many repos do not run coverage in CI or do not expose it per-PR. The tool can still give an **AI-estimated coverage** and a quality score from the diff + test files, so you get a signal even when there is no Jest/pytest coverage report.

---

## Current limitations and pain points

| Pain point | Description |
|------------|-------------|
| **No mechanical coverage in most runs** | Real coverage (e.g. Jest `--coverage`, pytest-cov) only runs when a **local repo path** is provided and the stack supports it (e.g. Jest for JS/TS). In MCP or CLI without `--repo-path`, the tool relies on **AI-estimated coverage** and formula (test/code ratio, test-file pairing). |
| **Rate limits** | With OpenRouter (or heavy OpenAI use), batch runs (e.g. many PRs for an Epic) can hit rate limits. The tool uses delays and backoff; for large Epics, running the Epic via **CLI** with sufficient spacing is more reliable than via MCP. |
| **Epic runs can be long** | Analyzing 20+ PRs (each with several AI calls) can take many minutes; timeouts or client disconnects can occur if run over MCP. Prefer **CLI** for Epic analysis. |
| **No SonarQube/Codecov in the loop yet** | Config has placeholders for `sonar_token`, `codecov_token`, and there are providers for Sonar and Codecov, but the **pipeline does not yet feed Sonar/Codecov data** into the score or report. Coverage today is either local (Jest) or AI-estimated. |
| **Single scoring model** | The testing quality score blends formula (coverage, ratio, pairing) with optional LLM qualitative score. There is no separate “code smell” or “maintainability” dimension yet. |

---

## Possible improvements

| **Scope alignment is heuristic** | The "Scope vs ticket" section in PR reports uses keyword matching to classify as Aligned, Issues, Partial, or No ticket context. In ambiguous cases check the full text in the PR report. |

---

## Workflow documentation

The tool can generate **core workflow docs** from Jira Epics:

```bash
python -m src.cli generate_workflow_docs --epics "CLOSE-8615,OTHER-1" --org FloQastInc
```

This produces a single Markdown (`docs/core-workflows.md`) with: Epic description, child tickets (Stories first = main flows, then Tasks/Bugs), ticket descriptions, and optionally a **Implementation (PRs)** table grouped by ticket (when `--repo` or `--org` is given and storage has metrics).

---

## Possible improvements

These are directions the team could take next:

| Improvement | Benefit |
|-------------|--------|
| **Integrate mechanical coverage** | When Codecov/SonarQube (or CI artifacts) are available for the PR, **pull real coverage** and use it in the score and report instead of (or in addition to) AI estimate. Config already has `codecov_token`, `sonar_token`, `sonar_url`; wiring them into the pipeline would improve accuracy. |
| **SonarQube code smells and quality** | Use Sonar’s issues (bugs, code smells, vulnerabilities) in the report: e.g. “Test files have X code smells; production has Y.” Would give a second axis (quality/maintainability) alongside coverage. |
| **CI integration** | Run the CLI in CI (e.g. `analyze_change` on the PR branch), optionally post the **PR description snippet** as a comment or require a minimum score for merge. |
| **Caching and idempotency** | Cache GitHub/Jira responses and analysis results (e.g. by `repo+pr+sha`) so re-runs are cheap and CI can re-use previous results when the diff hasn’t changed. |
| **Configurable thresholds** | Make the 90% coverage target and score thresholds (e.g. “fail below 6”) configurable per repo or per Epic so different products can have different bars. |
| **Richer Epic report** | Already added: well-covered tickets, areas for improvement, AI summaries and recommendations per PR, and general observations. Further: link to individual PR reports, or a one-pager PDF/HTML for stakeholders. |

---

## Example use cases

- **Before release:** Run `analyze_epic --epic CLOSE-8615 --org FloQastInc` and share the Epic report (summary, PR table, well-covered tickets, areas for improvement, general recommendations) with the team.
- **Code review:** For a single PR, run `analyze_change` or use the MCP `analyze_pr` tool; paste the **PR description report** into the PR so reviewers see score, coverage estimate, and AI summary.
- **Team health:** Use `analyze_author` or `generate_summary` over a time window to see coverage and score trends by author or repo.
- **Retrospective:** Use the Epic report to identify which tickets had weak testing (low score, no tests, or low coverage) and turn that into action items (e.g. add tests for PRs #X, #Y).

---

## Where to learn more

- **CLI usage:** `python -m src.cli --help` and subcommands `analyze_change`, `analyze_epic`, `analyze_author`, `pr_description_report`, `generate_summary`.
- **MCP response shapes:** `docs/MCP-RESPONSE-SHAPES.md`.
- **Deployment and security:** `docs/DEPLOYMENT-SECURITY.md`.
- **Alignment with FloQast standards:** `docs/FQ-SKILLS-ALIGNMENT.md`.

If you want to extend the tool (e.g. plug in SonarQube code smells or Codecov), the main entry points are the **pipeline** (`src/pr_analysis_pipeline.py`), **report generator** (`src/report_generator.py`), and **coverage providers** (`src/coverage_providers/`).
