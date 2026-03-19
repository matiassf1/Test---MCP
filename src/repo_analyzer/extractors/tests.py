from __future__ import annotations

import re
from typing import Iterable

from src.repo_analyzer.models import Signal

_IT_DESC = re.compile(
    r"\b(?:it|test)\s*\(\s*['\"]([^'\"]{1,200})['\"]",
    re.IGNORECASE,
)
_EXPECT_THROW = re.compile(
    r"expect\s*\([^)]*\)\.(?:toThrow|rejects?|toBeRejected)\b",
    re.IGNORECASE,
)
_EXPECT_FALSE = re.compile(
    r"expect\s*\([^)]*\)\.toBe\s*\(\s*false\s*\)",
    re.IGNORECASE,
)
_DESCRIBE = re.compile(
    r"\bdescribe\s*\(\s*['\"]([^'\"]{1,200})['\"]",
    re.IGNORECASE,
)


def _intent_from_name(name: str) -> str:
    lower = name.lower()
    if any(x in lower for x in ("must not", "should not", "cannot", "can't", "fail", "reject", "deny", "unauthorized", "forbidden", "invalid")):
        return "negative_case_expectation"
    if any(x in lower for x in ("should", "must", "allows", "can ")):
        return "positive_case_expectation"
    return "test_case_description"


def extract_test_behavior_signals(
    lines: Iterable[str],
    source_file: str,
    *,
    start_line: int = 1,
) -> list[Signal]:
    out: list[Signal] = []
    for i, line in enumerate(lines, start=start_line):
        for m in _IT_DESC.finditer(line):
            name = m.group(1).strip()
            out.append(
                Signal(
                    pattern_kind="test_behavior",
                    subtype="it_or_test_block",
                    semantic_intent=_intent_from_name(name),
                    source_file=source_file,
                    line=i,
                    snippet=name[:200],
                    confidence=0.62,
                    tags=["jest", "vitest"],
                )
            )
        for m in _DESCRIBE.finditer(line):
            name = m.group(1).strip()
            out.append(
                Signal(
                    pattern_kind="test_behavior",
                    subtype="describe_block",
                    semantic_intent=_intent_from_name(name),
                    source_file=source_file,
                    line=i,
                    snippet=name[:200],
                    confidence=0.5,
                    tags=["jest", "vitest"],
                )
            )
        if _EXPECT_THROW.search(line) or _EXPECT_FALSE.search(line):
            out.append(
                Signal(
                    pattern_kind="test_behavior",
                    subtype="expect_failure",
                    semantic_intent="unauthorized_or_error_expected",
                    source_file=source_file,
                    line=i,
                    snippet=line.strip()[:200],
                    confidence=0.75,
                    tags=["assertion"],
                )
            )
    return out
