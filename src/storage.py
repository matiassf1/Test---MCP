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
    def load(self, pr_number: int) -> Optional[PRMetrics]:
        """Return metrics for a given PR number, or None if not found."""

    @abstractmethod
    def load_all(self) -> list[PRMetrics]:
        """Return all persisted PR metrics records."""


# ---------------------------------------------------------------------------
# JSON backend (original behaviour, default)
# ---------------------------------------------------------------------------

class JSONStorage(StorageBackend):
    """Stores each PR as a separate JSON file under ``directory/``."""

    def __init__(self, directory: str = "metrics") -> None:
        self._dir = Path(directory)
        self._dir.mkdir(exist_ok=True)

    def save(self, metrics: PRMetrics) -> None:
        path = self._dir / f"pr_{metrics.pr_number}.json"
        path.write_text(metrics.model_dump_json(indent=2), encoding="utf-8")

    def load(self, pr_number: int) -> Optional[PRMetrics]:
        path = self._dir / f"pr_{pr_number}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PRMetrics.model_validate(data)
        except Exception:
            return None

    def load_all(self) -> list[PRMetrics]:
        records: list[PRMetrics] = []
        for p in sorted(self._dir.glob("pr_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                records.append(PRMetrics.model_validate(data))
            except Exception:
                continue
        return records

    def path_for(self, pr_number: int) -> Path:
        """Return the file path for a PR (used by MetricsEngine for display)."""
        return self._dir / f"pr_{pr_number}.json"


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pr_metrics (
    pr_number                INTEGER PRIMARY KEY,
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
    created_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

# Additive migrations — applied on startup, silently ignored if column exists
_MIGRATIONS = [
    "ALTER TABLE pr_metrics ADD COLUMN testing_quality_score REAL NOT NULL DEFAULT 0",
]


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

    def load(self, pr_number: int) -> Optional[PRMetrics]:
        with self._connect() as conn:
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
