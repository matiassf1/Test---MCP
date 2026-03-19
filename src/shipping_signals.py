"""Feature-flag inventory, legacy-path detection, and ship recommendation for PR reports."""

from __future__ import annotations

import re
from typing import Literal

from src.file_classification import is_test_file
from src.models import PRMetrics

_FLAG_RE = re.compile(
    r"featureFlag\(\s*['\"]([^'\"]+)['\"]"
    r"|isEnabled\(\s*['\"]([^'\"]+)['\"]"
    r"|useFeatureFlag\(\s*['\"]([^'\"]+)['\"]"
    r"|FEATURE_([A-Z_][A-Z0-9_]{3,})",
    re.IGNORECASE,
)


def extract_flags_from_text(text: str) -> set[str]:
    flags: set[str] = set()
    for m in _FLAG_RE.finditer(text or ""):
        flag = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if flag:
            flags.add(flag.strip())
    return flags


def analyze_feature_flags(prod_diff: str, test_diff: str) -> tuple[list[str], list[str], list[str]]:
    """Return (sorted prod flags, sorted flags also referenced in tests, sorted untested)."""
    prod = extract_flags_from_text(prod_diff)
    test = extract_flags_from_text(test_diff)
    tested = sorted(prod & test)
    untested = sorted(prod - test)
    return sorted(prod), tested, untested


def legacy_touched_files(file_changes: list, segments: list[str]) -> list[str]:
    """Prod files whose path contains any configured legacy segment (case-insensitive)."""
    if not segments:
        return []
    segs = [s.strip().lower() for s in segments if s.strip()]
    out: list[str] = []
    for fc in file_changes or []:
        if is_test_file(fc.filename):
            continue
        norm = fc.filename.replace("\\", "/").lower()
        if any(seg in norm for seg in segs):
            p = fc.filename.replace("\\", "/")
            if p not in out:
                out.append(p)
    return out


ShipVerdict = Literal["SHIP", "SHIP_WITH_CONDITIONS", "REVIEW", "INFORMATIONAL"]


