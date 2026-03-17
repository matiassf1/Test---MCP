#!/usr/bin/env python3
"""
Demo: analyze all merged PRs by an author (org-wide, last N days).
Run from project root with venv activated:  python scripts/demo_author.py [AUTHOR] [ORG] [SINCE]
Example:  python scripts/demo_author.py c-sachanocetto_floqast FloQastInc 15d
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
    author = sys.argv[1] if len(sys.argv) > 1 else "c-sachanocetto_floqast"
    org = sys.argv[2] if len(sys.argv) > 2 else "FloQastInc"
    since = sys.argv[3] if len(sys.argv) > 3 else "15d"
    print("==============================================")
    print("Demo: Author analysis")
    print(f"  Author: {author}")
    print(f"  Org:    {org}")
    print(f"  Since:  last {since}")
    print("==============================================\n")
    code = subprocess.call(
        [
            sys.executable,
            "-m",
            "src.cli",
            "analyze_author",
            "--author",
            author,
            "--org",
            org,
            "--since",
            since,
            "--cache",
        ],
        cwd=_ROOT,
    )
    if code == 0:
        print("\nSummary: reports/team_summary.md and reports/team_summary.json")
    return code


if __name__ == "__main__":
    sys.exit(main())
