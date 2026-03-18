from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from src.file_classification import is_test_file
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

# Roles as standalone tokens in *added* prod lines (reduces noise from removed context)
_ROLE_RE = re.compile(
    r"\b(preparer|reviewer|ops|admin|sso|superAdmin|auditor|manager|approver|signer)\b",
    re.IGNORECASE,
)

# Prod dirs where any co-located-folder test file counts as covering new modules
_CLUSTER_DIRS = frozenset({"helpers", "utils", "lib", "services"})


# ---------------------------------------------------------------------------
# Auth / test pairing
# ---------------------------------------------------------------------------


def _test_paths_in_pr(file_changes: list) -> set[str]:
    return {fc.filename.replace("\\", "/") for fc in file_changes if is_test_file(fc.filename)}


def _auth_flagged_prod_files(file_changes: list) -> list[str]:
    seen: list[str] = []
    for fc in file_changes:
        if is_test_file(fc.filename):
            continue
        if _AUTH_FILE_RE.search(fc.filename):
            p = fc.filename.replace("\\", "/")
            if p not in seen:
                seen.append(p)
    return seen


def _prod_module_covered_by_tests(prod_path: str, test_paths: set[str]) -> bool:
    """True if this prod file has a colocated test OR (in helpers/utils/...) any test in same folder."""
    p = Path(prod_path.replace("\\", "/"))
    stem = p.stem
    parent = p.parent.as_posix()
    tp_norm = {t.replace("\\", "/") for t in test_paths}

    for suffix in (".test.js", ".test.jsx", ".test.ts", ".test.tsx"):
        cand = f"{parent}/{stem}{suffix}"
        if cand in tp_norm:
            return True

    folder = p.parent.name.lower()
    if folder in _CLUSTER_DIRS:
        prefix = parent + "/"
        for tp in tp_norm:
            if not tp.startswith(prefix):
                continue
            if ".test." in tp or "/__tests__/" in tp:
                return True
    return False


def _auth_signal(
    prod_diff: str,
    files_summary: list,
    file_changes: list,
    untested_flags: list[str],
) -> tuple[int, str]:
    """Return (points 0–3, evidence string). 0 = not triggered."""
    auth_prod = _auth_flagged_prod_files(file_changes)
    test_paths = _test_paths_in_pr(file_changes)

    if auth_prod:
        covered = sum(1 for f in auth_prod if _prod_module_covered_by_tests(f, test_paths))
        n = len(auth_prod)
        if untested_flags:
            pts = 3
            detail = f"Authorization-related files modified ({n}): {', '.join(Path(f).name for f in auth_prod[:4])}"
            if covered == n:
                detail += " — tests updated in PR, but feature-flag gaps remain"
            return pts, detail

        if covered >= n:
            return 2, (
                f"Authorization-related files modified with matching test updates in this PR "
                f"({covered}/{n} modules covered: {', '.join(Path(f).name for f in auth_prod[:4])})"
            )
        if covered > 0:
            return 3, (
                f"Authorization-related files modified; partial test coverage in PR "
                f"({covered}/{n} modules with tests): {', '.join(Path(f).name for f in auth_prod[:4])}"
            )
        return 3, (
            f"Authorization-related files modified without test files in this PR: "
            f"{', '.join(Path(f).name for f in auth_prod[:4])}"
        )

    triggered_files = []
    for f in files_summary:
        name = f.get("file", "") if isinstance(f, dict) else getattr(f, "filename", "")
        if name and _AUTH_FILE_RE.search(name):
            triggered_files.append(name)
    if triggered_files:
        return 3, f"Authorization-related files modified: {', '.join(triggered_files[:3])}"

    code_hits = len(_AUTH_CODE_RE.findall(prod_diff))
    if code_hits >= 3:
        return 3, f"Authorization patterns in diff ({code_hits} occurrences)"
    return 0, ""


def _flag_signal(prod_diff: str, test_diff: str) -> list[str]:
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
    added = [l for l in prod_diff.split("\n") if l.startswith("+") and not l.startswith("+++")]
    if not added:
        return 0.0
    behavioral = len(_CONDITIONAL_RE.findall("\n".join(added)))
    return behavioral / len(added)


