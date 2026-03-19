"""Workflow-aware PR analysis: Jira, Confluence, repo docs + domain_context.md.

LLM must map findings to Domain Invariants (§2) and Known Failure Patterns (§6) when context exists.
"""

from __future__ import annotations

from typing import Optional

from src.file_classification import is_generated, is_test_file
from src.models import JiraIssue, PRMetrics

_MAX_PATCH = 2600
_MAX_FILES = 6

_SYSTEM_BASE = """You are a staff-level reviewer. Compare the PR to **workflow context** (Jira, Epic, wiki, repo docs) and, when provided, **Organizational Domain Context** (domain_context.md).

## Rules
1. Ground findings in supplied context + diff. No invented product rules.
2. **DOMAIN_STRUCT vs diff (critical):** The machine-readable block must reflect whether this PR’s **code change** can realistically break §2 invariants or trigger §6 patterns. If overlap is only keywords/paths (e.g. UI-only) and **authorization / guards / ordering** in the diff are unchanged, use `- NONE` under `VIOLATED_INVARIANTS`. The pipeline runs keyword heuristics first; an **evidence layer** then reconciles your `NONE` with those candidates — you are not “overriding” safety, you are supplying the semantic judgement the diff needs. In narrative sections, still note residual uncertainty when appropriate.
3. Every material finding must cite **which invariant or pattern** it relates to (or state "no mapping" if none apply).
4. Avoid noise: intended denials are not bugs.

## Required output structure (markdown)

## Workflow context analysis

### Findings mapped to Domain Invariants (Section 2)
- For each finding: invariant paraphrase → diff evidence → file path. Use `_None — no Section 2 violation identified._` if clean.

### Findings mapped to Known Failure Patterns (Section 6)
- For each: pattern name/quote → overlap with diff → path. Use `_None — no Section 6 pattern triggered._` if clean.

### Other findings
- Scope, workflow, authz not covered above (omit if none).

### Verification gaps
At most 2 bullets. Omit if none.

### Impact
**LOW** | **MEDIUM** | **HIGH** — one line.

If Domain Context is **absent**, omit the two mapping subsections and use a single **Findings** list instead.

---

**Mandatory machine-readable appendix** (exact format, end of message):

---DOMAIN_STRUCT---
VIOLATED_INVARIANTS:
- (bullet per Section 2 violation, or single line `- NONE`)
TRIGGERED_FAILURE_PATTERNS:
- (per Section 6, or `- NONE`)
CROSS_MODULE:
- (cross-MFE/import parity concerns, or `- NONE`)
MISSING_ROLES:
- (actors from Role Model §3 not evident in tests/diff, or `- NONE`)
---END_DOMAIN_STRUCT---
"""


def _context_richness(
    confluence: str,
    epic_md: str,
    repo_docs: str,
    pr_description: str,
    jira_issue: Optional[JiraIssue],
) -> int:
    n = len(confluence.strip()) + len(epic_md.strip()) + len(repo_docs.strip()) + len(pr_description.strip())
    if jira_issue:
        n += len((jira_issue.summary or "") + (jira_issue.description or ""))
    return n


def try_contextual_workflow_analysis(
    metrics: PRMetrics,
    *,
    confluence_context: str = "",
    epic_markdown: str = "",
    repo_docs_markdown: str = "",
    pr_description: str = "",
    jira_issue: Optional[JiraIssue] = None,
    domain_context: str = "",
) -> Optional[str]:
    """Return markdown analysis, a skip message, or None if AI is unavailable."""
    from src.ai_reporter import _call_llm, _is_ai_enabled

    if not metrics.has_testable_code:
        return "Workflow context analysis skipped (no production code in PR)."

    rich = _context_richness(
        confluence_context, epic_markdown, repo_docs_markdown, pr_description, jira_issue
    )
    if metrics.jira_ticket:
        rich += 450
    if rich < 400:
        return (
            "Workflow context analysis skipped: insufficient context "
            "(enable Jira + ticket, Confluence, or ensure repo docs/README are reachable)."
        )

    if not _is_ai_enabled():
        return (
            "_Workflow context analysis not run: configure AI "
            "(AI_ENABLED, OPENAI_API_KEY, OPENROUTER_API_KEY, or ANTHROPIC_API_KEY)._"
        )

    blocks: list[str] = [
        f"# PR #{metrics.pr_number} — {metrics.repo}",
        f"**Title:** {metrics.title}",
    ]
    if pr_description.strip():
        blocks.append(f"## PR description\n{pr_description.strip()[:3500]}")

    if jira_issue:
        blocks.append("## Jira ticket")
        blocks.append(f"**{jira_issue.key}** ({jira_issue.issue_type or 'Issue'}) — {jira_issue.summary or ''}")
        if jira_issue.description:
            blocks.append(jira_issue.description[:4500])
        if jira_issue.components:
            blocks.append(f"Components: {', '.join(jira_issue.components)}")

    if epic_markdown.strip():
        blocks.append(epic_markdown.strip())

    if confluence_context.strip():
        blocks.append("## Confluence / wiki (excerpts)\n" + confluence_context.strip()[:7000])

    if repo_docs_markdown.strip():
        blocks.append("## Repository documentation (excerpts)\n" + repo_docs_markdown.strip()[:8000])

    blocks.append("## Production diff (excerpt)")
    prod = [
        fc
        for fc in metrics.file_changes
        if fc.status != "removed" and not is_test_file(fc.filename) and not is_generated(fc.filename)
    ]
    prod.sort(key=lambda x: x.additions + x.deletions, reverse=True)
    for fc in prod[:_MAX_FILES]:
        blocks.append(f"### {fc.filename}")
        if fc.patch:
            p = fc.patch if len(fc.patch) <= _MAX_PATCH else fc.patch[:_MAX_PATCH] + "\n...[truncated]"
            blocks.append(f"```diff\n{p}\n```")

    user = "\n\n".join(blocks)

    system = _SYSTEM_BASE
    if domain_context.strip():
        system += (
            "\n\n---\n## Organizational Domain Context (authoritative)\n\n"
            "Map findings explicitly to **Section 2** and **Section 6** as required above.\n\n"
            + domain_context.strip()[:24000]
        )
    else:
        system += (
            "\n\n_No domain_context.md in this run — use simplified Findings only; "
            "still emit the DOMAIN_STRUCT block with `- NONE` for all four lists._"
        )

    try:
        return _call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
    except Exception:
        return "_Workflow context analysis failed (LLM error)._"
