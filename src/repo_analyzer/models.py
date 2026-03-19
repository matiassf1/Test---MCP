from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """Single inferred pattern occurrence (line-level MVP)."""

    pattern_kind: str  # guard_pattern, feature_flag_behavior, role_pattern, test_behavior, ...
    subtype: Optional[str] = None
    semantic_intent: str = ""
    source_file: str = ""
    line: Optional[int] = None
    snippet: str = ""
    confidence: float = 0.5
    frequency: int = 1
    tags: list[str] = Field(default_factory=list)


class RepoSignalsFile(BaseModel):
    """Root schema written to repo_signals.json (or artifacts/repo_signals.json)."""

    schema_version: str = "1.0"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    repo_path: str = ""
    files_scanned: int = 0
    lines_scanned: int = 0
    signals: list[Signal] = Field(default_factory=list)


class RepoBehaviorCluster(BaseModel):
    """Aggregated cluster for reports (post-normalization)."""

    pattern_kind: str
    semantic_intent: str
    occurrences: int
    file_count: int
    confidence: float
    sample_files: list[str] = Field(default_factory=list)


class RepoBehaviorSnapshot(BaseModel):
    """Attached to PRMetrics for the experimental report section."""

    schema_version: str = "1.0"
    generated_at: str = ""
    source_json: Optional[str] = None
    clusters: list[RepoBehaviorCluster] = Field(default_factory=list)
    files_scanned: int = 0
    lines_scanned: int = 0
    raw_signals_count: int = 0
