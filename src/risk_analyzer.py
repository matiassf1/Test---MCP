from __future__ import annotations

import re
from typing import Optional

from src.models import PRMetrics

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

_AUTH_FILE_RE = re.compile(
    r"(auth|signoff|permission|role|guard|authorize|access|privilege|credential)",
    re.IGNORECASE,
)

_AUTH_CODE_RE = re.compile(
    r"(isAuthorized|hasPermission|canSignOff|isSSOEnabled|featureFlag|isEnabled"
    r"|throw.*nauthorized|\b403\b|\b401\b)",
    re.IGNORECASE,
)

_FLAG_RE = re.compile(
    r"featureFlag\(['\"]([^'\"]+)['\"]"
    r"|isEnabled\(['\"]([^'\"]+)['\"]"
    r"|FEATURE_([A-Z_]{4,})",
)

_CONDITIONAL_RE = re.compile(
    r"^\+[^+].*(\bif\b|\belse\b| && | \|\| |\?[^:]|return\s+(true|false)\b|switch\s*\()",
    re.MULTILINE,
)

_ROLE_RE = re.compile(
    r"\b(preparer|reviewer|ops|admin|sso|superAdmin|auditor|manager|approver|signer)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Individual signal detectors
# ---------------------------------------------------------------------------

def _auth_signal(prod_diff: str, files_summary: list) -> tuple[bool, str]:
    """Detect authorization-related file names or code patterns."""
    triggered_files = []
    for f in files_summary:
        name = f.get("file", "") if isinstance(f, dict) else getattr(f, "filename", "")
        if _AUTH_FILE_RE.search(name):
            triggered_files.append(name)

    if triggered_files:
        return True, f"Authorization-related files modified: {', '.join(triggered_files[:3])}"

    code_hits = len(_AUTH_CODE_RE.findall(prod_diff))
    if code_hits >= 3:
        return True, f"Authorization patterns detected in diff ({code_hits} occurrences)"

    return False, ""


def _flag_signal(prod_diff: str, test_diff: str) -> list[str]:
    """Return feature flags present in prod diff but not toggled in test diff."""
    def _extract_flags(text: str) -> set[str]:
        flags: set[str] = set()
        for m in _FLAG_RE.finditer(text):
            flag = m.group(1) or m.group(2) or m.group(3)
            if flag:
                flags.add(flag)
        return flags

    untested = _extract_flags(prod_diff) - _extract_flags(test_diff)
    return list(untested)


def _behavioral_ratio(prod_diff: str) -> float:
    """Fraction of added lines that contain conditional/branching logic."""
    added = [l for l in prod_diff.split("\n") if l.startswith("+") and not l.startswith("+++")]
    if not added:
        return 0.0
    behavioral = len(_CONDITIONAL_RE.findall("\n".join(added)))
    return behavioral / len(added)


def _role_gap(prod_diff: str, test_diff: str) -> list[str]:
    """Roles/actors mentioned in production code but absent from test code."""
    prod_roles = {m.group(1).lower() for m in _ROLE_RE.finditer(prod_diff)}
    test_roles = {m.group(1).lower() for m in _ROLE_RE.finditer(test_diff)}
    return list(prod_roles - test_roles)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_risk(
    metrics: PRMetrics,
    prod_diff: str,
    test_diff: str,
    llm_risk_suggestion: Optional[str] = None,
) -> tuple[str, int, list[str]]:
    """Compute risk level from static heuristics, optionally upgraded by LLM signal.

    Returns:
        (risk_level, risk_points, risk_factors)
        risk_level: "HIGH" | "MEDIUM" | "LOW"
        risk_points: raw integer score
        risk_factors: human-readable list of triggered signals
    """
    points = 0
    factors: list[str] = []

    # Build file list from file_changes (native PRMetrics field)
    files_summary = [
        {"file": fc.filename} for fc in (metrics.file_changes or [])
    ]

    # Auth signal (+3)
    auth_triggered, auth_evidence = _auth_signal(prod_diff, files_summary)
    if auth_triggered:
        points += 3
        factors.append(auth_evidence)

    # Feature flag gap (+2)
    untested_flags = _flag_signal(prod_diff, test_diff)
    if untested_flags:
        points += 2
        factors.append(f"Feature flags without test toggle: {', '.join(untested_flags[:3])}")

    # Behavioral ratio with low score (+2)
    ratio = _behavioral_ratio(prod_diff)
    if ratio > 0.4 and metrics.testing_quality_score < 6.0:
        points += 2
        factors.append(
            f"High behavioral change ratio ({ratio:.0%}) with low quality score ({metrics.testing_quality_score})"
        )

    # Role gap (+1 or +2)
    role_gaps = _role_gap(prod_diff, test_diff)
    if len(role_gaps) >= 2:
        points += 2
        factors.append(f"Roles/actors in production not exercised in tests: {', '.join(role_gaps)}")
    elif len(role_gaps) == 1:
        points += 1
        factors.append(f"Role not exercised in tests: {role_gaps[0]}")

    # Static threshold
    if points >= 5:
        level = "HIGH"
    elif points >= 3:
        level = "MEDIUM"
    else:
        level = "LOW"

    # LLM upgrade — one step only, never downgrade (task 3.7)
    if llm_risk_suggestion:
        _RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        _FROM_RANK = {1: "LOW", 2: "MEDIUM", 3: "HIGH"}
        current = _RANK.get(level, 1)
        suggested = _RANK.get(llm_risk_suggestion.strip().upper(), 0)
        if suggested > current:
            level = _FROM_RANK.get(min(current + 1, 3), level)

    return level, points, factors
