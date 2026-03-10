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
    get_pr_description_report as _get_pr_description_report,
    get_repo_summary as _get_repo_summary,
    get_author_summary as _get_author_summary,
    get_multi_repo_summary as _get_multi_repo_summary,
    list_prs_by_author as _list_prs_by_author,
    list_prs_by_jira_ticket as _list_prs_by_jira_ticket,
    analyze_pr_by_jira_ticket as _analyze_pr_by_jira_ticket,
    batch_analyze_author as _batch_analyze_author,
    batch_analyze_repo as _batch_analyze_repo,
)

_port = int(os.environ.get("MCP_PORT", os.environ.get("PORT", "8080")))
mcp = FastMCP("pr-analysis", host="0.0.0.0", port=_port)


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


def _metrics_dict(metrics, include_description_report: bool = False) -> dict:
    d = metrics.model_dump(exclude={"file_changes", "test_files"})
    d["files_summary"] = [
        {"file": fc.filename, "status": fc.status, "additions": fc.additions}
        for fc in (metrics.file_changes or [])
    ]
    if include_description_report:
        try:
            from src.report_generator import ReportGenerator
            d["description_markdown"] = ReportGenerator().pr_description_snippet(metrics)
        except Exception:
            d["description_markdown"] = None
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
    include_description_report: bool = True,
) -> str:
    """Fetch a GitHub PR, run the full analysis pipeline (test quality, LLM coverage
    estimate, Jira link), persist metrics, and return a JSON summary.

    When include_description_report is True (default), the response includes
    \"description_markdown\": a markdown block you can paste into the PR description.

    Args:
        repo: GitHub repository in org/name format, e.g. FloQastInc/reconciliations_lambdas
        pr: Pull Request number
        repo_path: Optional absolute path to a local checkout. When provided, Jest
                   runs to compute mechanical coverage for changed JS/TS files.
        include_description_report: If True, add description_markdown to the response (default True)
    """
    metrics = _analyze_pr(repo=repo, pr=pr, repo_path=repo_path)
    if metrics is None:
        return _json({"error": "Analysis failed — check GITHUB_TOKEN and repo/PR number"})
    return _json(_metrics_dict(metrics, include_description_report=include_description_report))


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
def get_pr_description_report(repo: str, pr: int, run_analysis_if_missing: bool = True) -> str:
    """Return a markdown report ready to paste into the PR description.

    Includes testing quality score, coverage, test ratio, and AI analysis (if available).
    Use the returned \"markdown\" field as the body for the PR description or a comment.

    Args:
        repo: GitHub repository in org/name format, e.g. FloQastInc/reconciliations_lambdas
        pr: Pull Request number
        run_analysis_if_missing: If True (default), run analyze_pr when metrics are not in storage
    """
    out = _get_pr_description_report(
        repo=repo, pr=pr, run_analysis_if_missing=run_analysis_if_missing
    )
    return _json(out)


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
def list_prs_by_jira_ticket(
    ticket_key: str,
    org: str,
    limit: int = 20,
) -> str:
    """List merged PRs that mention the given Jira ticket (e.g. CLOSE-13348).

    Search is by ticket key in PR title, body, or branch. Use analyze_pr_by_jira_ticket
    to analyze the first (or chosen) PR without needing repo/number.

    Args:
        ticket_key: Jira ticket key (e.g. CLOSE-13348, FQ-1234)
        org: GitHub organization (e.g. FloQastInc)
        limit: Max PRs to return (default 20)
    """
    return _json(_list_prs_by_jira_ticket(ticket_key=ticket_key, org=org, limit=limit))


@mcp.tool()
def analyze_pr_by_jira_ticket(
    ticket_key: str,
    org: str,
    pr_index: int = 0,
) -> str:
    """Find merged PR(s) for the Jira ticket, analyze one, and return full metrics + report.

    Uses GitHub Search for the ticket key, then runs the same pipeline as analyze_pr
    on the PR at pr_index (0 = most recent). No need to look up repo/PR number.

    Args:
        ticket_key: Jira ticket key (e.g. CLOSE-13348)
        org: GitHub organization (e.g. FloQastInc)
        pr_index: Which PR to analyze if several mention the ticket (0 = first/most recent)
    """
    return _json(_analyze_pr_by_jira_ticket(ticket_key=ticket_key, org=org, pr_index=pr_index))


# analyze_epic disabled: long-running, causes client timeout. Use CLI: python analyze_change.py analyze_epic --epic X --org Y
# @mcp.tool()
# def analyze_epic(...): ...


@mcp.tool()
def list_prs_by_author(
    author: str,
    org: str,
    since_days: int = 90,
    limit: int = 50,
) -> str:
    """List merged PRs by author in an org (discovery only, no analysis).
    Use the returned repo+pr pairs with analyze_pr to process one PR at a time.

    Args:
        author: GitHub username
        org: GitHub organization (e.g. FloQastInc)
        since_days: How far back to search (default 90)
        limit: Max PRs to return (default 50)
    """
    return _json(_list_prs_by_author(author=author, org=org, since_days=since_days, limit=limit))


@mcp.tool()
def get_multi_repo_summary(repos: list[str], since_days: int = 30) -> str:
    """Return a combined testing-quality summary across multiple repositories.

    Args:
        repos: List of repositories in org/name format
        since_days: How many days back to include (default 30)
    """
    summary = _get_multi_repo_summary(repos=repos, since_days=since_days)
    return _json(_summary_dict(summary))