def compute_ship_verdict(m: PRMetrics) -> tuple[ShipVerdict, list[str]]:
    """Return recommended gate + up to 5 executive bullets (English, for report)."""
    bullets: list[str] = []

    if getattr(m, "is_contract_only", False):
        return "INFORMATIONAL", [
            "**Contract / spec change** — merge policy is team-specific; tests usually follow in implementation PRs.",
            "**Next step:** Confirm API consumers and versioning with your team process.",
        ]

    if not m.has_testable_code:
        return "INFORMATIONAL", [
            "**Non-code PR** (config, i18n, docs) — no test-quality gate applies.",
            "**Next step:** Use your usual review process for this change type.",
        ]

    flags_prod = list(getattr(m, "feature_flags_in_pr", []) or [])
    flags_untested = list(getattr(m, "feature_flags_untested", []) or [])
    legacy = list(getattr(m, "legacy_touched_files", []) or [])
    drs = getattr(m, "domain_risk_signals", None)
    hard_n = 0
    hard_inv = 0
    if drs and getattr(drs, "signals", None):
        hard_n = sum(1 for s in drs.signals if getattr(s, "is_hard", False))
        hard_inv = sum(
            1
            for s in drs.signals
            if getattr(s, "is_hard", False) and getattr(s, "type", "") == "invariant_violation"
        )
    domain_hot = bool(
        drs
        and drs.domain_context_loaded
        and (
            hard_inv >= 1
            or hard_n >= 2
            or (getattr(drs, "heuristic_llm_contradictions", None) or [])
        )
    )
    risk = (m.risk_level or "LOW").upper()
    score = float(m.testing_quality_score or 0)
    spec_v = len(m.spec_violations or [])
    try:
        cov = float(m.effective_coverage or 0.0)
    except (TypeError, ValueError):
        cov = 0.0

    # Build bullets
    bullets.append(
        f"**Testing score:** {score:.2f}/10 · **Risk:** {risk} · **Estimated change coverage:** {cov * 100:.0f}%"
    )

    if domain_hot:
        bullets.append(
            "**Domain context:** invariant or failure-pattern signals from `domain_context.md` — review **Domain Risk Analysis** before merge."
        )

    if flags_prod:
        if flags_untested:
            bullets.append(
                f"**Feature flags in diff:** {len(flags_prod)} — **{len(flags_untested)} without toggle/assert in test diffs** "
                f"({', '.join(flags_untested[:5])}{'…' if len(flags_untested) > 5 else ''})."
            )
        else:
            bullets.append(
                f"**Feature flags:** {len(flags_prod)} referenced in prod; all appear in test diffs in this PR."
            )
    else:
        bullets.append("**Feature flags:** none detected in production diff (heuristic).")

    if legacy:
        short = [f"`{x.split('/')[-1]}`" for x in legacy[:4]]
        bullets.append(
            f"**Legacy / sensitive paths:** {len(legacy)} file(s) — {', '.join(short)}"
            f"{'…' if len(legacy) > 4 else ''}. Consider extra smoke or e2e after deploy."
        )
    else:
        bullets.append("**Legacy paths:** none matched configured segments.")

    verdict: ShipVerdict = "SHIP"
    reasons: list[str] = []

    if domain_hot and verdict == "SHIP":
        verdict = "SHIP_WITH_CONDITIONS"
        reasons.append("Domain Risk Analysis flagged invariant/pattern alignment issues.")

    if risk == "HIGH":
        verdict = "REVIEW"
        reasons.append("HIGH heuristic risk (auth, flags, or branching vs score).")
    elif risk == "MEDIUM":
        if score < 7.0 or flags_untested or legacy or spec_v > 0:
            verdict = "SHIP_WITH_CONDITIONS"
            reasons.append("MEDIUM risk plus score < 7, flags, legacy, or spec notes.")
        # else: strong score + clean signals → treat as SHIP

    if score < 5.0:
        verdict = "REVIEW"
        reasons.append(f"Score {score:.1f} < 5.")
    elif score < 6.5 and verdict == "SHIP":
        verdict = "SHIP_WITH_CONDITIONS"
        reasons.append(f"Score {score:.1f} below 6.5.")

    if flags_untested and verdict == "SHIP":
        verdict = "SHIP_WITH_CONDITIONS"
        reasons.append("Feature flag(s) in prod diff not referenced in test diffs.")

    if legacy and verdict == "SHIP":
        verdict = "SHIP_WITH_CONDITIONS"
        reasons.append("Touches configured legacy/sensitive path segments.")

    if spec_v > 0 and verdict == "SHIP":
        verdict = "SHIP_WITH_CONDITIONS"
        reasons.append(f"{spec_v} spec-vs-impl note(s) from AI audit.")

    if (
        m.change_coverage == 0.0
        and m.llm_estimated_coverage is None
        and m.production_lines_added > 30
        and verdict == "SHIP"
    ):
        verdict = "SHIP_WITH_CONDITIONS"
        reasons.append("No coverage signal for a large change.")

    if m.tests_added == 0 and m.production_lines_added > 20 and verdict == "SHIP":
        verdict = "SHIP_WITH_CONDITIONS"
        reasons.append("Large prod change with no new tests.")

    action = {
        "SHIP": "Proceed with normal merge; still run standard CI and code review.",
        "SHIP_WITH_CONDITIONS": "Merge if rollout plan + on-call + smoke on legacy/flag paths are agreed.",
        "REVIEW": "Hold for deeper review or added tests before merge.",
        "INFORMATIONAL": "Use team process for non-code or contract-only changes.",
    }[verdict]

    out: list[str] = []
    if reasons and verdict not in ("SHIP", "INFORMATIONAL"):
        out.append("**Why:** " + "; ".join(dict.fromkeys(reasons)))
    out.extend(bullets)
    out.append(f"**Next step:** {action}")
    return verdict, out[:8]


def populate_shipping_metadata(
    m: PRMetrics,
    prod_diff: str,
    test_diff: str,
    legacy_segments: list[str],
) -> None:
    prod_flags, tested, untested = analyze_feature_flags(prod_diff, test_diff)
    m.feature_flags_in_pr = prod_flags
    m.feature_flags_tested_in_pr = tested
    m.feature_flags_untested = untested
    m.legacy_touched_files = legacy_touched_files(m.file_changes or [], legacy_segments)


def finalize_ship_summary(m: PRMetrics) -> None:
    v, bullets = compute_ship_verdict(m)
    m.ship_verdict = v
    m.ship_executive_summary = bullets
