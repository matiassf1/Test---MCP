from __future__ import annotations

import re
from typing import Iterable

from src.repo_analyzer.models import Signal

# Tokens that often appear in auth / workflow conditionals (generic, not domain-specific nouns)
_ROLE_TOKEN = re.compile(
    r"\b(preparer|reviewer|admin|auditor|approver|signer|operator|viewer|editor|owner|guest)\b",
    re.IGNORECASE,
)
_PERM_CALL = re.compile(
    r"\b(?:can[A-Z]\w*|hasPermission|isAuthorized|checkPermission|assertPermission)\s*\(",
)


def extract_role_signals(
    lines: Iterable[str],
    source_file: str,
    *,
    start_line: int = 1,
) -> list[Signal]:
    out: list[Signal] = []
    for i, line in enumerate(lines, start=start_line):
        if _PERM_CALL.search(line):
            out.append(
                Signal(
                    pattern_kind="role_pattern",
                    subtype="permission_call",
                    semantic_intent="authorization_check",
                    source_file=source_file,
                    line=i,
                    snippet=line.strip()[:200],
                    confidence=0.68,
                    tags=["auth_shape"],
                )
            )
        rm = _ROLE_TOKEN.search(line)
        if rm and ("if" in line or "?" in line or "&&" in line or "||" in line):
            out.append(
                Signal(
                    pattern_kind="role_pattern",
                    subtype="role_token_in_condition",
                    semantic_intent="role_condition",
                    source_file=source_file,
                    line=i,
                    snippet=line.strip()[:200],
                    confidence=0.45,
                    tags=["role_token", rm.group(1).lower()],
                )
            )
    return out