@mcp.tool()
def batch_analyze_author(
    author: str,
    org: str,
    since_days: int = 30,
    limit: int = 20,
    skip_existing: bool = True,
) -> str:
    """Discover and analyze all merged PRs by an author across an entire GitHub org.

    Finds PRs via GitHub Search, runs the full analysis pipeline on each, and
    persists results. Already-analyzed PRs are skipped by default.
    Call get_author_summary or get_multi_repo_summary afterward to see aggregates.

    Args:
        author: GitHub username
        org: GitHub organization name (e.g. FloQastInc)
        since_days: How far back to search for merged PRs (default 30)
        limit: Max PRs to analyze in this call (default 20, keep low to avoid timeouts)
        skip_existing: Skip PRs already in storage (default True)
    """
    return _json(_batch_analyze_author(
        author=author, org=org, since_days=since_days,
        limit=limit, skip_existing=skip_existing,
    ))


@mcp.tool()
def batch_analyze_repo(
    repo: str,
    since_days: int = 30,
    limit: int = 20,
    skip_existing: bool = True,
) -> str:
    """Discover and analyze all merged PRs in a single repository.

    Fetches merged PRs since since_days ago, runs the full analysis pipeline on
    each, and persists results. Call get_repo_summary afterward for aggregates.

    Args:
        repo: GitHub repository in org/name format
        since_days: How far back to search (default 30)
        limit: Max PRs to analyze in this call (default 20)
        skip_existing: Skip PRs already in storage (default True)
    """
    return _json(_batch_analyze_repo(
        repo=repo, since_days=since_days,
        limit=limit, skip_existing=skip_existing,
    ))


# ---------------------------------------------------------------------------
# SSE fixes: OAuth discovery + POST /sse → 405 with Allow: GET
# ---------------------------------------------------------------------------

def _make_sse_wrapped_app():
    """Wrap MCP SSE app so /.well-known and POST /sse don't 404/405. Optional auth via MCP_AUTH_SECRET."""
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse, Response
    from starlette.middleware.base import BaseHTTPMiddleware

    try:
        from src.config import settings
        _auth_secret = (settings.mcp_auth_secret or "").strip()
    except Exception:
        _auth_secret = (os.environ.get("MCP_AUTH_SECRET") or "").strip()

    def exception_handler(request, exc):
        # Avoid 500 when client disconnects or times out; keep server up for next request.
        name = type(exc).__name__
        msg = str(exc).lower()
        if name == "ClosedResourceError":
            return Response(status_code=202, content=b"")
        if name in ("TimeoutError", "CancelledError", "asyncio.CancelledError"):
            return Response(status_code=202, content=b"")
        if "timed out" in msg or "timeout" in msg or "cancelled" in msg or "requestresponder" in msg or "context manager" in msg:
            return Response(status_code=202, content=b"")
        raise exc

    async def oauth_well_known(_request):
        # OAuth discovery: return minimal JSON so probes get 200 instead of 404
        return JSONResponse({
            "issuer": "/",
            "authorization_endpoint": "/oauth/authorize",
            "token_endpoint": "/oauth/token",
        }, status_code=200)

    async def post_sse_not_allowed(_request):
        # POST /sse → 405; client must use GET for the SSE stream
        return Response(
            status_code=405,
            headers={"Allow": "GET", "Content-Type": "application/json"},
            content=b'{"error":"Use GET /sse for the event stream"}',
        )

    # Get the raw SSE/HTTP app from FastMCP (API varies by SDK version)
    raw_app = None
    try:
        if hasattr(mcp, "sse_app"):
            raw_app = mcp.sse_app()
        elif hasattr(mcp, "http_app"):
            try:
                raw_app = mcp.http_app(transport="sse")
            except TypeError:
                raw_app = mcp.http_app()
        elif hasattr(mcp, "get_asgi_app"):
            raw_app = mcp.get_asgi_app(transport="sse")
    except (AttributeError, TypeError):
        pass
    if raw_app is None:
        raw_app = getattr(mcp, "_app", None)
    if raw_app is None:
        return None

    app = Starlette(
        routes=[
            Route("/.well-known/oauth-authorization-server", oauth_well_known, methods=["GET"]),
            Route("/sse", post_sse_not_allowed, methods=["POST"]),
            Mount("/", raw_app),
        ],
        exception_handlers={Exception: exception_handler},
    )

    # Optional: require API key for /sse (and any path under /) when MCP_AUTH_SECRET is set
    if _auth_secret:

        class RequireMCPAuth(BaseHTTPMiddleware):
            def __init__(self, app, secret: str):
                super().__init__(app)
                self._secret = secret

            async def dispatch(self, request, call_next):
                path = request.url.path or ""
                if path == "/sse" or path.startswith("/sse?"):
                    auth = request.headers.get("authorization") or request.headers.get("Authorization")
                    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
                    if auth and auth.strip().lower().startswith("bearer "):
                        token = auth.split(maxsplit=1)[1].strip()
                    else:
                        token = api_key or ""
                    if token != self._secret:
                        return Response(
                            status_code=401,
                            content=b'{"error":"Unauthorized: missing or invalid MCP auth (use Authorization: Bearer <secret> or X-API-Key: <secret>)"}',
                            headers={"Content-Type": "application/json", "WWW-Authenticate": "Bearer"},
                        )
                return await call_next(request)

        app.add_middleware(RequireMCPAuth, secret=_auth_secret)

    return app


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()

    if transport == "sse":
        print(f"Starting SSE MCP server on port {_port}")
        wrapped = _make_sse_wrapped_app()
        if wrapped is not None:
            import uvicorn
            uvicorn.run(wrapped, host="0.0.0.0", port=_port)
        else:
            mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
