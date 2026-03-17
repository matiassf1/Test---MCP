#!/usr/bin/env python3
"""
Demo: analyze a single PR (metrics + AI report + markdown).
Run from project root with venv activated:  python scripts/demo_pr.py [REPO] [PR]
Example:  python scripts/demo_pr.py FloQastInc/close 5194
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
    repo = sys.argv[1] if len(sys.argv) > 1 else "FloQastInc/close"
    pr = sys.argv[2] if len(sys.argv) > 2 else "5194"
    print("==============================================")
    print("Demo: Single PR analysis")
    print(f"  Repo: {repo}")
    print(f"  PR:   #{pr}")
    print("==============================================\n")
    code = subprocess.call(
        [sys.executable, "-m", "src.cli", "analyze_change", "--repo", repo, "--pr", str(pr), "--cache"],
        cwd=_ROOT,
    )
    if code == 0:
        print(f"\nReport written to: reports/pr_{pr}_report.md")
    return code


if __name__ == "__main__":
    sys.exit(main())
