from __future__ import annotations

import re
from typing import Iterable

from src.repo_analyzer.models import Signal

_INVARIANT_COMMENT = re.compile(
    r"//\s*(?:must|never|should not|do not)\s+.+"  # JS line comment
    r"|#\s*(?:must|never|should not|do not)\s+.+",  # Python
    re.IGNORECASE,
)
_TRY_CATCH = re.compile(r"\btry\s*\{", re.IGNORECASE)


def extract_failure_signals(
    lines: Iterable[str],
    source_file: str,
    *,
    start_line: int = 1,
    is_test_file: bool = False,
) -> list[Signal]:
    """Comments with invariant language; try/catch shape in prod files only."""
    out: list[Signal] = []
    for i, line in enumerate(lines, start=start_line):
        if _INVARIANT_COMMENT.search(line):
            out.append(
                Signal(
                    pattern_kind="failure_pattern_candidate",
                    subtype="invariant_comment",
                    semantic_intent="documented_constraint",
                    source_file=source_file,
                    line=i,
                    snippet=line.strip()[:200],
                    confidence=0.4,
                    tags=["comment"],
                )
            )
        if not is_test_file and _TRY_CATCH.search(line):
            out.append(
                Signal(
                    pattern_kind="failure_pattern_candidate",
                    subtype="try_block",
                    semantic_intent="error_handling_path",
                    source_file=source_file,
                    line=i,
                    snippet=line.strip()[:120],
                    confidence=0.35,
                    tags=["structure"],
                )
            )
    return out
