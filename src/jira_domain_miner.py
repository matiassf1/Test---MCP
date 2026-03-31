"""Jira Domain Miner — bulk mines Jira project tickets for domain failure patterns.

Fixes the 0-result failure in the pipeline by broadening the issue type filter
from Bug/Incident to Story/Task/Bug/Incident/Epic.

Writes structured output to domain_knowledge/jira_patterns.md via the
existing JIRA_MINING_SYSTEM LLM prompt.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.config import settings
from src.jira_invariant_extractor import JiraInvariantContext, JiraInvariantExtractor

logger = logging.getLogger(__name__)

_DEFAULT_ISSUE_TYPES = ["Story", "Task", "Bug", "Incident", "Epic"]


class JiraDomainMiner:
    """Bulk Jira mining for the domain knowledge pipeline."""

    def __init__(self, jira_service=None) -> None:
        from src.jira_service import JiraService
        self._jira = jira_service or JiraService()
        self._extractor = JiraInvariantExtractor()

    def mine(
        self,
        project: str,
        issue_types: Optional[list[str]] = None,
        max_tickets: int = 100,
        since_days: int = 180,
    ) -> JiraInvariantContext:
        """Query the Jira project, extract invariants, and return merged context."""
        if not self._jira.is_available():
            logger.warning("JiraDomainMiner: Jira not configured — skipping")
            return JiraInvariantContext()

        types = issue_types or _DEFAULT_ISSUE_TYPES
        tickets = self._jira.search_project_tickets(
            project=project,
            issue_types=types,
            max_tickets=max_tickets,
            since_days=since_days,
        )
        logger.info("JiraDomainMiner: fetched %d tickets from %s", len(tickets), project)

        if not tickets:
            return JiraInvariantContext()

        contexts = self._extractor.extract_batch(tickets)
        return JiraInvariantExtractor.merge_batch(contexts)

    def mine_and_write(
        self,
        project: str,
        issue_types: Optional[list[str]] = None,
        max_tickets: int = 100,
        since_days: int = 180,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Mine Jira, summarize via LLM, and write jira_patterns.md."""
        out = output_path or Path(settings.domain_knowledge_dir) / "jira_patterns.md"
        out.parent.mkdir(parents=True, exist_ok=True)

        if not self._jira.is_available():
            stub = "# Jira Patterns\n(Jira not configured — set JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)\n"
            out.write_text(stub, encoding="utf-8")
            return out

        types = issue_types or _DEFAULT_ISSUE_TYPES
        tickets = self._jira.search_project_tickets(
            project=project,
            issue_types=types,
            max_tickets=max_tickets,
            since_days=since_days,
        )

        total = len(tickets)
        header = (
            f"Mined: {total} tickets (latest {min(total, max_tickets)} of {total}) "
            f"updated in last {since_days} days\n\n"
        )

        if not tickets:
            content = (
                f"# Jira Patterns\n{header}"
                "## Failure Patterns\n"
                "(no domain failure patterns identified in the mined tickets)\n"
            )
            out.write_text(content, encoding="utf-8")
            logger.info("JiraDomainMiner: 0 tickets found for project %s — wrote stub", project)
            return out

        summary = self._summarize(tickets, project)
        sources = self._format_sources(tickets, project)
        content = f"# Jira Patterns\n{header}{summary.rstrip()}\n\n{sources}\n"

        out.write_text(content, encoding="utf-8")
        logger.info("JiraDomainMiner: wrote %d tickets → %s", total, out)
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _summarize(self, tickets: list[dict], project: str) -> str:
        """Summarize tickets via LLM or fall back to raw bullet list."""
        from src.domain_knowledge_pipeline import _JIRA_MINING_SYSTEM

        parts: list[str] = []
        for t in tickets:
            desc = (t.get("description") or "")[:400]
            parts.append(f"**{t['key']}** ({t.get('issuetype', '')}): {t.get('summary', '')}\n{desc}")

        user_content = (
            f"# Jira Tickets — {project} ({len(parts)} tickets)\n\n"
            + "\n\n---\n".join(parts)
        )

        try:
            from src.ai_reporter import _call_llm, _is_ai_enabled
            if not _is_ai_enabled():
                raise RuntimeError("AI disabled")

            result = _call_llm([
                {"role": "system", "content": _JIRA_MINING_SYSTEM},
                {"role": "user", "content": user_content},
            ])
            return result or _raw_bullet_fallback(tickets)
        except Exception as exc:
            logger.info("JiraDomainMiner: LLM unavailable (%s) — writing raw summaries", exc)
            return _raw_bullet_fallback(tickets)

    def _format_sources(self, tickets: list[dict], project: str) -> str:
        lines = ["## Sources\n"]
        for t in tickets:
            url = t.get("url") or f"{(settings.jira_url or '').rstrip('/')}/browse/{t['key']}"
            lines.append(
                f"- [{t['key']}: {t.get('summary', '')}]({url}) (type: {t.get('issuetype', '')})\n"
            )
        return "".join(lines)


def _raw_bullet_fallback(tickets: list[dict]) -> str:
    lines = ["## Raw Ticket Summaries\n(AI summarization disabled)\n\n"]
    for t in tickets:
        lines.append(f"- **{t['key']}** ({t.get('issuetype', '')}): {t.get('summary', '')}\n")
    return "".join(lines)
