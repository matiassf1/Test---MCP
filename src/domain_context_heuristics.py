"""Domain signals from domain_context.md only (no product-specific hardcoding)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.models import (
    DomainRiskSignals,
    DomainSignal,
    HeuristicLLMContradiction,
)

if TYPE_CHECKING:
    from src.models import FileChange

from src.file_classification import is_generated, is_test_file

_RE_INV = re.compile(
    r"^##\s*(?:2[\.\)]?\s*)?(?:Domain\s*)?Invariants",
    re.I | re.M,
)
_RE_CROSS = re.compile(
    r"^##\s*(?:5[\.\)]?\s*)?(?:Cross[- ]module|Cross module)",
    re.I | re.M,
)
_RE_FAIL = re.compile(
    r"^##\s*(?:6[\.\)]?\s*)?(?:Known\s*)?(?:Failure\s*)?Patterns",
    re.I | re.M,
)
_RE_ROLE = re.compile(
    r"^##\s*(?:3[\.\)]?\s*)?(?:Role\s*)?Model",
    re.I | re.M,
)
_RE_NEXT_SEC = re.compile(r"^##\s+", re.M)
# Generic diff signals when domain_context is absent (soft only)
_FLAG_LINE = re.compile(
    r"featureFlag|useFeatureFlag|isEnabled\s*\(",
    re.I,
)


def _extract_until_next_header(md: str, start_match: re.Match) -> str:
    start = start_match.end()
    rest = md[start:]
    m = _RE_NEXT_SEC.search(rest, pos=1)
    end = start + m.start() if m else len(md)
    return md[start:end]


def _bullets(text: str, max_items: int = 40) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(("-", "*", "•")) or re.match(r"^\d+[\.)]\s", s):
            out.append(re.sub(r"^[-*•\d.)]+\s*", "", s).strip())
        elif len(s) > 20 and s[0].isupper() and out:
            out[-1] = out[-1] + " " + s
    return out[:max_items]


def _word_hits(line: str, haystack: str, min_words: int = 2) -> bool:
    words = re.findall(r"[a-zA-Z]{4,}", line.lower())
    stop = frozenset({
        "that", "this", "with", "from", "must", "when", "each", "same", "only",
        "have", "been", "will", "were", "they", "than", "into", "such", "what",
        "does", "doesn", "other", "some", "many", "most", "very",
    })
    words = [w for w in words if w not in stop]
    if len(words) < 2:
        return False
    h = haystack.lower()
    hit = sum(1 for w in words if w in h)
    return hit >= min(min_words, len(words))


def _evidence_snippet(haystack: str, keywords: list[str], max_len: int = 120) -> list[str]:
    h = haystack.lower()
    for kw in keywords[:5]:
        if len(kw) < 4:
            continue
        i = h.find(kw.lower())
        if i >= 0:
            lo = max(0, i - 40)
            return [haystack[lo : lo + max_len].replace("\n", " ").strip()]
    return []


def _role_lexicon(role_body: str) -> set[str]:
    """Distinctive tokens from §3 bullets (domain-agnostic)."""
    words: set[str] = set()
    for line in role_body.splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        body = re.sub(r"^[-*•\d.)]+\s*", "", s)
        body = re.sub(r"\*+", "", body)
        chunk = re.split(r"[\(:]", body, 1)[0].strip()
        for w in re.findall(r"\b[a-z]{5,}\b", chunk.lower()):
            if w not in frozenset({"cannot", "special", "behavior", "subject", "perform", "manage"}):
                words.add(w)
    return words


def _dedupe_signals(signals: list[DomainSignal], n: int = 24) -> list[DomainSignal]:
    seen: set[str] = set()
    out: list[DomainSignal] = []
    for s in signals:
        k = f"{s.type}:{s.description[:100]}"
        if k not in seen:
            seen.add(k)
            out.append(s)
        if len(out) >= n:
            break
    return out


def sync_legacy_domain_lists(sig: DomainRiskSignals) -> None:
    """Mirror structured signals into legacy string lists for reports / JSON consumers."""
    sig.violated_invariants = []
    sig.triggered_failure_patterns = []
    sig.cross_module_concerns = []
    sig.missing_role_coverage = []
    sig.early_warnings = []
    for s in sig.signals:
        vs = getattr(s, "validation_status", "unvalidated")
        if s.source == "llm":
            tag = "[LLM] "
        elif vs == "dismissed":
            tag = "[Dismissed] "
        elif s.is_hard and s.source == "heuristic":
            tag = "[Hard] "
        elif vs == "candidate":
            tag = "[Candidate] "
        elif vs == "confirmed":
            tag = "[Confirmed] "
        elif vs == "uncertain":
            tag = "[Uncertain] "
        else:
            tag = ""
        line = f"{tag}{s.description}"
        if s.evidence:
            ev = ", ".join(s.evidence[:2])
            if len(ev) < 180:
                line += f" _({ev})_"
        if s.type == "invariant_violation":
            sig.violated_invariants.append(line)
        elif s.type == "failure_pattern":
            sig.triggered_failure_patterns.append(line)
        elif s.type == "cross_module_concern":
            sig.cross_module_concerns.append(line)
        elif s.type == "missing_role":
            sig.missing_role_coverage.append(line)
        elif s.type == "early_warning":
            sig.early_warnings.append(line)


def append_porting_signals(sig: DomainRiskSignals, copy_flags: list[dict]) -> None:
    """Near-duplicate file pairs — soft cross-module hint (not domain-specific)."""
    for cf in copy_flags[:6]:
        src_f = cf.get("source_file", "") or ""
        tgt_f = cf.get("target_file", "") or ""
        if not src_f or not tgt_f:
            continue
        sig.signals.append(
            DomainSignal(
                type="cross_module_concern",
                description=(
                    f"Similar blocks `{src_f.split('/')[-1]}` ↔ `{tgt_f.split('/')[-1]}` — verify domain guards."
                ),
                evidence=[src_f, tgt_f],
                confidence=0.65,
                source="heuristic",
                is_hard=False,
            )
        )
    sig.signals = _dedupe_signals(sig.signals, 28)
    sync_legacy_domain_lists(sig)


def run_domain_heuristics(
    domain_context: str,
    prod_diff: str,
    file_changes: list,
    test_diff: str,
) -> DomainRiskSignals:
    """Emit DomainSignals from domain_context §2/§3/§5/§6; soft fallbacks when MD missing."""
    sig = DomainRiskSignals()
    paths = {
        fc.filename.replace("\\", "/")
        for fc in file_changes
        if not is_test_file(fc.filename) and not is_generated(fc.filename)
    }
    path_blob = " ".join(paths).lower()

    if not domain_context or not domain_context.strip():
        sig.signals.append(
            DomainSignal(
                type="early_warning",
                description="No `domain_context.md` loaded — only generic diff heuristics apply (soft).",
                source="heuristic",
                is_hard=False,
                confidence=0.5,
            )
        )
        n_flag = len(_FLAG_LINE.findall(prod_diff))
        if n_flag >= 4:
            sig.signals.append(
                DomainSignal(
                    type="early_warning",
                    description=f"Heavy feature-flag usage in diff (~{n_flag} hits).",
                    source="heuristic",
                    is_hard=False,
                    confidence=0.55,
                )
            )
        sig.signals = _dedupe_signals(sig.signals, 12)
        sync_legacy_domain_lists(sig)
        return sig

    sig.domain_context_loaded = True
    md = domain_context

    inv_body = _extract_until_next_header(md, m) if (m := _RE_INV.search(md)) else ""
    fail_body = _extract_until_next_header(md, m) if (m := _RE_FAIL.search(md)) else ""
    cross_body = _extract_until_next_header(md, m) if (m := _RE_CROSS.search(md)) else ""
    role_body = _extract_until_next_header(md, m) if (m := _RE_ROLE.search(md)) else ""

    inv_lines = _bullets(inv_body)
    for line in inv_lines:
        if len(line) < 25:
            continue
        strong = any(
            x in line.lower()
            for x in ("must not", "must never", "always", "shall not", "never ", "hard constraint")
        )
        if strong and _word_hits(line, prod_diff, min_words=3):
            kws = re.findall(r"[a-z]{5,}", line.lower())[:8]
            sig.signals.append(
                DomainSignal(
                    type="invariant_violation",
                    description=f"Possible overlap with invariant: {line[:200]}",
                    evidence=_evidence_snippet(prod_diff, kws),
                    confidence=min(1.0, 0.55 + 0.05 * len([w for w in kws if w in prod_diff.lower()])),
                    source="heuristic",
                    is_hard=True,
                )
            )

    fail_lines = _bullets(fail_body)
    for line in fail_lines:
        if len(line) < 22:
            continue
        if _word_hits(line, prod_diff, min_words=2):
            kws = re.findall(r"[a-z]{5,}", line.lower())[:8]
            sig.signals.append(
                DomainSignal(
                    type="failure_pattern",
                    description=f"Diff overlaps known pattern: {line[:200]}",
                    evidence=_evidence_snippet(prod_diff, kws),
                    confidence=0.75,
                    source="heuristic",
                    is_hard=True,
                )
            )

    cross_lines = _bullets(cross_body)
    for line in cross_lines:
        if len(line) < 30:
            continue
        if _word_hits(line, prod_diff, min_words=2) or _word_hits(line, path_blob, min_words=2):
            sig.signals.append(
                DomainSignal(
                    type="cross_module_concern",
                    description=f"Cross-module rule may apply: {line[:220]}",
                    evidence=_evidence_snippet(prod_diff + "\n" + path_blob, re.findall(r"[a-z]{5,}", line.lower())[:6]),
                    confidence=0.7,
                    source="heuristic",
                    is_hard=True,
                )
            )

    if len(paths) >= 1 and cross_body and ("parity" in cross_body.lower() or "align" in cross_body.lower()):
        prefixes = set()
        for p in paths:
            parts = p.split("/")
            if len(parts) >= 2:
                prefixes.add(f"{parts[0]}/{parts[1]}".lower())
        if len(prefixes) == 1:
            sig.signals.append(
                DomainSignal(
                    type="cross_module_concern",
                    description="Single path prefix in PR; domain doc mentions parity/alignment across modules — confirm siblings.",
                    evidence=list(prefixes)[:3],
                    confidence=0.6,
                    source="heuristic",
                    is_hard=True,
                )
            )

    lex = _role_lexicon(role_body)
    prod_l = prod_diff.lower()
    test_l = test_diff.lower()
    for w in sorted(lex):
        if len(w) < 5:
            continue
        if re.search(rf"\b{re.escape(w)}\b", prod_l) and not re.search(rf"\b{re.escape(w)}\b", test_l):
            sig.signals.append(
                DomainSignal(
                    type="missing_role",
                    description=f"Role/actor token `{w}` appears in prod diff but not in test diff (see §3 Role Model).",
                    evidence=[w],
                    confidence=0.65,
                    source="heuristic",
                    is_hard=True,
                )
            )

    n_flag = len(_FLAG_LINE.findall(prod_diff))
    if n_flag >= 4:
        sig.signals.append(
            DomainSignal(
                type="early_warning",
                description=f"Heavy feature-flag usage (~{n_flag}) — cross-check §4 in domain_context.",
                source="heuristic",
                is_hard=False,
                confidence=0.5,
            )
        )

    non_mr = [s for s in sig.signals if s.type != "missing_role"]
    mr = [s for s in sig.signals if s.type == "missing_role"][:8]
    sig.signals = non_mr + mr

    sig.signals = _dedupe_signals(sig.signals, 24)

    # Optional: verify invariant/failure signals against diff; downgrade if no behavior change evidence
    try:
        from src.config import settings as _settings
        if getattr(_settings, "domain_verify_behavior_before_hard", False):
            from src.behavior_verifier import apply_verifier_to_signals
            apply_verifier_to_signals(prod_diff, sig.signals)
    except Exception:
        pass

    sync_legacy_domain_lists(sig)
    return sig


def _text_overlap(a: str, b: str, n: int = 2) -> bool:
    wa = set(re.findall(r"[a-z]{4,}", a.lower()))
    wb = set(re.findall(r"[a-z]{4,}", b.lower()))
    return len(wa & wb) >= n


def merge_llm_domain_struct(workflow_markdown: str, sig: DomainRiskSignals) -> None:
    """Merge LLM DOMAIN_STRUCT: never remove hard heuristics; record contradictions."""
    if not workflow_markdown:
        return
    m = re.search(
        r"---DOMAIN_STRUCT---\s*(.*?)---END_DOMAIN_STRUCT---",
        workflow_markdown,
        re.DOTALL | re.I,
    )
    if not m:
        return
    block = m.group(1)

    def _section(name: str) -> list[str]:
        pat = re.compile(rf"^{name}:\s*$", re.I | re.M)
        mm = pat.search(block)
        if not mm:
            return []
        tail = block[mm.end() :]
        nxt = re.search(r"^[A-Z_]+:\s*$", tail, re.M)
        chunk = tail[: nxt.start()] if nxt else tail
        items = []
        for line in chunk.splitlines():
            s = line.strip()
            if s.startswith("-"):
                body = s[1:].strip()
                if body.upper() in ("NONE", "N/A", ""):
                    continue
                if "no violation" in body.lower() and len(body) < 80:
                    continue
                items.append(body)
        return items[:18]

    hard_inv = [s for s in sig.signals if s.type == "invariant_violation" and s.is_hard and s.source == "heuristic"]
    llm_inv = _section("VIOLATED_INVARIANTS")
    llm_meaningful = [x for x in llm_inv if x.upper() != "NONE" and "none —" not in x.lower()[:20]]

    if hard_inv and not llm_meaningful:
        for h in hard_inv[:5]:
            sig.heuristic_llm_contradictions.append(
                HeuristicLLMContradiction(
                    heuristic_description=h.description,
                    heuristic_signal_type="invariant_violation",
                    llm_claim="DOMAIN_STRUCT listed no invariant violations (NONE or empty).",
                )
            )

    existing_hard_desc = {s.description[:120] for s in sig.signals if s.is_hard}
    for item in llm_meaningful:
        if any(_text_overlap(item, h.description) for h in hard_inv):
            continue
        sig.signals.append(
            DomainSignal(
                type="invariant_violation",
                description=item[:500],
                source="llm",
                is_hard=False,
                confidence=0.45,
            )
        )
    for item in _section("TRIGGERED_FAILURE_PATTERNS"):
        if any(_text_overlap(item, s.description) for s in sig.signals if s.type == "failure_pattern" and s.is_hard):
            continue
        sig.signals.append(
            DomainSignal(
                type="failure_pattern",
                description=item[:500],
                source="llm",
                is_hard=False,
                confidence=0.45,
            )
        )
    for item in _section("CROSS_MODULE"):
        sig.signals.append(
            DomainSignal(
                type="cross_module_concern",
                description=item[:500],
                source="llm",
                is_hard=False,
                confidence=0.45,
            )
        )
    for item in _section("MISSING_ROLES"):
        sig.signals.append(
            DomainSignal(
                type="missing_role",
                description=item[:500],
                source="llm",
                is_hard=False,
                confidence=0.45,
            )
        )

    for h in hard_inv:
        for li in llm_meaningful:
            if "no " in li.lower() and "violation" in li.lower() and _text_overlap(li, h.description, n=3):
                sig.heuristic_llm_contradictions.append(
                    HeuristicLLMContradiction(
                        heuristic_description=h.description,
                        llm_claim=li[:400],
                    )
                )

    _seen_c: set[tuple[str, str]] = set()
    _cd: list[HeuristicLLMContradiction] = []
    for c in sig.heuristic_llm_contradictions:
        k = (c.heuristic_description[:100], c.llm_claim[:100])
        if k not in _seen_c:
            _seen_c.add(k)
            _cd.append(c)
    sig.heuristic_llm_contradictions = _cd[:12]

    sig.signals = _dedupe_signals(sig.signals, 32)
    sync_legacy_domain_lists(sig)
