# PR Testing Impact Analyzer — One Pager

## Where This Came From

While working on the Workflows team, I noticed two recurring friction points:

1. **Test coverage reports were misleading** — CI would show a passing coverage %, but the actual test quality on changed logic was unclear. This created uncertainty when landing PRs.
2. **Epic-level visibility didn't exist** — when a feature spanned multiple tickets and PRs, there was no easy way to see the overall testing health of the whole Epic before it shipped.

I wanted to fix both without building a complex system from scratch. I used **OpenSpec** — a spec-driven development workflow with AI — to go from idea to working PoC in a few days, without needing to be a Python expert. OpenSpec helped me define requirements, design decisions, and implementation tasks in plain language before writing any code, which let Claude handle most of the heavy lifting.

The result is a tool that the team can use directly inside **Cursor**, without context switching, to get real answers about their PRs before they ship.

---

## The Problem

Code review tells you *what* changed. CI coverage tells you *what percentage* of lines are covered. Neither tells you *whether the tests are actually good*.

A PR can have 80% coverage and still have:
- Tests that don't assert anything meaningful
- Production logic added with no test counterpart
- Coverage inflated by pre-existing tests that happen to run the new code

The result: noise and uncertainty about whether a feature is truly ready to deploy.

---

## What This Tool Does

Analyzes every merged PR and answers: **"How well was this change tested?"**

For each PR it produces:

| Signal | What it means |
|---|---|
| **Testing Quality Score (0–10)** | Composite score: coverage + test/prod ratio + file pairing + AI qualitative judgment |
| **AI Report** | Free-form narrative from Claude: what's untested, specific suggestions, risk areas |
| **LLM Coverage Estimate** | Claude reads the actual diff and estimates % of changed logic covered by tests |
| **Test Type Breakdown** | Unit / Integration / E2E counts |

The AI judgment is aligned with **FloQast testing standards**: meaningful assertions, behavior-focused tests, no coverage inflation.

---

## How It Works

The tool runs as an **MCP server** — a background process that Cursor can call as a tool, just like a function. The idea was to put the analysis capabilities directly where developers already work, so there's no context switch and no separate dashboard to check.

```
Developer asks Cursor:
"Analyze CLOSE-12688 for me"
         ↓
Cursor calls the MCP tool
         ↓
Tool fetches PR from GitHub → reads the diff → calls Claude → returns score + report
         ↓
Cursor shows the full analysis in chat
```

No manual steps. No copy-pasting diffs. No switching tabs.

---

## What You Can Ask It

- `"Analyze PR #4422"` → full metrics + AI report for one PR
- `"Analyze ticket CLOSE-12688"` → same, but you only need the Jira key
- `"Analyze the CLOSE-999 Epic"` → analyzes every PR across all child tickets
- `"List all of @username's PRs in the last 30 days"` → discovery then analyze one by one
- `"Summarize testing quality for repo X in the last 30 days"` → team trend report

---

## Real Numbers (Workflows Team, last ~30 days)

| PR | Title | Score |
|---|---|---|
| #2093 | feat: add strictSignOff settings to CompanySchema | **10.0** |
| #5477 | Set strictSignoff from strictSignoffEnabled | **10.0** |
| #124 | implement lock route for reconciliations | **8.2** |
| #717 | Add Harness feature flags | **7.2** |
| #4422 | Update isAuthorizedForSignoff helper | **6.8** |
| #123 | M1 recs service item unlock route | **4.0** |
| #121 | Define lock and unlock contracts | **0.0** *(config-only, no tests needed)* |

Scores of 0.0 on contract/config-only PRs are expected — the tool detects when there's no testable code.

---

## How Another Team Could Use It

1. Point the MCP server at your GitHub org (`GITHUB_TOKEN` + `.env`)
2. Add it to Cursor or Claude Desktop (one JSON config line)
3. Start asking questions about your own PRs

No code changes to your repos. No CI pipeline modifications. Runs entirely from GitHub's API.

The same OpenSpec workflow I used to build this is available to anyone — so if a team wanted to extend the tool or build something similar for their own pain points, the path is the same: define the spec, let the AI implement, iterate fast.

---

## What It Doesn't Do (Yet)

- It doesn't block merges or post comments on PRs automatically (read-only)
- Coverage numbers are AI-estimated when CI artifacts aren't available
- Works best for repos with clear test file conventions (`.test.ts`, `test_*.py`, etc.)
