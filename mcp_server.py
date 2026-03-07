"""MCP server exposing PR analysis tools.

Local (stdio) — for Cursor / Claude Desktop:
    python mcp_server.py

Remote (HTTP/SSE) — for shared team access (Railway, Render, Fly.io):
    MCP_TRANSPORT=sse MCP_PORT=8080 python mcp_server.py
"""
from __future__ import annotations

import os
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent

from src.tool_api import (
    analyze_pr,
    get_pr_metrics,
    get_repo_summary,
    get_author_summary,
    get_multi_repo_summary,
)


app = Server("pr-analysis")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_pr",
            description=(
                "Fetch a GitHub PR, run the full analysis pipeline (test quality, "
                "coverage estimate, Jira link), persist metrics, and return a summary. "
                "Use this the first time you analyze a PR, or to refresh stale data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "GitHub repository in org/name format, e.g. FloQastInc/reconciliations_lambdas",
                    },
                    "pr": {
                        "type": "integer",
                        "description": "Pull Request number",
                    },
                    "repo_path": {
                        "type": "string",
                        "description": (
                            "Optional absolute path to a local checkout of the repo. "
                            "When provided, Jest is run to compute mechanical coverage."
                        ),
                    },
                },
                "required": ["repo", "pr"],
            },
        ),
        Tool(
            name="get_pr_metrics",
            description=(
                "Load previously computed metrics for a PR from local storage. "
                "Returns null if the PR has not been analyzed yet."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "org/name"},
                    "pr": {"type": "integer", "description": "PR number"},
                },
                "required": ["repo", "pr"],
            },
        ),
        Tool(
            name="get_repo_summary",
            description=(
                "Return aggregate testing-quality statistics for a repository: "
                "average coverage, average quality score, top contributors, trend."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "org/name"},
                    "since_days": {
                        "type": "integer",
                        "description": "How many days back to include (default 30)",
                        "default": 30,
                    },
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="get_author_summary",
            description=(
                "Return aggregate stats for a single author across all analyzed PRs: "
                "PR count, repos, avg coverage, avg quality score, tests added."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "author": {
                        "type": "string",
                        "description": "GitHub username (exact, as it appears in PRs)",
                    },
                },
                "required": ["author"],
            },
        ),
        Tool(
            name="get_multi_repo_summary",
            description=(
                "Return a combined summary across multiple repositories. "
                "Useful for org-wide dashboards."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repos": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of org/name repos to include",
                    },
                    "since_days": {
                        "type": "integer",
                        "description": "How many days back to include (default 30)",
                        "default": 30,
                    },
                },
                "required": ["repos"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool call handler
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    import json

    try:
        result = _dispatch(name, arguments)
        text = json.dumps(result, default=_json_default, indent=2)
    except Exception as exc:
        text = json.dumps({"error": str(exc)})

    return [TextContent(type="text", text=text)]


def _dispatch(name: str, args: dict[str, Any]) -> Any:
    if name == "analyze_pr":
        metrics = analyze_pr(
            repo=args["repo"],
            pr=int(args["pr"]),
            repo_path=args.get("repo_path"),
        )
        if metrics is None:
            return {"error": "Analysis failed — check GITHUB_TOKEN and repo/PR number"}
        return _metrics_to_dict(metrics)

    if name == "get_pr_metrics":
        metrics = get_pr_metrics(repo=args["repo"], pr=int(args["pr"]))
        if metrics is None:
            return {"error": "No metrics found. Run analyze_pr first."}
        return _metrics_to_dict(metrics)

    if name == "get_repo_summary":
        summary = get_repo_summary(
            repo=args["repo"],
            since_days=int(args.get("since_days", 30)),
        )
        return _summary_to_dict(summary)

    if name == "get_author_summary":
        return get_author_summary(author=args["author"])

    if name == "get_multi_repo_summary":
        summary = get_multi_repo_summary(
            repos=args["repos"],
            since_days=int(args.get("since_days", 30)),
        )
        return _summary_to_dict(summary)

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _json_default(obj: Any) -> Any:
    """Fallback serializer for types json.dumps can't handle."""
    from datetime import datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    try:
        return obj.model_dump()
    except AttributeError:
        return str(obj)


def _metrics_to_dict(metrics) -> dict:
    d = metrics.model_dump(exclude={"file_changes", "test_files"})
    # Summarise file list without bloating the response
    d["files_summary"] = [
        {"file": fc.filename, "status": fc.status, "additions": fc.additions}
        for fc in (metrics.file_changes or [])
    ]
    return d


def _summary_to_dict(summary) -> dict:
    return summary.model_dump(exclude={"pr_metrics", "by_author"})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()

    if transport == "sse":
        # HTTP/SSE for remote hosting
        import uvicorn
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount

        sse = SseServerTransport("/messages")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0], streams[1],
                    InitializationOptions(
                        server_name="pr-analysis",
                        server_version="1.0.0",
                        capabilities=app.get_capabilities(
                            notification_options=None,
                            experimental_capabilities={},
                        ),
                    ),
                )

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages", app=sse.handle_post_message),
            ]
        )

        port = int(os.environ.get("MCP_PORT", "8080"))
        print(f"Starting SSE MCP server on port {port}")
        uvicorn.run(starlette_app, host="0.0.0.0", port=port)

    else:
        # stdio for local Cursor / Claude Desktop
        import asyncio
        from mcp.server.stdio import stdio_server

        async def run():
            async with stdio_server() as (read_stream, write_stream):
                await app.run(
                    read_stream, write_stream,
                    InitializationOptions(
                        server_name="pr-analysis",
                        server_version="1.0.0",
                        capabilities=app.get_capabilities(
                            notification_options=None,
                            experimental_capabilities={},
                        ),
                    ),
                )

        asyncio.run(run())


if __name__ == "__main__":
    main()
