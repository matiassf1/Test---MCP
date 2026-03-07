"""Entrypoint for the PR Testing Impact Analyzer.

Usage examples:
  python analyze_change.py analyze_change --repo org/project --pr 123
  python analyze_change.py analyze_author --org MyOrg --author jdoe --since 50d
  python analyze_change.py generate_summary --repo org/project --since 30d --fetch
"""
import sys

# Ensure stdout/stderr can handle Unicode on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    from src.cli import main
    sys.exit(main())
