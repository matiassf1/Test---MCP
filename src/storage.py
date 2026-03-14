from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.models import PRMetrics


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class StorageBackend(ABC):
    """Protocol for persisting and loading PR metrics.

    Implementations must be interchangeable — callers only depend on this
    interface, making it straightforward to add new backends (e.g. PostgreSQL,
    an Atlassian MCP store) without touching the rest of the codebase.
    """

    @abstractmethod
    def save(self, metrics: PRMetrics) -> None:
        """Persist a PRMetrics record, overwriting any existing one."""

    @abstractmethod
    def load(self, pr_number: int, repo: Optional[str] = None) -> Optional[PRMetrics]:
        """Return metrics for a given PR number (and optionally repo), or None.

        When ``repo`` is provided, the lookup uses the composite key
        ``(repo, pr_number)`` for accuracy in multi-repo scenarios.
        When omitted, falls back to pr_number-only (legacy behaviour).
        """

    @abstractmethod
    def load_all(self) -> list[PRMetrics]:
        """Return all persisted PR metrics records."""


# ---------------------------------------------------------------------------
# JSON backend (original behaviour, default)
# ---------------------------------------------------------------------------

class JSONStorage(StorageBackend):
    """Stores each PR as a separate JSON file under ``directory/``.

    File naming uses a composite key ``{repo_slug}__pr_{number}.json`` so
    PRs from different repos never collide.  Legacy files (``pr_N.json``)
    are still found by ``load`` and ``load_all`` for backward compatibility.
    """

    def __init__(self, directory: str = "metrics") -> None:
        self._dir = Path(directory)
        self._dir.mkdir(exist_ok=True)

    @staticmethod
    def _repo_slug(repo: str) -> str:
        """Turn 'org/repo' into 'org__repo' (safe for filenames)."""
        return repo.replace("/", "__")

    def _composite_path(self, repo: str, pr_number: int) -> Path:
        return self._dir / f"{self._repo_slug(repo)}__pr_{pr_number}.json"

    def _legacy_path(self, pr_number: int) -> Path:
        return self._dir / f"pr_{pr_number}.json"

    def save(self, metrics: PRMetrics) -> None:
        path = self._composite_path(metrics.repo, metrics.pr_number)
        path.write_text(metrics.model_dump_json(indent=2), encoding="utf-8")
        # Remove legacy file if it exists to avoid duplicates
        legacy = self._legacy_path(metrics.pr_number)
        if legacy.exists() and legacy != path:
            try:
                legacy.unlink()
            except OSError:
                pass

    def load(self, pr_number: int, repo: Optional[str] = None) -> Optional[PRMetrics]:
        # Try composite path first when repo is known
        if repo:
            path = self._composite_path(repo, pr_number)
            if path.exists():
                return self._read(path)
        # Fallback: legacy path
        legacy = self._legacy_path(pr_number)
        if legacy.exists():
            return self._read(legacy)
        # Last resort: scan for any file ending with __pr_{N}.json
        for p in self._dir.glob(f"*__pr_{pr_number}.json"):
            result = self._read(p)
            if result:
                return result
        return None

    def load_all(self) -> list[PRMetrics]:
        records: list[PRMetrics] = []
        seen: set[tuple[str, int]] = set()
        for p in sorted(self._dir.glob("*.json")):
            m = self._read(p)
            if m:
                key = (m.repo, m.pr_number)
                if key not in seen:
                    seen.add(key)
                    records.append(m)
        return records

    def path_for(self, pr_number: int, repo: Optional[str] = None) -> Path:
        """Return the file path for a PR (used by MetricsEngine for display)."""
        if repo:
            return self._composite_path(repo, pr_number)
        return self._legacy_path(pr_number)

    def _read(self, path: Path) -> Optional[PRMetrics]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PRMetrics.model_validate(data)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pr_metrics (
    pr_number                INTEGER NOT NULL,
    repo                     TEXT    NOT NULL,
    author                   TEXT    NOT NULL,
    title                    TEXT    NOT NULL,
    pr_date                  TEXT,
    jira_ticket              TEXT,
    jira_issue_type          TEXT,
    jira_status              TEXT,
    jira_priority            TEXT,
    files_changed            INTEGER NOT NULL DEFAULT 0,
    lines_modified           INTEGER NOT NULL DEFAULT 0,
    lines_covered            INTEGER NOT NULL DEFAULT 0,
    change_coverage          REAL    NOT NULL DEFAULT 0,
    production_lines_added   INTEGER NOT NULL DEFAULT 0,
    test_lines_added         INTEGER NOT NULL DEFAULT 0,
    overall_coverage         REAL,
    test_code_ratio          REAL    NOT NULL DEFAULT 0,
    testing_quality_score    REAL    NOT NULL DEFAULT 0,
    tests_added              INTEGER NOT NULL DEFAULT 0,
    test_types_unit          INTEGER NOT NULL DEFAULT 0,
    test_types_integration   INTEGER NOT NULL DEFAULT 0,
    test_types_e2e           INTEGER NOT NULL DEFAULT 0,
    test_types_unknown       INTEGER NOT NULL DEFAULT 0,
    raw_json                 TEXT    NOT NULL,
    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (repo, pr_number)
);
"""

# Additive migrations — applied on startup, silently ignored if column exists
_MIGRATIONS = [
    "ALTER TABLE pr_metrics ADD COLUMN testing_quality_score REAL NOT NULL DEFAULT 0",
]

# If old table has INTEGER PRIMARY KEY on pr_number only, we recreate with composite PK.
# Handled in _init_db via a check + copy approach.


class SQLiteStorage(StorageBackend):
    """Stores PR metrics in a SQLite database.

    Each record includes indexed scalar columns for efficient querying AND
    a ``raw_json`` column containing the full serialized ``PRMetrics`` so
    the complete object graph can always be restored without schema migrations.

    New columns are added via safe ``ALTER TABLE … ADD COLUMN`` migrations that
    are silently ignored when the column already exists.
    """

    def __init__(self, db_path: str = "metrics/pr_metrics.db") -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(exist_ok=True)
        self._init_db()

    def save(self, metrics: PRMetrics) -> None:
        row = self._to_row(metrics)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pr_metrics (
                    pr_number, repo, author, title, pr_date,
                    jira_ticket, jira_issue_type, jira_status, jira_priority,
                    files_changed, lines_modified, lines_covered, change_coverage,
                    production_lines_added, test_lines_added,
                    overall_coverage, test_code_ratio, testing_quality_score,
                    tests_added,
                    test_types_unit, test_types_integration, test_types_e2e, test_types_unknown,
                    raw_json, created_at
                ) VALUES (
                    :pr_number, :repo, :author, :title, :pr_date,
                    :jira_ticket, :jira_issue_type, :jira_status, :jira_priority,
                    :files_changed, :lines_modified, :lines_covered, :change_coverage,
                    :production_lines_added, :test_lines_added,
                    :overall_coverage, :test_code_ratio, :testing_quality_score,
                    :tests_added,
                    :test_types_unit, :test_types_integration, :test_types_e2e, :test_types_unknown,
                    :raw_json, :created_at
                )
                """,
                row,
            )

    def load(self, pr_number: int, repo: Optional[str] = None) -> Optional[PRMetrics]:
        with self._connect() as conn:
            if repo:
                row = conn.execute(
                    "SELECT raw_json FROM pr_metrics WHERE repo = ? AND pr_number = ?",
                    (repo, pr_number),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT raw_json FROM pr_metrics WHERE pr_number = ?", (pr_number,)
                ).fetchone()
        if row is None:
            return None
        try:
            return PRMetrics.model_validate_json(row[0])
        except Exception:
            return None

    def load_all(self) -> list[PRMetrics]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT raw_json FROM pr_metrics ORDER BY pr_number"
            ).fetchall()
        records: list[PRMetrics] = []
        for (raw,) in rows:
            try:
                records.append(PRMetrics.model_validate_json(raw))
            except Exception:
                continue
        return records

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            for migration in _MIGRATIONS:
                try:
                    conn.execute(migration)
                except sqlite3.OperationalError:
                    pass  # column already exists — safe to ignore
            self._migrate_to_composite_pk(conn)

    def _migrate_to_composite_pk(self, conn: sqlite3.Connection) -> None:
        """If the old schema used INTEGER PRIMARY KEY on pr_number, migrate to (repo, pr_number)."""
        try:
            info = conn.execute("PRAGMA table_info(pr_metrics)").fetchall()
            pk_col = next((r for r in info if r["name"] == "pr_number"), None)
            if pk_col and pk_col["pk"] == 1:
                # Old schema (pr_number is sole PK). Rebuild with composite PK.
                conn.execute("ALTER TABLE pr_metrics RENAME TO _pr_metrics_old")
                conn.execute(_CREATE_TABLE)
                cols = ", ".join(r["name"] for r in info if r["name"] in {
                    "pr_number", "repo", "author", "title", "pr_date",
                    "jira_ticket", "jira_issue_type", "jira_status", "jira_priority",
                    "files_changed", "lines_modified", "lines_covered", "change_coverage",
                    "production_lines_added", "test_lines_added",
                    "overall_coverage", "test_code_ratio", "testing_quality_score",
                    "tests_added", "test_types_unit", "test_types_integration",
                    "test_types_e2e", "test_types_unknown", "raw_json", "created_at",
                })
                conn.execute(f"INSERT OR IGNORE INTO pr_metrics ({cols}) SELECT {cols} FROM _pr_metrics_old")
                conn.execute("DROP TABLE _pr_metrics_old")
        except Exception:
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _to_row(self, m: PRMetrics) -> dict:
        issue = m.jira_issue
        return {
            "pr_number": m.pr_number,
            "repo": m.repo,
            "author": m.author,
            "title": m.title,
            "pr_date": m.pr_date.isoformat() if m.pr_date else None,
            "jira_ticket": m.jira_ticket,
            "jira_issue_type": issue.issue_type if issue else None,
            "jira_status": issue.status if issue else None,
            "jira_priority": issue.priority if issue else None,
            "files_changed": m.files_changed,
            "lines_modified": m.lines_modified,
            "lines_covered": m.lines_covered,
            "change_coverage": m.change_coverage,
            "production_lines_added": m.production_lines_added,
            "test_lines_added": m.test_lines_added,
            "overall_coverage": m.overall_coverage,
            "test_code_ratio": m.test_code_ratio,
            "testing_quality_score": m.testing_quality_score,
            "tests_added": m.tests_added,
            "test_types_unit": m.test_types.unit,
            "test_types_integration": m.test_types.integration,
            "test_types_e2e": m.test_types.e2e,
            "test_types_unknown": m.test_types.unknown,
            "raw_json": m.model_dump_json(),
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_storage(backend: str = "json") -> StorageBackend:
    """Return a storage backend by name.  Accepts ``'json'`` or ``'sqlite'``."""
    if backend == "sqlite":
        return SQLiteStorage()
    return JSONStorage()
