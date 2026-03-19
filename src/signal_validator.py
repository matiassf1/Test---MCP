"""Evidence resolution layer: detection (heuristics) → validation → risk.

Heuristic domain signals are treated as *candidates*. After workflow LLM output and
DOMAIN_STRUCT merge, we can **dismiss** signals when structured LLM context contradicts
a hard invariant hit (e.g. VIOLATED_INVARIANTS is NONE while heuristics fired).

Placed between ``merge_llm_domain_struct`` and ``compute_risk``. See
``docs/EVIDENCE-RESOLUTION-LAYER.md``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models import DomainRiskSignals, DomainSignal, HeuristicLLMContradiction

_SAFE_NARRATIVE = re.compile(
    r"no\s+violation|reinforces?\s|immutability|UI[-\s]?only|does\s+not\s+modify\s+.{0,48}auth"
    r"|without\s+changing\s+.{0,32}(authorization|signoff|permission)",
    re.IGNORECASE | re.DOTALL,
)


def _text_overlap(a: str, b: str, n: int = 2) -> bool:
    wa = set(re.findall(r"[a-z]{4,}", a.lower()))
    wb = set(re.findall(r"[a-z]{4,}", b.lower()))
    return len(wa & wb) >= n


def _signal_matches_contradiction(
    sig: "DomainSignal",
    c: "HeuristicLLMContradiction",
) -> bool:
    if c.heuristic_signal_type and sig.type != c.heuristic_signal_type:
        return False
    return _text_overlap(sig.description, c.heuristic_description, n=2)


def _claim_suggests_no_violations(claim: str) -> bool:
    cl = claim.lower()
    if "none" in cl or "no invariant" in cl or "empty" in cl:
        return True
    if "no " in cl and "violation" in cl:
        return True
    return False


def apply_evidence_resolution(
    sig: "DomainRiskSignals",
    workflow_markdown: str,
    prod_diff: str,
    *,
    _settings: Any | None = None,
) -> None:
    """In-place: mark candidates, dismiss when evidence supports it, confirm the rest.

    ``prod_diff`` reserved for future rules (e.g. second-pass checks).
    ``_settings`` is for tests only (object with the same attrs as ``Settings``).
    """
    del prod_diff  # MVP: LLM struct + optional narrative only

    if _settings is None:
        try:
            from src.config import settings as _settings
        except Exception:
            return

    if not getattr(_settings, "domain_evidence_validation_enabled", False):
        return

    dismiss_on_none = getattr(_settings, "domain_evidence_dismiss_on_llm_no_violations", True)
    narrative = getattr(_settings, "domain_evidence_narrative_dismissal", False)

    contradictions = list(sig.heuristic_llm_contradictions or [])

    # Promote remaining hard heuristics to candidates (skip already dismissed e.g. behavior verifier)
    for s in sig.signals:
        if s.source != "heuristic":
            continue
        if s.validation_status == "dismissed":
            continue
        if s.is_hard and s.validation_status == "unvalidated":
            s.validation_status = "candidate"

    def _should_dismiss_invariant(s: "DomainSignal") -> bool:
        if s.source != "heuristic" or s.type != "invariant_violation" or not s.is_hard:
            return False
        if dismiss_on_none:
            for c in contradictions:
                if c.heuristic_signal_type != "invariant_violation":
                    continue
                if not _claim_suggests_no_violations(c.llm_claim):
                    continue
                if _signal_matches_contradiction(s, c):
                    return True
        if narrative and workflow_markdown and _SAFE_NARRATIVE.search(workflow_markdown):
            if any(_signal_matches_contradiction(s, c) for c in contradictions):
                return True
        return False

    for s in sig.signals:
        if not _should_dismiss_invariant(s):
            continue
        s.is_hard = False
        s.validation_status = "dismissed"
        s.validation_reason = (
            "Workflow DOMAIN_STRUCT / LLM context reported no invariant violations while this "
            "heuristic fired; treated as false positive for risk scoring."
        )
        s.validation_source = "evidence_layer"

    # Update contradiction resolutions when we dismissed matching heuristics
    for c in sig.heuristic_llm_contradictions:
        if c.resolution != "heuristic_precedence":
            continue
        for s in sig.signals:
            if s.validation_status != "dismissed" or s.validation_source != "evidence_layer":
                continue
            if _signal_matches_contradiction(s, c):
                c.resolution = "evidence_dismissed"
                break

    # Confirm surviving hard heuristics
    for s in sig.signals:
        if s.source != "heuristic" or not s.is_hard:
            continue
        if s.validation_status == "candidate":
            s.validation_status = "confirmed"
            s.validation_reason = s.validation_reason or (
                "No dismissal rule matched; heuristic counts toward risk."
            )
            s.validation_source = "evidence_layer"


def validated_hard_signals(signals: list) -> list:
    """Signals that still count as hard for risk (excludes dismissed)."""
    out = []
    for s in signals or []:
        if not getattr(s, "is_hard", False):
            continue
        if getattr(s, "validation_status", "unvalidated") == "dismissed":
            continue
        out.append(s)
    return out


def uncertain_domain_signals(signals: list) -> list:
    """Heuristic signals marked uncertain (partial risk weight)."""
    return [
        s
        for s in (signals or [])
        if getattr(s, "source", None) == "heuristic"
        and getattr(s, "validation_status", "") == "uncertain"
    ]
