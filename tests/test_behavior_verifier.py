"""Behavior Verifier: verified vs not_verified from diff content."""

from __future__ import annotations

from src.behavior_verifier import apply_verifier_to_signals, verify_behavior_change
from src.models import DomainSignal


def test_verified_when_guard_removed() -> None:
    diff = """
--- a/auth.js
+++ b/auth.js
@@ -10,6 +10,5 @@
-  if (!user.isAuthorizedForSignoff()) return;
   doSomething();
"""
    out = verify_behavior_change(diff, "invariant_violation", "signoff invariant")
    assert out == "verified"


def test_not_verified_when_no_guard_change() -> None:
    diff = """
--- a/button.js
+++ b/button.js
@@ -1,3 +1,3 @@
-  label: "Submit",
+  label: "Save",
"""
    out = verify_behavior_change(diff, "invariant_violation", "signoff invariant")
    assert out == "not_verified"


def test_apply_verifier_downgrades_not_verified() -> None:
    sig = DomainSignal(
        type="invariant_violation",
        description="Possible overlap with invariant",
        source="heuristic",
        is_hard=True,
        confidence=0.8,
    )
    diff = """
-  label: "Old",
+  label: "New",
"""
    apply_verifier_to_signals(diff, [sig], downgrade_confidence_factor=0.35)
    assert sig.is_hard is False
    assert sig.confidence < 0.5
