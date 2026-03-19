"""Repo analyzer MVP: guards, flags, normalization, JSON round-trip."""

from __future__ import annotations

import json
from pathlib import Path

from src.repo_analyzer.analyzer import (
    RepoAnalyzer,
    load_repo_signals_file,
    write_repo_signals_json,
)
from src.repo_analyzer.normalizer import normalize_signals, signals_to_clusters


def test_guard_and_flag_extraction(tmp_path: Path) -> None:
    js = tmp_path / "auth.js"
    js.write_text(
        "if (!user) return;\n"
        "if (featureFlag('close_lock')) { doThing(); }\n",
        encoding="utf-8",
    )
    an = RepoAnalyzer()
    sigs = an.analyze_file(Path("auth.js"), js.read_text(encoding="utf-8"))
    kinds = {s.pattern_kind for s in sigs}
    assert "guard_pattern" in kinds
    assert "feature_flag_behavior" in kinds
    assert any("close_lock" in str(s.tags) for s in sigs if s.pattern_kind == "feature_flag_behavior")


def test_analyze_repo_skips_node_modules(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules" / "x.js"
    nm.parent.mkdir(parents=True)
    nm.write_text("if (a) return;\n", encoding="utf-8")
    good = tmp_path / "src" / "y.js"
    good.parent.mkdir(parents=True)
    good.write_text("if (b) throw x;\n", encoding="utf-8")
    an = RepoAnalyzer()
    doc = an.analyze_repo(tmp_path)
    assert doc.files_scanned == 1
    assert all("node_modules" not in s.source_file for s in doc.signals)


def test_normalize_and_clusters() -> None:
    from src.repo_analyzer.models import Signal

    raw = [
        Signal(
            pattern_kind="guard_pattern",
            semantic_intent="deny_on_condition",
            source_file="a.js",
            snippet="if (!u) return",
            confidence=0.7,
        ),
        Signal(
            pattern_kind="guard_pattern",
            semantic_intent="deny_on_condition",
            source_file="a.js",
            snippet="if (!u) return",
            confidence=0.7,
        ),
        Signal(
            pattern_kind="guard_pattern",
            semantic_intent="deny_on_condition",
            source_file="b.js",
            snippet="if (!u) return",
            confidence=0.7,
        ),
    ]
    norm = normalize_signals(raw)
    assert len(norm) == 2
    clusters = signals_to_clusters(norm)
    assert len(clusters) == 1
    assert clusters[0].occurrences >= 2


def test_json_round_trip(tmp_path: Path) -> None:
    an = RepoAnalyzer()
    f = tmp_path / "t.test.ts"
    f.write_text('it("should not allow guest", () => {});\n', encoding="utf-8")
    doc = an.analyze_repo(tmp_path)
    out = tmp_path / "repo_signals.json"
    write_repo_signals_json(doc, out)
    loaded = load_repo_signals_file(out)
    assert loaded is not None
    assert loaded.files_scanned == 1
    assert len(loaded.signals) >= 1
    # valid JSON schema
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert "signals" in data


def test_domain_context_appendix_section_10() -> None:
    from src.repo_analyzer.context_appendix import format_domain_context_appendix
    from src.repo_analyzer.models import RepoSignalsFile, Signal

    doc = RepoSignalsFile(
        repo_path="/tmp/demo",
        files_scanned=2,
        lines_scanned=40,
        signals=[
            Signal(
                pattern_kind="guard_pattern",
                semantic_intent="deny_on_condition",
                source_file="a.js",
                snippet="if (!u) return",
                confidence=0.7,
            ),
        ],
    )
    md = format_domain_context_appendix(doc)
    assert "## 10. INFERRED FROM CODE" in md
    assert "deny_on_condition" in md
    assert "Guard / early-exit" in md


def test_analyze_diff_added_lines_only() -> None:
    diff = """
+++ b/foo.js
@@ -1,1 +1,2 @@
+if (!ok) return;
 const x = 1;
"""
    an = RepoAnalyzer()
    sigs = an.analyze_diff(diff)
    assert any(s.pattern_kind == "guard_pattern" for s in sigs)
