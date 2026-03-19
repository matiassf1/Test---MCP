from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from github.PullRequest import PullRequest
from github.Repository import Repository

from src.models import FileChange


# ---------------------------------------------------------------------------
# Low-level SQLite cache
# ---------------------------------------------------------------------------

_CREATE_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    expires_at  REAL NOT NULL
);
"""


class _DiskCache:
    """Simple SQLite-backed key/value cache with TTL expiry.

    Uses only stdlib so no extra dependencies are needed.
    """

    def __init__(self, db_path: str = ".cache/github.db", ttl_seconds: int = 3600) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(exist_ok=True)
        self._ttl = ttl_seconds
        self._init()

    def get(self, key: str) -> Optional[Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        value_json, expires_at = row
        if time.time() > expires_at:
            self.delete(key)
            return None
        try:
            return json.loads(value_json)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        expires_at = time.time() + self._ttl
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, default=str), expires_at),
            )

    def delete(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))

    def purge_expired(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_CACHE_TABLE)
        self.purge_expired()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)


# ---------------------------------------------------------------------------
# Cached GitHub service wrapper
# ---------------------------------------------------------------------------

class CachedGitHubService:
    """Wraps ``GitHubService`` and caches expensive API calls transparently.

    Results are cached using a SQLite-backed disk cache (no extra dependencies).
    Cache keys are scoped to repo + PR number so multi-repo usage never collides.

    To disable caching, pass ``enabled=False`` — in that case every call falls
    through to the underlying service directly.
    """

    def __init__(
        self,
        github_service,  # GitHubService — avoid circular import by using duck typing
        cache_dir: str = ".cache",
        ttl_seconds: int = 3600,
        enabled: bool = True,
    ) -> None:
        self._svc = github_service
        self._enabled = enabled
        self._cache = _DiskCache(
            db_path=f"{cache_dir}/github.db", ttl_seconds=ttl_seconds
        ) if enabled else None

    # ------------------------------------------------------------------
    # Passthrough methods (same interface as GitHubService)
    # ------------------------------------------------------------------

    def get_repository(self, repo_name: str) -> Repository:
        return self._svc.get_repository(repo_name)

    def get_pull_request(self, repo_name: str, pr_number: int) -> PullRequest:
        """Return PR object — not cached (PyGithub objects are not serialisable)."""
        return self._svc.get_pull_request(repo_name, pr_number)

    def get_author(self, pr: PullRequest) -> str:
        return self._svc.get_author(pr)

    def get_title(self, pr: PullRequest) -> str:
        return self._svc.get_title(pr)

    def get_changed_files(self, pr: PullRequest) -> list[FileChange]:
        """Return changed files, served from cache when available."""
        key = f"files:{pr.base.repo.full_name}:{pr.number}"
        cached = self._get_cached(key)
        if cached is not None:
            try:
                return [FileChange.model_validate(fc) for fc in cached]
            except Exception:
                pass

        result = self._svc.get_changed_files(pr)
        self._set_cached(key, [fc.model_dump(mode="json") for fc in result])
        return result

    def get_merged_prs_since(self, repo_name: str, since_days: int) -> list[PullRequest]:
        """Fetch merged PRs — results are cached with a shorter TTL (30 min)."""
        key = f"merged_prs:{repo_name}:{since_days}"
        # We cannot cache PyGithub PullRequest objects directly, so only the
        # numbers are cached; the full objects are re-fetched individually.
        cached_numbers = self._get_cached(key)
        if cached_numbers is not None:
            prs = []
            for num in cached_numbers:
                try:
                    prs.append(self._svc.get_pull_request(repo_name, num))
                except Exception:
                    pass
            return prs

        prs = self._svc.get_merged_prs_since(repo_name, since_days)
        self._set_cached(key, [pr.number for pr in prs])
        return prs

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_cached(self, key: str) -> Optional[Any]:
        if self._cache is None:
            return None
        return self._cache.get(key)

    def _set_cached(self, key: str, value: Any) -> None:
        if self._cache is not None:
            self._cache.set(key, value)
