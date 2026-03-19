from __future__ import annotations

import re
from typing import Iterable

from src.repo_analyzer.models import Signal

_FLAG_RE = re.compile(
    r"featureFlag\s*\(\s*['\"]([^'\"]+)['\"]"
    r"|isEnabled\s*\(\s*['\"]([^'\"]+)['\"]"
    r"|useFeatureFlag\s*\(\s*['\"]([^'\"]+)['\"]"
    r"|getFeatureFlag\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def extract_flag_signals(
    lines: Iterable[str],
    source_file: str,
    *,
    start_line: int = 1,
) -> list[Signal]:
    out: list[Signal] = []
    for i, line in enumerate(lines, start=start_line):
        for m in _FLAG_RE.finditer(line):
            name = next((g for g in m.groups() if g), None)
            if not name:
                continue
            out.append(
                Signal(
                    pattern_kind="feature_flag_behavior",
                    subtype="flag_read",
                    semantic_intent="conditional_feature_toggle",
                    source_file=source_file,
                    line=i,
                    snippet=line.strip()[:200],
                    confidence=0.82,
                    tags=["flag", name[:80]],
                )
            )
    return out
