"""Copy detector — identifies near-duplicate code blocks within a PR diff.

Uses difflib.SequenceMatcher (stdlib, language-agnostic) to flag pairs of files
with similarity ≥ 0.75 and extracts differing boolean guard expressions so the
LLM can verify domain adaptation.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

from src.models import FileChange

_MIN_BLOCK_LINES = 5
_SIMILARITY_THRESHOLD = 0.75

# Regex patterns for boolean guard expressions
_GUARD_RE = re.compile(
    r"""
    (?:
        if\s*\(\s*!?\s*\w[\w.]*\s*\)   # if (!x) or if (x)
      | &&\s*!?\s*\w[\w.]*              # && !x or && x
      | \|\|\s*!?\s*\w[\w.]*            # || !x or || x
      | !\s*\w[\w.]*                    # !x standalone
    )
    """,
    re.VERBOSE,
)


def _normalize(code: str) -> str:
    """Strip comments, collapse whitespace, drop blank lines for comparison."""
    # Remove single-line // comments
    code = re.sub(r"//.*$", "", code, flags=re.MULTILINE)
    # Remove block /* */ comments
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    # Remove # comments (Python)
    code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
    # Collapse runs of whitespace to single space per line
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in code.splitlines()]
    # Drop blank lines
    return "\n".join(ln for ln in lines if ln)


def _extract_blocks(patch: Optional[str]) -> list[str]:
    """Extract contiguous non-trivial code blocks of ≥ MIN_BLOCK_LINES from a diff patch."""
    if not patch:
        return []
    # Strip diff +/- markers, keep only added/context lines (ignore removed lines)
    code_lines: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            code_lines.append(line[1:])
        elif not line.startswith("-") and not line.startswith("@@") and not line.startswith("diff"):
            code_lines.append(line)

    normalized = _normalize("\n".join(code_lines))
    lines = normalized.splitlines()

    if len(lines) < _MIN_BLOCK_LINES:
        return []

    # Slide a window of MIN_BLOCK_LINES to produce overlapping blocks
    blocks: list[str] = []
    step = _MIN_BLOCK_LINES
    for i in range(0, len(lines) - _MIN_BLOCK_LINES + 1, step):
        block = "\n".join(lines[i: i + max(_MIN_BLOCK_LINES, 10)])
        blocks.append(block)

    # Also add the full normalized content as one large block for whole-file comparison
    blocks.append(normalized)
    return blocks


def _extract_guards(code: str) -> set[str]:
    """Extract boolean guard expressions from code."""
    return {m.group(0).strip() for m in _GUARD_RE.finditer(code)}


def _differing_guards(block_a: str, block_b: str) -> list[str]:
    """Return guard expressions present in block_a but absent or negated in block_b."""
    guards_a = _extract_guards(block_a)
    guards_b = _extract_guards(block_b)
    # Guards in A not in B (candidate domain-specific guards)
    diff = guards_a - guards_b
    return sorted(diff)


class CopyDetector:
    """Detects near-duplicate code blocks across files in a PR diff."""

    def detect(self, file_changes: list[FileChange]) -> list[dict]:
        """Compare all pairs of files with extractable code; return flag dicts for similar pairs.

        Each flag dict:
          source_file, target_file, similarity (0-1), differing_guards (list[str])
        """
        # Build (filename → normalized full content) map
        candidates: list[tuple[str, str]] = []
        for fc in file_changes:
            if not fc.patch:
                continue
            normalized = _normalize(fc.patch)
            lines = [ln for ln in normalized.splitlines() if ln]
            if len(lines) < _MIN_BLOCK_LINES:
                continue
            candidates.append((fc.filename, "\n".join(lines)))

        if len(candidates) < 2:
            return []

        flags: list[dict] = []
        seen: set[frozenset[str]] = set()

        for i, (name_a, content_a) in enumerate(candidates):
            for name_b, content_b in candidates[i + 1:]:
                pair = frozenset({name_a, name_b})
                if pair in seen:
                    continue
                seen.add(pair)

                ratio = SequenceMatcher(None, content_a, content_b).ratio()
                if ratio >= _SIMILARITY_THRESHOLD:
                    diff_guards = _differing_guards(content_a, content_b)
                    flags.append({
                        "source_file": name_a,
                        "target_file": name_b,
                        "similarity": round(ratio, 3),
                        "differing_guards": diff_guards,
                        "note": "guard may be domain-specific" if diff_guards else "",
                    })

        return flags
