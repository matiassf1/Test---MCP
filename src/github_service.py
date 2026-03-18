from __future__ import annotations

import re
from typing import Optional

from github import Auth, Github
from github.PullRequest import PullRequest
from github.Repository import Repository

from src.config import settings
from src.models import FileChange


class GitHubService:
    """Fetches PR metadata and diff information from GitHub."""

    def __init__(self, token: Optional[str] = None) -> None:
        resolved_token = token or settings.github_token
        if not resolved_token:
            raise ValueError(
                "GitHub token is required. Set GITHUB_TOKEN in your environment or .env file."
            )
        auth = Auth.Token(resolved_token)
        self._client = Github(auth=auth)

    def get_pull_request(self, repo_name: str, pr_number: int) -> PullRequest:
        repo: Repository = self._client.get_repo(repo_name)
        return repo.get_pull(pr_number)

    def get_author(self, pr: PullRequest) -> str:
        return pr.user.login

    def get_title(self, pr: PullRequest) -> str:
        return pr.title

    def get_changed_files(self, pr: PullRequest) -> list[FileChange]:
        """Return FileChange objects for every file touched by the PR."""
        file_changes: list[FileChange] = []
        for f in pr.get_files():
            modified_lines = self._extract_modified_lines(f.patch)
            file_changes.append(
                FileChange(
                    filename=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                    modified_lines=modified_lines,
                    patch=f.patch,
                )
            )
        return file_changes

    def get_merged_prs_since(self, repo_name: str, since_days: int) -> list[PullRequest]:
        """Return merged PRs from the last `since_days` days."""
        from datetime import datetime, timedelta, timezone

        repo: Repository = self._client.get_repo(repo_name)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=since_days)

        prs: list[PullRequest] = []
        for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
            if pr.merged_at is None:
                continue
            if pr.merged_at < cutoff:
                break
            prs.append(pr)
        return prs

    def get_merged_prs_by_author(
        self, repo_name: str, author: str, since_days: int, limit: int = 100
    ) -> list[PullRequest]:
        """Return merged PRs by a specific author in a single repo."""
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        query = (
            f"repo:{repo_name} type:pr is:merged author:{author} merged:>={cutoff_str}"
        )
        issues = self._client.search_issues(query, sort="updated", order="desc")

        repo: Repository = self._client.get_repo(repo_name)
        prs: list[PullRequest] = []
        for issue in issues:
            if len(prs) >= limit:
                break
            try:
                prs.append(repo.get_pull(issue.number))
            except Exception:
                pass
        return prs

    def get_merged_prs_by_author_org(
        self, org: str, author: str, since_days: int, limit: int = 200
    ) -> list[tuple[str, int]]:
        """Return (repo_full_name, pr_number) pairs for all merged PRs by an author
        across every repository in the given organization.

        Returns tuples instead of PullRequest objects because results span multiple
        repos — the caller is responsible for fetching each PR via analyze_pr().
        """
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        query = (
            f"org:{org} type:pr is:merged author:{author} merged:>={cutoff_str}"
        )
        issues = self._client.search_issues(query, sort="updated", order="desc")

        results: list[tuple[str, int]] = []
        for issue in issues:
            if len(results) >= limit:
                break
            try:
                # issue.repository.full_name → "org/repo"
                repo_full_name = issue.repository.full_name
                results.append((repo_full_name, issue.number))
            except Exception:
                pass
        return results

    def get_prs_mentioning_ticket(
        self,
        ticket_key: str,
        repo: str = "",
        org: str = "",
        limit: int = 50,
    ) -> list[tuple[str, int]]:
        """Return (repo_full_name, pr_number) for merged PRs that mention *ticket_key*.

        Searches PR titles, bodies, and branch names via the GitHub Search API.
        Pass either ``repo`` (single repo) or ``org`` (entire org).
        """
        if not repo and not org:
            return []
        scope = f"repo:{repo}" if repo else f"org:{org}"
        # Quote ticket key so GitHub finds exact mention in title/body (e.g. CLOSE-13348)
        query = f'{scope} type:pr is:merged "{ticket_key}"'
        issues = self._client.search_issues(query, sort="updated", order="desc")
        results: list[tuple[str, int]] = []
        for issue in issues:
            if len(results) >= limit:
                break
            try:
                results.append((issue.repository.full_name, issue.number))
            except Exception:
                pass
        return results

    def fetch_repository_docs_context(self, repo_name: str, max_chars: int = 10000) -> str:
        """Pull README, CONTRIBUTING, and top-level ``docs/*.md`` from default branch.

        Used to ground workflow analysis in repo-native documentation. Returns empty
        string on total failure.
        """
        from github import GithubException

        try:
            repo = self._client.get_repo(repo_name)
            ref = repo.default_branch
        except Exception:
            return ""

        parts: list[str] = []
        used = 0

        def _append(title: str, body: str) -> None:
            nonlocal used
            if used >= max_chars or not body.strip():
                return
            chunk = f"### {title}\n{body.strip()}"
            room = max_chars - used - 20
            if len(chunk) > room:
                chunk = chunk[:room] + "\n…[truncated]"
            parts.append(chunk)
            used += len(chunk)

        for path in ("README.md", "README", "CONTRIBUTING.md", "docs/README.md"):
            try:
                c = repo.get_contents(path, ref=ref)
                if getattr(c, "type", "") == "file" and getattr(c, "decoded_content", None):
                    _append(path, c.decoded_content.decode("utf-8", errors="replace"))
            except GithubException:
                continue

        try:
            entries = repo.get_contents("docs", ref=ref)
            if isinstance(entries, list):
                for ent in sorted(entries, key=lambda x: x.path)[:15]:
                    if not ent.path.endswith(".md") or ent.type != "file":
                        continue
                    try:
                        fc = repo.get_contents(ent.path, ref=ref)
                        if fc.decoded_content:
                            _append(ent.path, fc.decoded_content.decode("utf-8", errors="replace"))
                    except GithubException:
                        continue
        except GithubException:
            pass

        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_modified_lines(self, patch: Optional[str]) -> list[int]:
        """Parse a unified diff patch and return the new-file line numbers that
        were added or changed (lines starting with '+', excluding the header)."""
        if not patch:
            return []

        modified: list[int] = []
        current_line = 0

        for line in patch.splitlines():
            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if hunk_match:
                current_line = int(hunk_match.group(1)) - 1
                continue

            if line.startswith("+") and not line.startswith("+++"):
                current_line += 1
                modified.append(current_line)
            elif line.startswith("-") and not line.startswith("---"):
                # Deleted lines don't advance new-file line counter
                pass
            else:
                # Context line
                current_line += 1

        return modified