def _role_gap(prod_diff: str, test_diff: str) -> list[str]:
    added_prod = "\n".join(
        ln for ln in prod_diff.split("\n") if ln.startswith("+") and not ln.startswith("+++")
    )
    prod_roles = {m.group(1).lower() for m in _ROLE_RE.finditer(added_prod)}
    test_roles = {m.group(1).lower() for m in _ROLE_RE.finditer(test_diff)}
    return sorted(prod_roles - test_roles)


def _role_points(role_gaps: list[str], testing_quality_score: float) -> tuple[int, str]:
    if not role_gaps:
        return 0, ""
    n = len(role_gaps)
    base = 2 if n >= 2 else 1
    # Strong tests: role tokens often differ between prod helpers and mock users — attenuate
    if testing_quality_score >= 7.5:
        base = min(base, 1)
        msg = (
            f"Roles in new/changed code not all named in tests: {', '.join(role_gaps)} "
            f"_(attenuated: quality score {testing_quality_score:.1f} ≥ 7.5 — review if mocks should cover these actors)_"
        )
    elif testing_quality_score >= 6.5:
        base = 1 if n >= 2 else base
        msg = (
            f"Roles in new/changed code not all named in tests: {', '.join(role_gaps)} "
            f"_(partially attenuated given score {testing_quality_score:.1f})_"
        )
    else:
        msg = f"Roles/actors in production not exercised in tests: {', '.join(role_gaps)}"
    return base, msg


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_risk(
    metrics: PRMetrics,
    prod_diff: str,
    test_diff: str,
    llm_risk_suggestion: Optional[str] = None,
) -> tuple[str, int, list[str], list[dict], Optional[str]]:
    """Compute risk level from static heuristics, optionally upgraded by LLM signal.

    Returns:
        risk_level, risk_points, risk_factors, risk_breakdown, risk_context_note
        risk_breakdown: [{"label": str, "points": int}, ...]
    """
    points = 0
    factors: list[str] = []
    breakdown: list[dict] = []
    file_changes = metrics.file_changes or []
    files_summary = [{"file": fc.filename} for fc in file_changes]

    untested_flags = _flag_signal(prod_diff, test_diff)
    auth_pts, auth_evidence = _auth_signal(
        prod_diff, files_summary, file_changes, untested_flags
    )
    if auth_pts > 0:
        points += auth_pts
        factors.append(auth_evidence)
        breakdown.append({"label": "Authorization / signoff surface", "points": auth_pts})

    if untested_flags:
        points += 2
        factors.append(f"Feature flags without test toggle: {', '.join(untested_flags[:3])}")
        breakdown.append({"label": "Untested feature flags", "points": 2})

    ratio = _behavioral_ratio(prod_diff)
    if ratio > 0.4 and metrics.testing_quality_score < 6.0:
        points += 2
        msg = (
            f"High behavioral change ratio ({ratio:.0%}) with low quality score "
            f"({metrics.testing_quality_score})"
        )
        factors.append(msg)
        breakdown.append({"label": "Branching-heavy diff + low test score", "points": 2})

    role_gaps = _role_gap(prod_diff, test_diff)
    rp, role_msg = _role_points(role_gaps, metrics.testing_quality_score)
    if rp > 0:
        points += rp
        factors.append(role_msg)
        breakdown.append({"label": "Role / actor coverage gap", "points": rp})

    if points >= 5:
        level = "HIGH"
    elif points >= 3:
        level = "MEDIUM"
    else:
        level = "LOW"

    context_note: Optional[str] = None
    if level in ("MEDIUM", "HIGH") and metrics.testing_quality_score >= 7.0:
        context_note = (
            f"**Testing quality is strong ({metrics.testing_quality_score}/10).** "
            "Heuristic risk reflects *inherent* sensitivity (auth, flags, roles), not necessarily missing tests. "
            "Use the factor breakdown below to see what drove the score."
        )
    elif level == "LOW" and auth_pts >= 2:
        context_note = (
            "Authorization-related code is present but test updates in this PR align well with the change."
        )

    if llm_risk_suggestion:
        _RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        _FROM_RANK = {1: "LOW", 2: "MEDIUM", 3: "HIGH"}
        current = _RANK.get(level, 1)
        suggested = _RANK.get(llm_risk_suggestion.strip().upper(), 0)
        if suggested > current:
            level = _FROM_RANK.get(min(current + 1, 3), level)

    return level, points, factors, breakdown, context_note
