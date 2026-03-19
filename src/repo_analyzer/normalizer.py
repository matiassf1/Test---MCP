from __future__ import annotations

from collections import defaultdict

from src.repo_analyzer.models import RepoBehaviorCluster, Signal


def cluster_key(s: Signal) -> tuple[str, str]:
    return (s.pattern_kind, s.semantic_intent or s.subtype or "unknown")


def normalize_signals(signals: list[Signal], min_confidence: float = 0.0) -> list[Signal]:
    """Drop low-confidence noise; identical snippet+file+kind deduped by merging frequency."""
    filtered = [s for s in signals if s.confidence >= min_confidence]
    buckets: dict[tuple[str, str, str, str], Signal] = {}
    for s in filtered:
        key = (s.pattern_kind, s.source_file, s.snippet[:120], s.semantic_intent)
        if key not in buckets:
            buckets[key] = s.model_copy()
        else:
            buckets[key].frequency += 1
            buckets[key].confidence = max(buckets[key].confidence, s.confidence)
    return list(buckets.values())


def signals_to_clusters(signals: list[Signal], max_sample_files: int = 8) -> list[RepoBehaviorCluster]:
    """Aggregate by (pattern_kind, semantic_intent) for report / JSON summary."""
    by_key: dict[tuple[str, str], list[Signal]] = defaultdict(list)
    for s in signals:
        by_key[cluster_key(s)].append(s)

    clusters: list[RepoBehaviorCluster] = []
    for (pk, intent), group in sorted(by_key.items(), key=lambda x: -len(x[1])):
        files = sorted({g.source_file for g in group if g.source_file})
        occ = sum(g.frequency for g in group)
        conf = max((g.confidence for g in group), default=0.0)
        clusters.append(
            RepoBehaviorCluster(
                pattern_kind=pk,
                semantic_intent=intent,
                occurrences=occ,
                file_count=len(files),
                confidence=round(min(1.0, conf + 0.05 * min(5, len(files) // 3)), 3),
                sample_files=files[:max_sample_files],
            )
        )
    clusters.sort(key=lambda c: (-c.occurrences, c.pattern_kind))
    return clusters
