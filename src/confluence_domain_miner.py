"""Confluence Domain Miner — bulk mines Confluence spaces and labels for domain rules.

Fixes the 0-result failure in the pipeline by using space-scoped CQL queries
instead of file-path keyword search.

Writes structured output to domain_knowledge/confluence_rules.md via the
existing CONFLUENCE_MINING_SYSTEM LLM prompt.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.confluence_service import ConfluencePage, ConfluenceService, build_confluence_context
from src.config import settings

logger = logging.getLogger(__name__)

_CONTENT_BUDGET = 12_000  # characters fed to LLM


class ConfluenceDomainMiner:
    """Bulk Confluence mining for the domain knowledge pipeline."""

    def __init__(self, confluence_service: Optional[ConfluenceService] = None) -> None:
        _conf_user = (
            getattr(settings, "confluence_username", "") or
            getattr(settings, "jira_username", "")
        )
        self._confluence = confluence_service or ConfluenceService(
            base_url=settings.confluence_base_url,
            token=settings.confluence_token,
            username=_conf_user,
        )

    def mine(
        self,
        spaces: list[str],
        query_terms: list[str],
        labels: list[str] | None = None,
        max_results_per_space: int = 20,
    ) -> list[ConfluencePage]:
        """Return deduplicated pages from space-scoped and label-based searches.

        Space-scoped results are prioritized over label-based results.
        """
        if not self._confluence.is_available():
            logger.warning("ConfluenceDomainMiner: Confluence not configured — skipping")
            return []

        seen_ids: set[str] = set()
        pages: list[ConfluencePage] = []

        # Space-scoped searches first (higher priority)
        for space_key in spaces:
            try:
                found = self._confluence.search_by_space(
                    space_key=space_key,
                    query_terms=query_terms,
                    max_results=max_results_per_space,
                )
                for page in found:
                    if page.page_id not in seen_ids:
                        seen_ids.add(page.page_id)
                        pages.append(page)
                logger.info("ConfluenceDomainMiner: space=%r → %d pages", space_key, len(found))
            except Exception as exc:
                logger.warning("ConfluenceDomainMiner: space %r search failed: %s", space_key, exc)

        # Label-based fallback / supplement
        for label in (labels or []):
            try:
                found = self._confluence.search_by_label(label=label, max_results=10)
                added = 0
                for page in found:
                    if page.page_id not in seen_ids:
                        seen_ids.add(page.page_id)
                        pages.append(page)
                        added += 1
                if added:
                    logger.info("ConfluenceDomainMiner: label=%r → %d new pages", label, added)
            except Exception as exc:
                logger.warning("ConfluenceDomainMiner: label %r search failed: %s", label, exc)

        return pages

    def mine_and_write(
        self,
        spaces: list[str],
        query_terms: list[str],
        labels: list[str] | None = None,
        output_path: Optional[Path] = None,
        max_results_per_space: int = 20,
    ) -> Path:
        """Mine Confluence, summarize via LLM, and write confluence_rules.md."""
        out = output_path or Path(settings.domain_knowledge_dir) / "confluence_rules.md"
        out.parent.mkdir(parents=True, exist_ok=True)

        pages = self.mine(spaces=spaces, query_terms=query_terms, labels=labels,
                          max_results_per_space=max_results_per_space)

        if not pages:
            stub = (
                "# Confluence Rules\n"
                f"(No pages found — spaces searched: {', '.join(spaces)}; "
                f"queries: {', '.join(query_terms)})\n"
            )
            out.write_text(stub, encoding="utf-8")
            logger.warning("ConfluenceDomainMiner: 0 pages found — wrote stub to %s", out)
            return out

        # Enforce content budget
        context = build_confluence_context(pages, budget=_CONTENT_BUDGET)

        # LLM summarization (or plain-text fallback)
        summary = self._summarize(context, len(pages))

        # Append sources
        sources = self._format_sources(pages)
        content = summary.rstrip() + "\n\n" + sources + "\n"

        out.write_text(content, encoding="utf-8")
        logger.info("ConfluenceDomainMiner: wrote %d pages → %s", len(pages), out)
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _summarize(self, context: str, page_count: int) -> str:
        """Run LLM summarization or fall back to plain text dump."""
        from src.domain_knowledge_pipeline import _CONFLUENCE_MINING_SYSTEM

        try:
            from src.ai_reporter import _call_llm, _is_ai_enabled
            if not _is_ai_enabled():
                raise RuntimeError("AI disabled")

            user = f"# Confluence Documentation ({page_count} pages)\n\n{context}"
            result = _call_llm([
                {"role": "system", "content": _CONFLUENCE_MINING_SYSTEM},
                {"role": "user", "content": user},
            ])
            return result or _plain_text_fallback(context, page_count)
        except Exception as exc:
            logger.info("ConfluenceDomainMiner: LLM unavailable (%s) — writing plain text", exc)
            return _plain_text_fallback(context, page_count)

    def _format_sources(self, pages: list[ConfluencePage]) -> str:
        """Build ## Sources section with page metadata."""
        base = settings.confluence_base_url.rstrip("/")
        lines = ["## Sources\n"]
        for page in pages:
            url = f"{base}/pages/{page.page_id}" if base else f"(id: {page.page_id})"
            lines.append(f"- [{page.title}]({url}) (id: {page.page_id})\n")
        return "".join(lines)


def _plain_text_fallback(context: str, page_count: int) -> str:
    """Plain-text dump used when AI is disabled."""
    return (
        f"# Confluence Rules\n"
        f"(AI summarization disabled — raw content from {page_count} pages)\n\n"
        f"{context[:8000]}"
    )
