#!/usr/bin/env python3
"""
Demo: find a merged PR that mentions a Jira ticket and run full analysis.
Run from project root with venv activated:  python scripts/demo_ticket.py [TICKET] [ORG]
Example:  python scripts/demo_ticket.py CLOSE-13455 FloQastInc
"""
from __future__ import annotations

import os
import subprocess
import sys

# Run from project root (parent of scripts/)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    ticket = sys.argv[1] if len(sys.argv) > 1 else "CLOSE-13455"
    org = sys.argv[2] if len(sys.argv) > 2 else "FloQastInc"
    print("==============================================")
    print("Demo: Ticket-based PR analysis")
    print(f"  Ticket: {ticket}")
    print(f"  Org:    {org}")
    print("==============================================\n")
    from src.github_service import GitHubService

    gh = GitHubService()
    pairs = gh.get_prs_mentioning_ticket(ticket, org=org, limit=1)
    if not pairs:
        print(f"No merged PR found mentioning {ticket} in org {org}.")
        return 1
    repo, pr = pairs[0]
    print(f"Found: {repo} PR #{pr}\n")
    code = subprocess.call(
        [
            sys.executable,
            "-m",
            "src.cli",
            "analyze_change",
            "--repo",
            repo,
            "--pr",
            str(pr),
            "--cache",
        ],
        cwd=_ROOT,
    )
    if code == 0:
        print(f"\nReport written to: reports/pr_{pr}_report.md")
    return code


if __name__ == "__main__":
    sys.exit(main())
