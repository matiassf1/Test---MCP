"""Jira invariant extractor — parse ticket descriptions for porting signals and domain constraints."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


_PORTING_PHRASES = [
    "parity", "based on", "ported from", "similar to", "replicate",
    "match behavior", "match behaviour", "same as", "mirror",
]

_PORTING_RE = re.compile(
    r"(?P<phrase>" + "|".join(re.escape(p) for p in _PORTING_PHRASES) + r")",
    re.IGNORECASE,
)

# Sentence splitter (splits on . ! ? followed by space or end)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_CONSTRAINT_RE = re.compile(
    r"\b(?:must|always|never|should\s+not|shall|required|ensure)\b",
    re.IGNORECASE,
)


@dataclass
class PortingSignal:
    phrase: str
    context_sentence: str


@dataclass
class JiraInvariantContext:
    porting_signals: list[PortingSignal] = field(default_factory=list)
    domain_constraints: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.porting_signals and not self.domain_constraints

    def as_text(self) -> str:
        """Render as human-readable text for LLM prompt injection."""
        parts: list[str] = []
        if self.porting_signals:
            parts.append("**Porting signals detected in ticket:**")
            for sig in self.porting_signals:
                parts.append(f'- "{sig.phrase}": {sig.context_sentence}')
        if self.domain_constraints:
            parts.append("**Domain constraints from ticket:**")
            for c in self.domain_constraints:
                parts.append(f"- {c}")
        return "\n".join(parts)


def _sentences(text: str) -> list[str]:
    """Split text into sentences; also treat bullet lines as sentences."""
    sentences: list[str] = []
    for para in text.split("\n"):
        para = para.strip().lstrip("*-•|").strip()
        if not para:
            continue
        for sent in _SENTENCE_RE.split(para):
            s = sent.strip()
            if s:
                sentences.append(s)
    return sentences


class JiraInvariantExtractor:
    """Extract porting signals and domain constraints from Jira ticket descriptions."""

    def extract(self, description: Optional[str]) -> JiraInvariantContext:
        if not description or not description.strip():
            return JiraInvariantContext()

        sents = _sentences(description)
        porting: list[PortingSignal] = []
        constraints: list[str] = []
        seen_porting: set[str] = set()
        seen_constraints: set[str] = set()

        for sent in sents:
            # Porting signals
            for m in _PORTING_RE.finditer(sent):
                phrase = m.group("phrase").lower()
                key = phrase + "|" + sent[:60]
                if key not in seen_porting:
                    seen_porting.add(key)
                    porting.append(PortingSignal(phrase=phrase, context_sentence=sent.strip()))

            # Normative constraints
            if _CONSTRAINT_RE.search(sent):
                norm = sent.strip()
                if norm and norm not in seen_constraints and len(norm) > 10:
                    seen_constraints.add(norm)
                    constraints.append(norm)

        return JiraInvariantContext(porting_signals=porting, domain_constraints=constraints)
