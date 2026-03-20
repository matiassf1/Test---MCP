# Demo Script — PR Testing Impact Analyzer
**Grooming · Tuesday 2026-03-18 · ~10 min**

**Other doc (Spanish index + cheat sheet + MCP tips):** [`docs/DEMO-GUIA.md`](docs/DEMO-GUIA.md) · [`docs/DEMO-HELPER.md`](docs/DEMO-HELPER.md)  
For a **lighter** live run (faster MCP): set `PR_ANALYZER_PROFILE=demo` in `.env` — see [`docs/DEMO-MCP-GUIDE.md`](docs/DEMO-MCP-GUIDE.md).

---

## Setup (before the meeting)

- [ ] MCP server running locally: `python mcp_server.py`
- [ ] Cursor open with the MCP tool configured and connected
- [ ] `.env` has `GITHUB_TOKEN` + **an LLM key** (Anthropic, OpenAI, or OpenRouter — match your setup)
- [ ] Optional for speed: `PR_ANALYZER_PROFILE=demo` (skips full narrative + second LLM pass by default)
- [ ] This file open on a second screen or phone

---

## Intro (1.5 min) — origin + problem

Start here — this is the most important minute:

> "This started from two things I kept running into on Workflows.
>
> First: test coverage numbers in CI don't tell you if the tests are actually good.
> A PR can show green coverage and still have tests that don't assert anything real.
> That created a lot of noise and uncertainty — especially right before deploying a feature.
>
> Second: when a feature spans multiple tickets and PRs, there was no easy way to see
> the overall testing health of the whole Epic. You'd have to check each PR manually.
>
> I wanted to fix both. But I don't know Python — the language this is built in.
> So I used OpenSpec, which is a spec-driven workflow where you write requirements and
> design decisions in plain language, and Claude implements them. That let me go from
> idea to working tool in a few days without needing to learn the language from scratch."

**One sentence before the demo:**
> "The result is a tool that lives inside Cursor. You ask it about your PR or your Jira ticket, and it tells you how well it was tested — specifically, not just a percentage."

---

## Part 1 — Analyze a PR by Jira ticket (3 min)

Type this in Cursor chat (or have it ready to paste):

```
Analyze ticket CLOSE-12688 for me
```

**What happens:** Cursor calls `analyze_pr_by_jira_ticket` → finds PR #4422 → fetches the diff → runs Claude → returns score + report.

**What to say while it loads:**
> "I gave it only the Jira ticket key. It found the PR on GitHub automatically."

**When the result appears, point to:**

1. **Score: 6.8/10** — "Good, but not great. There's real logic in this PR that isn't fully covered."
2. **AI report** — quote this line: *"The test for `getEffectiveStrictFlags` only tests the legacy flag and does not verify the granular flags."* — "This is Claude reading the actual diff, not just line counts."
3. **Tests added: 2** — "Two test files modified. The tool found which specific paths they missed."

**Key point to land:**
> "A developer looking at this PR would see 2 test files modified and think 'looks fine'. The tool flags exactly what's missing."

---

## Part 2 — Contrast: high score (1.5 min)

```
Get me the metrics for PR #2093
```

**Point to:**
- **Score: 10.0** — "Same author, different PR. When the test coverage is comprehensive, it reflects it."
- "This PR had a schema change with full test coverage — unit tests for every new field."

**Key point:**
> "The score is not a punishment tool. It recognizes good work too."

---

## Part 3 — Author trend (1.5 min)

```
Give me an author summary for c-matiasgabrielsfer in the last 30 days
```

**Point to:**
- Average score across PRs
- Which PRs dragged the average down vs. which were solid

**Key point:**
> "As a lead, you can see at a glance if someone's testing patterns are consistent or if one PR was an outlier."

---

## Part 4 — How any team could use it (2 min)

> "To set this up for another team, you need three things:"

1. **A GitHub token** for your org
2. **An Anthropic API key** (or OpenAI / OpenRouter)
3. **One JSON config line** in Cursor or Claude Desktop

> "You don't touch your CI pipeline. You don't add anything to your repos. It reads from GitHub's API."

Show the `.env` file briefly (with keys redacted) — makes it feel concrete and simple.

**If asked about cost:**
> "gpt-4o-mini costs fractions of a cent per PR. An Anthropic key for dev use runs a few dollars a month at this scale."

---

## Part 5 — Epic view (if time allows, ~1.5 min)

```
Analyze the CLOSE-11985 epic
```

> "For epics that span multiple PRs and tickets, you can get a report across the whole feature — not just one PR."

Point to:
- Child tickets discovered from Jira
- Per-PR scores aggregated
- `avg_testing_quality_score` for the whole epic

---

## Closing (45 sec)

> "This tool exists because of specific pain I saw in our own workflow — the uncertainty around test quality before shipping.
> The MCP approach means it lives where developers already are, no extra dashboards.
>
> And the fact that I built it with OpenSpec without being a Python dev is kind of the point —
> if another team has a similar pain point, they don't need to wait for engineering bandwidth.
> The workflow is the same: write the spec, implement with AI, iterate.
>
> Right now it's just me using it. If anyone wants to try it, setup is about 15 minutes
> and I'm happy to walk through it."

**Leave on screen:** the 6.8/10 report from Part 1 — it's the most concrete output.

---

## Likely questions

**"Can it post comments on PRs automatically?"**
> Not yet — it's read-only. That's a possible next step but I wanted to keep it non-intrusive first.

**"Does it work for frontend repos?"**
> Yes — it detects `.test.ts`, `.spec.ts`, etc. The AI report is language-agnostic since it reads the diff.

**"What if a PR legitimately doesn't need tests?"**
> It detects config-only and contract-only PRs and marks `has_testable_code: false` — score of 0.0 in those cases doesn't mean bad, it means nothing to test. PR #121 is an example.

**"Who else has access?"**
> Just me right now. It runs locally. If a team wanted to share it, you could deploy the MCP server to Railway or Render and point everyone's Cursor at the same instance.

**"You built this without knowing Python?"**
> Yes — I used OpenSpec to write the requirements and design decisions first, and Claude implemented them. I reviewed and iterated, but I didn't write most of the Python from scratch. That's actually part of what I wanted to show: you don't need to wait until you're an expert in a language to build something useful with it.

**"How long did it take?"**
> About a week from first idea to the MCP server being usable. The OpenSpec workflow kept it focused — each feature had a proposal, a spec, and a task list before any code was written.
