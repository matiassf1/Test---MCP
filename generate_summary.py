"""Entrypoint for: python generate_summary.py --repo org/project --since 30d

Multi-repo usage:
    python generate_summary.py --repos repos.yaml --since 30d --fetch
"""
import sys
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a team testing summary across PRs")

    repo_group = parser.add_mutually_exclusive_group(required=True)
    repo_group.add_argument("--repo", help="GitHub repo, e.g. org/project")
    repo_group.add_argument(
        "--repos",
        metavar="FILE",
        help="Path to repos.yaml for multi-repo analysis",
    )

    parser.add_argument(
        "--since",
        default="30d",
        help="Time window, e.g. '30d' (default: 30d)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch and analyze merged PRs from GitHub before summarizing",
    )
    parser.add_argument(
        "--storage",
        choices=["json", "sqlite"],
        default="json",
        help="Storage backend: 'json' (default) or 'sqlite'",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        default=False,
        help="Cache GitHub API responses to disk (reduces rate-limit risk)",
    )
    args = parser.parse_args()

    from src.cli import cmd_generate_summary
    sys.exit(cmd_generate_summary(args))


if __name__ == "__main__":
    main()
