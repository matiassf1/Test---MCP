"""Evidence resolution: heuristic candidates dismissed when LLM DOMAIN_STRUCT contradicts."""

from __future__ import annotations

from types import SimpleNamespace

from src.domain_context_heuristics import sync_legacy_domain_lists
from src.models import (
    DomainRiskSignals,
    DomainSignal,
    HeuristicLLMContradiction,
)
from src.signal_validator import apply_evidence_resolution, validated_hard_signals


def test_validated_hard_signals_excludes_dismissed() -> None:
    s = DomainSignal(
        type="invariant_violation",
        description="x",
        source="heuristic",
        is_hard=True,
        validation_status="dismissed",
    )
    assert validated_hard_signals([s]) == []


def test_validated_hard_signals_keeps_confirmed_hard() -> None:
    s = DomainSignal(
        type="invariant_violation",
        description="x",
        source="heuristic",
        is_hard=True,
        validation_status="confirmed",
    )
    assert validated_hard_signals([s]) == [s]


def test_apply_evidence_resolution_dismisses_on_contradiction() -> None:
    st = SimpleNamespace(
        domain_evidence_validation_enabled=True,
        domain_evidence_dismiss_on_llm_no_violations=True,
        domain_evidence_narrative_dismissal=False,
    )
    sig = DomainRiskSignals(domain_context_loaded=True)
    inv = DomainSignal(
        type="invariant_violation",
        description="Possible overlap with invariant: preparer must sign before reviewer",
        source="heuristic",
        is_hard=True,
        confidence=0.9,
    )
    sig.signals.append(inv)
    sig.heuristic_llm_contradictions.append(
        HeuristicLLMContradiction(
            heuristic_description=inv.description,
            heuristic_signal_type="invariant_violation",
            llm_claim="DOMAIN_STRUCT listed no invariant violations (NONE or empty).",
        )
    )

    apply_evidence_resolution(sig, workflow_markdown="", prod_diff="", _settings=st)

    assert inv.is_hard is False
    assert inv.validation_status == "dismissed"
    assert inv.validation_source == "evidence_layer"
    assert sig.heuristic_llm_contradictions[0].resolution == "evidence_dismissed"


def test_apply_evidence_resolution_confirms_when_no_contradiction() -> None:
    st = SimpleNamespace(
        domain_evidence_validation_enabled=True,
        domain_evidence_dismiss_on_llm_no_violations=True,
    )
    sig = DomainRiskSignals(domain_context_loaded=True)
    inv = DomainSignal(
        type="invariant_violation",
        description="Some invariant concern",
        source="heuristic",
        is_hard=True,
    )
    sig.signals.append(inv)

    apply_evidence_resolution(sig, workflow_markdown="", prod_diff="", _settings=st)

    assert inv.is_hard is True
    assert inv.validation_status == "confirmed"


def test_sync_legacy_tag_dismissed() -> None:
    sig = DomainRiskSignals()
    sig.signals.append(
        DomainSignal(
            type="invariant_violation",
            description="x",
            source="heuristic",
            is_hard=False,
            validation_status="dismissed",
        )
    )
    sync_legacy_domain_lists(sig)
    assert sig.violated_invariants
    assert "[Dismissed]" in sig.violated_invariants[0]
