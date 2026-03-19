from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.file_classification import is_test_file
from src.repo_analyzer.extractors import (
    extract_failure_signals,
    extract_flag_signals,
    extract_guard_signals,
    extract_role_signals,
    extract_test_behavior_signals,
)
from src.repo_analyzer.models import RepoBehaviorSnapshot, RepoSignalsFile, Signal
from src.repo_analyzer.normalizer import normalize_signals, signals_to_clusters

_SCAN_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py"}
_SKIP_DIR_PARTS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".next",
    "vendor",
    "target",
}


def _should_skip_dir(name: str) -> bool:
    return name in _SKIP_DIR_PARTS or name.startswith(".")


def _iter_source_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if any(_should_skip_dir(part) for part in p.parts):
            continue
        if p.suffix.lower() not in _SCAN_EXTENSIONS:
            continue
        files.append(p)
    return sorted(files)


class RepoAnalyzer:
    """Line-based structural extractors (MVP). Use ``analyze_repo`` for full scan; ``analyze_diff`` for PR-sized text."""

    def analyze_file(self, path: Path, content: str) -> list[Signal]:
        rel = path.as_posix()
        lines = content.splitlines()
        is_test = is_test_file(rel)
        sigs: list[Signal] = []
        sigs.extend(extract_guard_signals(lines, rel))
        sigs.extend(extract_flag_signals(lines, rel))
        sigs.extend(extract_role_signals(lines, rel))
        if is_test:
            sigs.extend(extract_test_behavior_signals(lines, rel))
        sigs.extend(extract_failure_signals(lines, rel, is_test_file=is_test))
        return sigs

    def analyze_repo(
        self,
        repo_path: str | Path,
        *,
        min_confidence: float = 0.0,
    ) -> RepoSignalsFile:
        root = Path(repo_path).resolve()
        all_signals: list[Signal] = []
        files_n = 0
        lines_n = 0
        for fp in _iter_source_files(root):
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files_n += 1
            lines_n += text.count("\n") + (1 if text else 0)
            all_signals.extend(self.analyze_file(fp.relative_to(root), text))

        normalized = normalize_signals(all_signals, min_confidence=min_confidence)
        return RepoSignalsFile(
            repo_path=str(root),
            files_scanned=files_n,
            lines_scanned=lines_n,
            signals=normalized,
        )

    def analyze_diff(self, diff: str, *, virtual_path: str = "pr_diff.txt") -> list[Signal]:
        """Run extractors on added lines only (+ prefix) from a unified diff."""
        added: list[str] = []
        for line in diff.splitlines():
            if line.startswith("+++ ") or line.startswith("--- "):
                continue
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
        text = "\n".join(added)
        return self.analyze_file(Path(virtual_path), text)

    def build_snapshot(
        self,
        doc: RepoSignalsFile,
        *,
        source_json: Optional[str] = None,
        top_clusters: int = 24,
    ) -> RepoBehaviorSnapshot:
        clusters = signals_to_clusters(doc.signals)[:top_clusters]
        return RepoBehaviorSnapshot(
            generated_at=doc.generated_at,
            source_json=source_json,
            clusters=clusters,
            files_scanned=doc.files_scanned,
            lines_scanned=doc.lines_scanned,
            raw_signals_count=len(doc.signals),
        )


def write_repo_signals_json(doc: RepoSignalsFile, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        doc.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return out_path


def load_repo_signals_file(path: Path) -> Optional[RepoSignalsFile]:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return RepoSignalsFile.model_validate(data)
    except Exception:
        return None


def load_or_build_snapshot(
    repo_path: Optional[str],
    *,
    explicit_json: Optional[str] = None,
) -> Optional[RepoBehaviorSnapshot]:
    """Resolve JSON path: explicit setting, else ``<repo_path>/artifacts/repo_signals.json``."""
    candidates: list[Path] = []
    if explicit_json:
        candidates.append(Path(explicit_json).expanduser())
    if repo_path:
        root = Path(repo_path).resolve()
        candidates.append(root / "artifacts" / "repo_signals.json")

    for c in candidates:
        doc = load_repo_signals_file(c)
        if doc is None:
            continue
        return RepoAnalyzer().build_snapshot(doc, source_json=str(c.resolve()))
    return None
