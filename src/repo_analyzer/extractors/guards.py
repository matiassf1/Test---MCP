from __future__ import annotations

import re
from typing import Iterable

from src.repo_analyzer.models import Signal

# Structural: early exit on condition (no product-specific identifiers required)
_LINE_GUARD = re.compile(
    r"\bif\s*\([^)]{1,400}\)\s*(?:return|throw)\b",
    re.IGNORECASE,
)
# Optional: deny-style helper calls (shape, not business names)
_DENY_CALL = re.compile(
    r"\b(?:deny|forbid|reject|abort)\s*\(",
    re.IGNORECASE,
)


def extract_guard_signals(
    lines: Iterable[str],
    source_file: str,
    *,
    start_line: int = 1,
) -> list[Signal]:
    out: list[Signal] = []
    for i, line in enumerate(lines, start=start_line):
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("#"):
            continue
        if _LINE_GUARD.search(line):
            snip = line.strip()[:200]
            out.append(
                Signal(
                    pattern_kind="guard_pattern",
                    subtype="early_return_guard",
                    semantic_intent="deny_on_condition",
                    source_file=source_file,
                    line=i,
                    snippet=snip,
                    confidence=0.72,
                    tags=["structure"],
                )
            )
        elif _DENY_CALL.search(line):
            out.append(
                Signal(
                    pattern_kind="guard_pattern",
                    subtype="explicit_deny_call",
                    semantic_intent="deny_api",
                    source_file=source_file,
                    line=i,
                    snippet=line.strip()[:200],
                    confidence=0.55,
                    tags=["structure"],
                )
            )
    return out
