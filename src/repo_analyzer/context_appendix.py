"""Appendix markdown for domain_context.md — deterministic, no LLM."""

from __future__ import annotations

from collections import defaultdict

from src.repo_analyzer.models import RepoSignalsFile
from src.repo_analyzer.normalizer import signals_to_clusters

_KIND_LABELS: dict[str, str] = {
    "guard_pattern": "Guard / early-exit patterns",
    "feature_flag_behavior": "Feature flag reads",
    "role_pattern": "Role / permission checks",
    "test_behavior": "Test-described behaviors (it/describe/expect)",
    "failure_pattern_candidate": "Invariant-style comments & error paths",
}


def _flag_names_from_signals(doc: RepoSignalsFile) -> list[str]:
    names: set[str] = set()
    for s in doc.signals:
        if s.pattern_kind != "feature_flag_behavior":
            continue
        for t in s.tags:
            if t and t != "flag" and not t.startswith("structure"):
                names.add(t[:120])
    return sorted(names)[:40]


def format_domain_context_appendix(
    doc: RepoSignalsFile,
    *,
    max_clusters_per_kind: int = 14,
    max_flags_list: int = 25,
) -> str:
    """Return markdown block to append after LLM-generated domain_context (section 10)."""
    clusters = signals_to_clusters(doc.signals)
    by_kind: dict[str, list] = defaultdict(list)
    for c in clusters:
        by_kind[c.pattern_kind].append(c)

    lines = [
        "---",
        "",
        "## 10. INFERRED FROM CODE (repo analyzer)",
        "",
        "_Automated structural scan of a **local** checkout. These are **frequency- and shape-based** hints — "
        "not authored invariants. Triage with `domain_context.md` §2–§6 and team judgment._",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Repo path scanned | `{doc.repo_path}` |",
        f"| Generated (signals file) | `{doc.generated_at}` |",
        f"| Files scanned | {doc.files_scanned} |",
        f"| Lines scanned | {doc.lines_scanned} |",
        f"| Deduped signal rows | {len(doc.signals)} |",
        "",
    ]

    flag_names = _flag_names_from_signals(doc)
    if flag_names:
        lines.append("### Flag identifiers seen in code (string literals)")
        lines.append("")
        for fn in flag_names[:max_flags_list]:
            lines.append(f"- `{fn}`")
        lines.append("")

    lines.append("### Pattern groups (by kind)")
    lines.append("")

    kind_order = [
        "guard_pattern",
        "feature_flag_behavior",
        "role_pattern",
        "test_behavior",
        "failure_pattern_candidate",
    ]
    for kind in kind_order:
        group = by_kind.get(kind, [])
        if not group:
            continue
        label = _KIND_LABELS.get(kind, kind)
        lines.append(f"#### {label}")
        lines.append("")
        for c in sorted(group, key=lambda x: -x.occurrences)[:max_clusters_per_kind]:
            samples = ", ".join(f"`{p}`" for p in c.sample_files[:5])
            if len(c.sample_files) > 5:
                samples += ", …"
            suffix = f"; e.g. {samples}" if samples else ""
            lines.append(
                f"- **{c.semantic_intent}** — {c.occurrences} hits in {c.file_count} file(s)"
                f" _(conf ~{c.confidence:.2f})_{suffix}"
            )
        lines.append("")

    # Any other pattern_kind not in kind_order
    for kind, group in sorted(by_kind.items()):
        if kind in kind_order or not group:
            continue
        lines.append(f"#### {kind}")
        lines.append("")
        for c in sorted(group, key=lambda x: -x.occurrences)[:max_clusters_per_kind]:
            lines.append(
                f"- **{c.semantic_intent}** — {c.occurrences} in {c.file_count} file(s)"
            )
        lines.append("")

    lines.append(
        "_Heuristics: line/regex-based (see `src/repo_analyzer/`). Re-scan with "
        "`python -m src.cli scan_repo_signals --path <repo>` after major refactors._"
    )
    return "\n".join(lines)
