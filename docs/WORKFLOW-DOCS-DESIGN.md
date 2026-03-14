# Core Workflow Documentation — Design & Feasibility

## Summary

**Yes, it’s feasible.** The tool already has the right data sources (Jira, GitHub, and our own analysis). Documenting core workflows and prioritizing them is a matter of **consuming those resources** and **wiring a small integration** that produces a single, prioritized workflow doc.

---

## Resources Already Available

| Resource | What we have | Use for workflow docs |
|----------|----------------|------------------------|
| **Jira** | `fetch_issue(epic_key)` → summary, description, type, status, priority; `fetch_epic_issues(epic_key)` → child tickets (Stories, Tasks, Bugs) | **Source of truth** for workflow scope: Epic = workflow, description = narrative, children = steps/tickets. Prioritization via Epic/ticket priority. |
| **GitHub** | PR search by ticket key (title/branch/body); repo, PR number, title | Link “implementation” to each ticket; optional “merged PRs” section per workflow. |
| **Our tool** | Stored PR metrics (score, coverage, scope alignment); Epic report generator | Optional “health” summary per workflow (e.g. “3 PRs, avg score 8.2, 1 scope concern”). |

No new external APIs are required. We only need to **call existing services** and **add a doc generator** that turns that into Markdown (or another format).

---

## What “Core Workflows” Means Here

- **Within an Epic:** The **core workflows** are its **child tickets** (Stories, Tasks, Bugs). **Stories** = main flows; **Tasks/Bugs** = supporting. The doc lists children with Stories first so the principal ones are easy to interpret.
- **How we get a clear picture:** The **Epic description** infers the main flows; together with **Stories/Tasks/Bugs descriptions** (from Jira) and **PR content** (when available), the doc gives a single, clear view of the workflows. The generator includes Epic description and **child ticket descriptions** (table excerpt + full text per ticket).
- **Doc** = a single artifact (e.g. `docs/core-workflows.md`) that:
  1. Lists Epics **in priority order** (by Jira Epic priority).
  2. For each Epic: **title** (key + summary), **full Epic description**, then **child tickets** (Stories first) with key, summary, type, status, **description excerpt** in the table, plus **Ticket descriptions** (full text) per child. Optionally: PR links/summary.

---

## Integrations Implemented

1. **CLI command: `generate_workflow_docs`**  
   - Example:  
     `python -m src.cli generate_workflow_docs --epics "CLOSE-8615,OTHER-1" [--output docs/core-workflows.md]`  
   - Input: comma-separated Epic keys (prioritized by Jira Epic priority: Critical → High → Medium → Low).  
   - Output: one Markdown file (default `docs/core-workflows.md`) with a section per Epic: summary, description, and child tickets table.  
   - Options: `--title`, `--intro` for custom doc title and intro paragraph.

2. **Doc generator**  
   - For each Epic key: call `JiraService.fetch_issue(epic_key)` and `JiraService.fetch_epic_issues(epic_key)`.  
   - Sort Epics by priority (e.g. Critical → High → Medium → Low).  
   - Emit sections: Epic title, full Epic description, table of child tickets (key, summary, type, status, description excerpt), and **Ticket descriptions** (full text per child). Optional: PR discovery + storage for implementation summary.  
   - Optional: for each Epic, run the same PR discovery we use for Epic reports and, if storage has metrics for those PRs, add a short “Implementation / testing health” subsection.

3. **Prioritization**  
   - **Today:** order Epics by Jira `priority` (and optionally by `--epics` order as tiebreaker).  
   - **Later:** filter by Jira label (e.g. `core-workflow`) or JQL and then sort by priority.

---

## Optional Enhancements (Once Base Is in Place)

- **JQL / label-based discovery:** e.g. “all Epics with label `core-workflow`” so the team maintains the list in Jira instead of the CLI.
- **Enrich with our metrics:** for each Epic, discover linked PRs, load from storage, and add a line like “Merged PRs: 5; avg testing score 8.2; 1 PR with scope concerns.”
- **Single workflow doc vs. one file per Epic:** start with one doc; split by Epic later if needed.
- **Export formats:** Markdown first; HTML/PDF later if needed.

---

## Conclusion

The data and integrations are at hand. The main work is:

1. **Consume** Jira (Epic + children, summary, description, priority).  
2. **Optionally consume** GitHub (PRs per ticket) and our storage (metrics).  
3. **Generate** a single, prioritized workflow doc (Markdown) via a small generator and a CLI command.

This gives the team a single place to see “what are our core workflows, in order of importance, with scope and status.”
