"""Domain Context Enricher — merges mined artifacts into domain_context.md.

Uses guard markers <!-- BEGIN MINED --> / <!-- END MINED --> to isolate
machine-generated content from manually authored content. Idempotent.

Usage:
    enricher = DomainContextEnricher()
    enricher.enrich()  # runs all enrichment phases
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from src.config import settings

logger = logging.getLogger(__name__)

_BEGIN_MARKER = "<!-- BEGIN MINED -->"
_END_MARKER = "<!-- END MINED -->"

# Matches a section header like "## 4. FEATURE FLAGS" or "## 4. Feature Flags"
_SECTION_RE = re.compile(r"^(##\s+\d+\..*?)$", re.MULTILINE)


class DomainContextEnricher:
    """Enriches domain_context.md with mined artifacts using guard markers."""

    def __init__(
        self,
        domain_context_path: Optional[Path] = None,
        domain_knowledge_dir: Optional[Path] = None,
    ) -> None:
        root = Path(__file__).resolve().parent.parent
        self._ctx_path = domain_context_path or (root / settings.domain_context_path)
        self._knowledge_dir = domain_knowledge_dir or (root / settings.domain_knowledge_dir)

    def enrich(self) -> None:
        """Run all enrichment phases."""
        self.enrich_feature_flags()
        self.enrich_failure_patterns()
        self.enrich_repo_index()

    # ------------------------------------------------------------------
    # Public enrichment phases
    # ------------------------------------------------------------------

    def enrich_feature_flags(self) -> None:
        """Enrich §4 FEATURE FLAGS with mined Harness and tlcModules keys."""
        flags_path = self._knowledge_dir / "feature_flags.md"
        if not flags_path.exists():
            logger.info("DomainContextEnricher: feature_flags.md not found — skipping §4")
            return

        harness_lines, tlc_lines = _parse_feature_flags_md(flags_path)

        parts: list[str] = []
        if harness_lines:
            parts.append("### Harness Flags (mined)\n")
            parts.extend(harness_lines)
            parts.append("\n")
        if tlc_lines:
            parts.append("### tlcModules (mined)\n")
            parts.extend(tlc_lines)

        if not parts:
            content = "(no flags extracted — run feature-flag-extractor to populate)\n"
        else:
            content = "".join(parts)

        self._insert_or_replace_guard("FEATURE FLAGS", content)
        logger.info("DomainContextEnricher: enriched §4 Feature Flags")

    def enrich_failure_patterns(self) -> None:
        """Enrich §6 KNOWN FAILURE PATTERNS with mined Jira patterns (no duplicates)."""
        jira_path = self._knowledge_dir / "jira_patterns.md"
        if not jira_path.exists():
            logger.info("DomainContextEnricher: jira_patterns.md not found — skipping §6")
            return

        new_patterns = _parse_failure_patterns(jira_path)
        if not new_patterns:
            logger.info("DomainContextEnricher: no failure patterns in jira_patterns.md — skipping §6")
            return

        # Load current domain_context to find existing MANUALLY AUTHORED pattern names.
        # Strip mined guard blocks first so we don't count previously-mined patterns as
        # existing (which would cause them to be suppressed on re-runs → idempotency bug).
        ctx_text = self._read_ctx()
        ctx_without_mined = re.sub(
            r"<!-- BEGIN MINED -->.*?<!-- END MINED -->",
            "",
            ctx_text,
            flags=re.DOTALL,
        )
        existing_names = {
            m.lower()
            for m in re.findall(r"### Pattern(?:\s+name)?:\s*(.+)", ctx_without_mined)
        }

        guard_lines: list[str] = []
        for name, body in new_patterns:
            if name.lower() in existing_names:
                guard_lines.append(f"<!-- mined duplicate: {name} suppressed -->\n")
            else:
                guard_lines.append(f"### Pattern: {name}\n{body}\n")

        if guard_lines:
            self._insert_or_replace_guard("KNOWN FAILURE PATTERNS", "".join(guard_lines))
            logger.info("DomainContextEnricher: enriched §6 Failure Patterns (%d items)", len(guard_lines))

    def enrich_repo_index(self) -> None:
        """Add/update §10 REPO PRIORITY INDEX with top-10 repos from YAML."""
        index_path = self._knowledge_dir / "repo_priority_index.yaml"
        if not index_path.exists():
            logger.info("DomainContextEnricher: repo_priority_index.yaml not found — skipping §10")
            return

        try:
            with open(index_path, encoding="utf-8") as f:
                entries = yaml.safe_load(f) or []
        except Exception as exc:
            logger.warning("DomainContextEnricher: failed to read repo index: %s", exc)
            return

        top10 = entries[:10]
        lines: list[str] = []
        for entry in top10:
            repo = entry.get("repo", "")
            priority = entry.get("priority", "?")
            score = entry.get("score", 0)
            rationale = entry.get("rationale", "")
            areas = ", ".join(entry.get("domain_areas") or []) or "—"
            lines.append(
                f"- **{repo}** (priority: {priority}, score: {score})\n"
                f"  - Domain areas: {areas}\n"
                f"  - {rationale}\n"
            )

        content = "".join(lines) if lines else "(no repos indexed)\n"
        self._insert_or_replace_guard("REPO PRIORITY INDEX", content, create_section_if_absent=True,
                                      section_title="## 10. REPO PRIORITY INDEX")
        logger.info("DomainContextEnricher: enriched §10 Repo Priority Index (%d repos)", len(top10))

    # ------------------------------------------------------------------
    # Core guard-block manipulation
    # ------------------------------------------------------------------

    def _insert_or_replace_guard(
        self,
        section_keyword: str,
        content: str,
        create_section_if_absent: bool = False,
        section_title: Optional[str] = None,
    ) -> None:
        """Insert or replace a guard block inside the named section.

        ``section_keyword`` is matched case-insensitively against section headers.
        If the section doesn't exist and ``create_section_if_absent`` is True,
        the section + guard block is appended at the end of the file.
        """
        ctx_text = self._read_ctx()

        guard_block = f"{_BEGIN_MARKER}\n{content.rstrip()}\n{_END_MARKER}"

        # Find the section
        section_pattern = re.compile(
            r"(##\s+\d+\.\s*" + re.escape(section_keyword) + r"[^\n]*\n)",
            re.IGNORECASE,
        )
        match = section_pattern.search(ctx_text)

        if not match:
            if create_section_if_absent:
                title = section_title or f"## {section_keyword}"
                ctx_text = ctx_text.rstrip() + f"\n\n---\n\n{title}\n\n{guard_block}\n"
                self._write_ctx(ctx_text)
            else:
                logger.warning(
                    "DomainContextEnricher: section %r not found in domain_context.md — skipping",
                    section_keyword,
                )
            return

        # Find the extent of this section (up to the next ## header)
        section_start = match.start()
        next_section = _SECTION_RE.search(ctx_text, match.end())
        section_end = next_section.start() if next_section else len(ctx_text)

        section_text = ctx_text[section_start:section_end]

        # Check for existing guard block in this section
        begin_idx = section_text.find(_BEGIN_MARKER)
        end_idx = section_text.find(_END_MARKER)

        if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
            # Replace existing guard block
            new_section = (
                section_text[:begin_idx]
                + guard_block
                + section_text[end_idx + len(_END_MARKER):]
            )
        else:
            # Append guard block at end of section
            new_section = section_text.rstrip() + "\n\n" + guard_block + "\n"

        new_ctx = ctx_text[:section_start] + new_section + ctx_text[section_end:]
        self._write_ctx(new_ctx)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _read_ctx(self) -> str:
        if self._ctx_path.exists():
            return self._ctx_path.read_text(encoding="utf-8")
        return ""

    def _write_ctx(self, content: str) -> None:
        self._ctx_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_feature_flags_md(path: Path) -> tuple[list[str], list[str]]:
    """Return (harness_lines, tlcmodules_lines) from feature_flags.md."""
    harness: list[str] = []
    tlc: list[str] = []
    current: Optional[list[str]] = None

    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        stripped = line.strip()
        if "## Harness Flags" in stripped:
            current = harness
        elif "## tlcModules" in stripped:
            current = tlc
        elif current is not None and stripped.startswith("- `"):
            current.append(line)

    return harness, tlc


def _parse_failure_patterns(path: Path) -> list[tuple[str, str]]:
    """Return list of (pattern_name, body) from jira_patterns.md.

    Accepts both ``### Pattern: <Name>`` and ``### Pattern name: <Name>`` headers
    (LLM output varies in which format it uses).
    """
    text = path.read_text(encoding="utf-8")
    # Match both "### Pattern: Name" and "### Pattern name: Name"
    pattern_blocks = re.split(r"(?=### Pattern(?:\s+name)?:)", text)
    results: list[tuple[str, str]] = []

    for block in pattern_blocks:
        m = re.match(r"### Pattern(?:\s+name)?:\s*(.+?)\n(.*)", block, re.DOTALL)
        if m:
            name = m.group(1).strip()
            body = m.group(2).strip()
            if name:
                results.append((name, body))

    return results
