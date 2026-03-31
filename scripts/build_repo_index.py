"""Build a prioritized index of FloQast GitHub repositories.

Queries the configured GitHub org, scores each repo by domain criticality
(commit frequency + contributor count + domain keyword presence), and writes
a ranked YAML to domain_knowledge/repo_priority_index.yaml.

Usage:
    python scripts/build_repo_index.py [--max-repos 50] [--output domain_knowledge/repo_priority_index.yaml]

Re-runs preserve any existing `manual_priority` annotations.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure src/ is on path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.config import settings

logger = logging.getLogger(__name__)

_DOMAIN_KEYWORDS = {"signoff", "locking", "checklist", "authorization", "close"}
_OUTPUT_DEFAULT = Path("domain_knowledge/repo_priority_index.yaml")


def _score_repo(repo, since: datetime) -> tuple[int, list[str], str]:
    """Return (score, domain_areas, rationale) for a GitHub repo object."""
    commit_score = 0
    contributor_score = 0
    keyword_score = 0
    domain_areas: list[str] = []
    rationale_parts: list[str] = []

    # Commit activity (last 90 days) — cap at 5
    try:
        commits = repo.get_commits(since=since)
        count = min(commits.totalCount, 999)
        if count >= 100:
            commit_score = 5
        elif count >= 50:
            commit_score = 4
        elif count >= 20:
            commit_score = 3
        elif count >= 10:
            commit_score = 2
        elif count >= 5:
            commit_score = 1
        rationale_parts.append(f"{count} commits (90d)")
    except Exception:
        rationale_parts.append("commits: n/a")

    # Contributor count — cap at 3
    try:
        contributors = repo.get_contributors()
        contrib_count = min(contributors.totalCount, 999)
        if contrib_count >= 10:
            contributor_score = 3
        elif contrib_count >= 5:
            contributor_score = 2
        elif contrib_count >= 2:
            contributor_score = 1
        rationale_parts.append(f"{contrib_count} contributors")
    except Exception:
        rationale_parts.append("contributors: n/a")

    # Domain keyword match in description + topics — cap at 2
    text = ((repo.description or "") + " " + " ".join(repo.get_topics())).lower()
    for kw in _DOMAIN_KEYWORDS:
        if kw in text:
            domain_areas.append(kw)
    if domain_areas:
        keyword_score = min(len(domain_areas), 2)
        rationale_parts.append(f"keywords: {', '.join(domain_areas)}")

    score = commit_score + contributor_score + keyword_score
    return score, domain_areas, "; ".join(rationale_parts)


def _load_existing(output_path: Path) -> dict[str, dict]:
    """Load existing YAML and return a dict of repo -> entry (preserves manual_priority)."""
    if not output_path.exists():
        return {}
    try:
        with open(output_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        return {entry["repo"]: entry for entry in data if isinstance(entry, dict) and "repo" in entry}
    except Exception:
        return {}


def build_repo_index(max_repos: int = 50, output_path: Path = _OUTPUT_DEFAULT) -> Path:
    """Query the GitHub org, score repos, and write the priority index YAML."""
    from github import GithubException

    from src.github_service import GitHubService

    org_name = settings.floqast_org or "FloQastInc"
    gh = GitHubService()

    if not gh._client:
        raise RuntimeError("GitHub client not available — check GITHUB_TOKEN")

    logger.info("Fetching repos for org: %s (max: %d)", org_name, max_repos)
    since = datetime.now(tz=timezone.utc) - timedelta(days=90)

    try:
        org = gh._client.get_organization(org_name)
        all_repos = list(org.get_repos(type="all", sort="updated"))
    except GithubException as exc:
        raise RuntimeError(f"Failed to list repos for {org_name}: {exc}") from exc

    # Filter archived repos; take top N by updated
    active_repos = [r for r in all_repos if not r.archived][:max_repos]
    logger.info("Scoring %d repos…", len(active_repos))

    existing = _load_existing(output_path)
    entries: list[dict] = []

    for repo in active_repos:
        logger.debug("Scoring %s", repo.full_name)
        try:
            score, domain_areas, rationale = _score_repo(repo, since)
        except Exception as exc:
            logger.warning("Skipping %s — scoring failed: %s", repo.full_name, exc)
            score, domain_areas, rationale = 0, [], "scoring failed"

        entry: dict = {
            "repo": repo.full_name,
            "score": score,
            "rationale": rationale,
            "domain_areas": domain_areas,
        }

        # Preserve manual_priority from existing YAML
        existing_entry = existing.get(repo.full_name, {})
        if "manual_priority" in existing_entry:
            entry["manual_priority"] = existing_entry["manual_priority"]
            entry["rationale"] += " [manual_priority pinned]"

        entries.append(entry)
        time.sleep(1)  # avoid secondary rate limits

    # Sort: manual_priority first (lower = higher rank), then by score desc
    def _sort_key(e: dict) -> tuple[int, int]:
        mp = e.get("manual_priority")
        return (mp if isinstance(mp, int) else 999, -e["score"])

    entries.sort(key=_sort_key)

    # Assign sequential priority ranks
    for i, entry in enumerate(entries, start=1):
        entry["priority"] = i

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(entries, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info("Wrote %d repos to %s", len(entries), output_path)
    return output_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Build FloQast repo priority index")
    parser.add_argument("--max-repos", type=int, default=50, help="Max repos to score (default: 50)")
    parser.add_argument(
        "--output",
        type=Path,
        default=_OUTPUT_DEFAULT,
        help=f"Output YAML path (default: {_OUTPUT_DEFAULT})",
    )
    args = parser.parse_args()

    try:
        output = build_repo_index(max_repos=args.max_repos, output_path=args.output)
        print(f"✓ Repo index written: {output}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
