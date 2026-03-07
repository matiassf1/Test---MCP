from __future__ import annotations

import json
from typing import Optional

from src.models import AIAnalysis, PRMetrics


# ---------------------------------------------------------------------------
# Heuristics shared with ChangeAnalyzer (duplicated to avoid circular imports)
# ---------------------------------------------------------------------------

_GENERATED_SEGMENTS = {"/generated/", "/__generated__/", "/gen/", "/.generated/"}
_GENERATED_SUFFIXES = (".generated.ts", ".generated.js", ".generated.py", ".g.ts", ".pb.ts", "_pb2.py")
_TEST_PATTERNS = (".test.", ".spec.", "test_", "_test.")


def _is_generated(filename: str) -> bool:
    n = filename.replace("\\", "/").lower()
    return any(seg in n for seg in _GENERATED_SEGMENTS) or any(
        n.endswith(s) for s in _GENERATED_SUFFIXES
    )


def _is_test_file(filename: str) -> bool:
    import os
    base = os.path.basename(filename).lower()
    n = filename.replace("\\", "/").lower()
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or ".test." in base
        or ".spec." in base
        or "/tests/" in n
        or "/test/" in n
        or "/__tests__/" in n
    )


# ---------------------------------------------------------------------------
# AI Analyzer
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior engineer reviewing test coverage quality for a GitHub PR.

Rules:
- Generated files (src/generated/, *.generated.ts, *.pb.ts, etc.) are already excluded — ignore them.
- Judge only hand-written production code vs hand-written tests.
- Name specific untested functions/classes; suggest concrete test cases.
- Score 0–10: 0–3 critical gaps | 4–5 major paths missing | 6–7 minor gaps | 8–9 good | 10 comprehensive

Return ONLY valid JSON (no markdown):
{"assessment":"<2-3 sentences>","untested_areas":["<fn/module>"],"suggestions":["<test case>"],"ai_quality_score":<0-10>,"reasoning":"<1-2 sentences>"}"""

_MAX_PATCH_CHARS = 3000   # per file — trimmed for token savings
_MAX_PROD_FILES_WITH_PATCH = 5
_MODIFIED_PATCH_THRESHOLD = 40  # only include patch for modified files with >40 additions


class AIAnalyzer:
    """Uses Claude to qualitatively assess PR testing quality.

    Only runs when the ``anthropic`` package is installed and
    ``ANTHROPIC_API_KEY`` is available.  All failures are silently swallowed
    so the rest of the pipeline is never blocked.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        import anthropic  # imported lazily — optional dependency
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def analyze(self, metrics: PRMetrics) -> AIAnalysis:
        """Return Claude's qualitative assessment of this PR's test quality."""
        prompt = self._build_prompt(metrics)

        with self._client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=800,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            final = stream.get_final_message()

        # With thinking enabled there may be thinking blocks before the text block
        text = next(b.text for b in final.content if b.type == "text")
        data = json.loads(text)
        return AIAnalysis.model_validate(data)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, m: PRMetrics) -> str:
        prod_files = [
            fc for fc in m.file_changes
            if not _is_generated(fc.filename) and not _is_test_file(fc.filename)
            and fc.status != "removed"
        ]
        test_file_changes = [
            fc for fc in m.file_changes
            if not _is_generated(fc.filename) and _is_test_file(fc.filename)
        ]

        # Most-changed production files first
        prod_files.sort(key=lambda fc: fc.additions, reverse=True)

        # Header: compact key:value format
        lines: list[str] = [f"PR #{m.pr_number} [{m.repo}]: {m.title}"]
        if m.jira_issue:
            ji = m.jira_issue
            lines.append(f"Jira: {ji.key} ({ji.issue_type or 'Issue'}) — {ji.summary or ''}")
        lines.append(
            f"Metrics: prod_lines+={m.production_lines_added} "
            f"test_lines+={m.test_lines_added} "
            f"ratio={m.test_code_ratio:.2f}"
        )
        lines.append("")

        # Production files — full patch only for added files or significantly modified ones
        lines.append(f"PROD FILES ({len(prod_files)}):")
        for fc in prod_files[:_MAX_PROD_FILES_WITH_PATCH]:
            include_patch = fc.patch and (
                fc.status == "added"
                or fc.additions > _MODIFIED_PATCH_THRESHOLD
            )
            lines.append(f"  {fc.filename} [{fc.status}, +{fc.additions}]")
            if include_patch:
                patch = fc.patch[:_MAX_PATCH_CHARS]  # type: ignore[index]
                if len(fc.patch) > _MAX_PATCH_CHARS:  # type: ignore[arg-type]
                    patch += "\n...[truncated]"
                lines.append(f"```diff\n{patch}\n```")

        if len(prod_files) > _MAX_PROD_FILES_WITH_PATCH:
            rest = prod_files[_MAX_PROD_FILES_WITH_PATCH:]
            lines.append("  (more: " + ", ".join(fc.filename for fc in rest) + ")")

        lines.append("")

        # Test files — always include patch for added test files (most informative)
        if not test_file_changes:
            lines.append("TEST FILES: none")
        else:
            lines.append(f"TEST FILES ({len(test_file_changes)}):")
            for fc in test_file_changes:
                lines.append(f"  {fc.filename} [{fc.status}, +{fc.additions}]")
                if fc.patch and fc.status == "added":
                    patch = fc.patch[:_MAX_PATCH_CHARS]
                    if len(fc.patch) > _MAX_PATCH_CHARS:
                        patch += "\n...[truncated]"
                    lines.append(f"```diff\n{patch}\n```")

        lines.append("\nReturn only the JSON.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Safe factory
# ---------------------------------------------------------------------------

def try_analyze(metrics: PRMetrics) -> tuple[Optional[AIAnalysis], Optional[str]]:
    """Run AI analysis and return (result, error_message).

    Returns (AIAnalysis, None) on success, or (None, reason) on failure.
    Never raises.
    """
    try:
        from src.config import settings
        api_key = settings.anthropic_api_key or None
        if not api_key:
            return None, "ANTHROPIC_API_KEY not set"
        analyzer = AIAnalyzer(api_key=api_key)
        return analyzer.analyze(metrics), None
    except Exception as exc:
        return None, str(exc)
