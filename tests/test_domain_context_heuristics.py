from __future__ import annotations

from src.domain_context_heuristics import (
    merge_llm_domain_struct,
    run_domain_heuristics,
    sync_legacy_domain_lists,
)
from src.models import DomainRiskSignals, DomainSignal


def test_merge_llm_domain_struct():
    sig = DomainRiskSignals(domain_context_loaded=True)
    sig.signals.append(
        DomainSignal(
            type="invariant_violation",
            description="User must not bypass signoff",
            source="heuristic",
            is_hard=True,
        )
    )
    sync_legacy_domain_lists(sig)
    md = """
Some narrative.

---DOMAIN_STRUCT---
VIOLATED_INVARIANTS:
- NONE
TRIGGERED_FAILURE_PATTERNS:
- NONE
CROSS_MODULE:
- NONE
MISSING_ROLES:
- NONE
---END_DOMAIN_STRUCT---
"""
    merge_llm_domain_struct(md, sig)
    assert sig.heuristic_llm_contradictions
    assert any("NONE" in c.llm_claim or "violation" in c.llm_claim.lower() for c in sig.heuristic_llm_contradictions)


def test_run_heuristics_empty_domain():
    from src.models import FileChange

    fc = FileChange(
        filename="x.js", status="modified", additions=1, deletions=0, patch="+a"
    )
    sig = run_domain_heuristics("", "+code", [fc], "")
    assert not sig.domain_context_loaded
    assert sig.signals
    assert not any(s.is_hard for s in sig.signals)


def test_hard_invariant_from_domain_md():
    from src.models import FileChange

    md = """## 2. DOMAIN INVARIANTS

- Users must never bypass authorization checks in any API path.
"""
    prod = "users must never bypass authorization checks in new path"
    fc = FileChange(
        filename="api/handler.js",
        status="modified",
        additions=2,
        deletions=0,
        patch="+bypass",
    )
    sig = run_domain_heuristics(md, prod, [fc], "")
    assert sig.domain_context_loaded
    assert any(s.is_hard and s.type == "invariant_violation" for s in sig.signals)


def test_merge_adds_soft_llm_without_removing_hard():
    sig = DomainRiskSignals(domain_context_loaded=True)
    sig.signals.append(
        DomainSignal(
            type="invariant_violation",
            description="Hard rule X",
            source="heuristic",
            is_hard=True,
        )
    )
    merge_llm_domain_struct(
        """---DOMAIN_STRUCT---
VIOLATED_INVARIANTS:
- Additional LLM-only concern about tests
TRIGGERED_FAILURE_PATTERNS:
- NONE
CROSS_MODULE:
- NONE
MISSING_ROLES:
- NONE
---END_DOMAIN_STRUCT---""",
        sig,
    )
    hard = [s for s in sig.signals if s.is_hard and s.source == "heuristic"]
    assert len(hard) == 1
    assert any(s.source == "llm" for s in sig.signals)
