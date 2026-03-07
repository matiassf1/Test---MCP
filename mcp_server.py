"""MCP server exposing PR analysis tools.

Local (stdio) — for Cursor / Claude Desktop:
    python mcp_server.py

Remote (HTTP/SSE) — for shared team access (Railway, Render, Fly.io):
    MCP_TRANSPORT=sse MCP_PORT=8080 python mcp_server.py
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from src.tool_api import (
    analyze_pr as _analyze_pr,
    get_pr_metrics as _get_pr_metrics,
    get_repo_summary as _get_repo_summary,
    get_author_summary as _get_author_summary,
    get_multi_repo_summary as _get_multi_repo_summary,
)

mcp = FastMCP("pr-analysis")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(obj: Any) -> str:
    def _default(o):
        from datetime import datetime
        if isinstance(o, datetime):
            return o.isoformat()
        try:
            return o.model_dump()
        except AttributeError:
            return str(o)
    return json.dumps(obj, default=_default, indent=2)


def _metrics_dict(metrics) -> dict:
    d = metrics.model_dump(exclude={"file_changes", "test_files"})
    d["files_summary"] = [
        {"file": fc.filename, "status": fc.status, "additions": fc.additions}
        for fc in (metrics.file_changes or [])
    ]
    return d


def _summary_dict(summary) -> dict:
    return summary.model_dump(exclude={"pr_metrics", "by_author"})


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_pr(
    repo: str,
    pr: int,
    repo_path: Optional[str] = None,
) -> str:
    """Fetch a GitHub PR, run the full analysis pipeline (test quality, LLM coverage
    estimate, Jira link), persist metrics, and return a JSON summary.

    Args:
        repo: GitHub repository in org/name format, e.g. FloQastInc/reconciliations_lambdas
        pr: Pull Request number
        repo_path: Optional absolute path to a local checkout. When provided, Jest
                   runs to compute mechanical coverage for changed JS/TS files.
    """
    metrics = _analyze_pr(repo=repo, pr=pr, repo_path=repo_path)
    if metrics is None:
        return _json({"error": "Analysis failed — check GITHUB_TOKEN and repo/PR number"})
    return _json(_metrics_dict(metrics))


@mcp.tool()
def get_pr_metrics(repo: str, pr: int) -> str:
    """Load previously computed metrics for a PR from local storage.

    Args:
        repo: GitHub repository in org/name format
        pr: Pull Request number
    """
    metrics = _get_pr_metrics(repo=repo, pr=pr)
    if metrics is None:
        return _json({"error": "No metrics found. Run analyze_pr first."})
    return _json(_metrics_dict(metrics))


@mcp.tool()
def get_repo_summary(repo: str, since_days: int = 30) -> str:
    """Return aggregate testing-quality stats for a repository: average coverage,
    average quality score, top contributors, trend over time.

    Args:
        repo: GitHub repository in org/name format
        since_days: How many days back to include (default 30)
    """
    summary = _get_repo_summary(repo=repo, since_days=since_days)
    return _json(_summary_dict(summary))


@mcp.tool()
def get_author_summary(author: str) -> str:
    """Return aggregate stats for a single author across all analyzed PRs:
    PR count, repos, avg coverage, avg quality score, total tests added.

    Args:
        author: GitHub username exactly as it appears in PRs
    """
    return _json(_get_author_summary(author=author))


@mcp.tool()
def get_multi_repo_summary(repos: list[str], since_days: int = 30) -> str:
    """Return a combined testing-quality summary across multiple repositories.

    Args:
        repos: List of repositories in org/name format
        since_days: How many days back to include (default 30)
    """
    summary = _get_multi_repo_summary(repos=repos, since_days=since_days)
    return _json(_summary_dict(summary))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    port = int(os.environ.get("MCP_PORT", "8080"))

    if transport == "sse":
        print(f"Starting SSE MCP server on port {port}")
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")
