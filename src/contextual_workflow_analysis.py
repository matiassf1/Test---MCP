"""Workflow-aware PR analysis: grounded in Jira (ticket + epic), Confluence, and repo docs.

No hardcoded product rules (signoff/SIL/etc.) — the model infers risks only from supplied context + diff.
"""

from __future__ import annotations

from typing import Optional

from src.file_classification import is_generated, is_test_file
from src.models import JiraIssue, PRMetrics

_MAX_PATCH = 2600
_MAX_FILES = 6

_SYSTEM = """You are a staff-level reviewer. Your job is to compare a pull request against the **workflow and product context** supplied by the organization (Jira ticket, Epic, internal wiki, repository documentation).

## Rules
1. **Infer only from provided context.** Do not assume domain rules (authorization, signoff, locks, flags, roles) unless they appear explicitly in the Epic, ticket, Confluence excerpts, or repo docs.
2. **Ground every finding** in either: (a) a quote or paraphrase of the supplied context, or (b) a concrete line of behavior visible in the PR diff.
3. **Avoid noise:** do not list "correct denials" or intended restrictions as risks. Do not give generic coding advice.
4. If context is thin or contradictory, say so once and keep findings minimal.

## Output (markdown)

## Workflow context analysis

### Findings
For each: **Severity** (blocker/high/medium/low), **Category** (scope|workflow|authz|parity|docs|other), **Evidence** (context + diff), **Location** (path), **Suggested check**.

### Verification gaps
At most 2 bullets: behaviors the **Epic/ticket/wiki** imply but the **diff/tests** do not clearly cover. Omit if none.

### Impact
**LOW** | **MEDIUM** | **HIGH** — one line, tied to business/compliance only if context mentions it.

If nothing substantive:
## Workflow context analysis
✅ No material gaps detected from the available context and diff.
_Note: broader risks may exist outside supplied documentation._"""


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
        rich += 450  # linked ticket: always ground analysis (title + diff at minimum)
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

    # Inject pre-built domain context into the system prompt when available.
    # The framing matters: the LLM must understand this is authoritative input
    # for inference, not background reading.
    system = _SYSTEM
    if domain_context.strip():
        domain_block = (
            "\n\n---\n\n"
            "## Organizational Domain Context\n\n"
            "The following DOMAIN CONTEXT was extracted from this organization's codebase, "
            "documentation, and incident history. Use it to:\n"
            "- Detect violations of domain invariants\n"
            "- Identify incorrect cross-module assumptions\n"
            "- Flag missing role coverage\n"
            "- Recognize known failure patterns before they reach production\n\n"
            "Treat every rule in section 2 (DOMAIN INVARIANTS) as a hard constraint. "
            "Treat every entry in section 6 (KNOWN FAILURE PATTERNS) as a red flag to actively look for.\n\n"
            + domain_context.strip()
        )
        system = _SYSTEM + domain_block

    try:
        return _call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
    except Exception:
        return "_Workflow context analysis failed (LLM error)._"
