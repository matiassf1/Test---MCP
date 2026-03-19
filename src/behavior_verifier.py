"""Diff-aware verification: heuristics become hypotheses verified against behavior change.

When a heuristic fires (e.g. invariant_violation), we check whether the diff actually
shows evidence of behavior change (guard removed, bypass added). If not, we downgrade
the signal so "hard" does not override LLM when there is no supporting evidence.

See docs/BEHAVIOR-VERIFIER-DESIGN.md.
"""

from __future__ import annotations

import re
from typing import Literal

# Removed lines: look like guard (early return/throw or auth check)
_GUARD_LIKE = re.compile(
    r"\b(if|else\s+if)\s*\([^)]*\)\s*(?:return|throw)\b"
    r"|(?:isAuthorized\w*|canSign\w*|hasPermission\w*|checkPermission\w*|deny|forbid)\s*\(",
    re.IGNORECASE,
)
# Added lines: possible bypass (e.g. early return on condition that skips strict path)
_BYPASS_LIKE = re.compile(
    r"\bif\s*\([^)]*\)\s*\{?\s*(return|throw)\b",
    re.IGNORECASE,
)


def _removed_and_added_lines(prod_diff: str) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    added: list[str] = []
    for line in prod_diff.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-") and len(line) > 1:
            removed.append(line[1:].strip())
        elif line.startswith("+") and len(line) > 1:
            added.append(line[1:].strip())
    return removed, added


def verify_behavior_change(
    prod_diff: str,
    signal_type: str,
    description: str,
) -> Literal["verified", "not_verified", "inconclusive"]:
    """Determine if the diff supports the heuristic (guard removed or bypass added).

    Returns:
        verified: Evidence of behavior change that could violate the rule → keep hard.
        not_verified: No such evidence → downgrade (e.g. UI-only, no guards removed).
        inconclusive: Cannot tell from diff alone.
    """
    if signal_type not in ("invariant_violation", "failure_pattern"):
        return "inconclusive"

    removed, added = _removed_and_added_lines(prod_diff)

    # Evidence 1: guard removed
    for line in removed:
        if len(line) < 10:
            continue
        if _GUARD_LIKE.search(line):
            return "verified"

    # Evidence 2: bypass added (new early return that might skip strict path)
    for line in added:
        if len(line) < 10:
            continue
        if _BYPASS_LIKE.search(line):
            return "verified"

    # No evidence of behavior change in diff
    if removed or added:
        return "not_verified"
    return "inconclusive"


def apply_verifier_to_signals(
    prod_diff: str,
    signals: list,
    *,
    downgrade_confidence_factor: float = 0.35,
    inconclusive_confidence_factor: float = 1.0,
) -> None:
    """In-place: for invariant_violation and failure_pattern with is_hard=True, run
    verify_behavior_change; if not_verified, set is_hard=False and reduce confidence."""
    for s in signals:
        if getattr(s, "source", None) != "heuristic":
            continue
        if getattr(s, "type", None) not in ("invariant_violation", "failure_pattern"):
            continue
        if not getattr(s, "is_hard", False):
            continue
        outcome = verify_behavior_change(prod_diff, s.type, s.description)
        if outcome == "not_verified":
            s.is_hard = False
            s.confidence = min(1.0, max(0.0, s.confidence * downgrade_confidence_factor))
            if hasattr(s, "validation_status"):
                s.validation_status = "dismissed"
                s.validation_reason = (
                    "Diff shows no guard removal or bypass matching this signal (behavior verifier)."
                )
                s.validation_source = "behavior_verifier"
        elif outcome == "inconclusive" and inconclusive_confidence_factor < 1.0:
            s.confidence = min(1.0, max(0.0, s.confidence * inconclusive_confidence_factor))
