#!/usr/bin/env python3
"""Clone and/or pull GitHub repos from a repos.yaml list (same format as generate_summary).

Examples:
  python scripts/sync_repos.py --repos-file repos.local.yaml
  python scripts/sync_repos.py --repos FloQastInc/close,FloQastInc/other-repo
  python scripts/sync_repos.py --repos-file repos.local.yaml --root ~/src --branch main

Layout under --root: <root>/<org>/<repo>  (e.g. ~/src/FloQastInc/close)

Requires: git on PATH; PyYAML if using --repos-file (pip install pyyaml).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _load_repos_yaml(path: Path) -> list[str]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: PyYAML required for --repos-file. pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    repos = data.get("repos", [])
    return [str(r).strip() for r in repos if r and str(r).strip()]


def _parse_repo(spec: str) -> tuple[str, str]:
    spec = spec.strip()
    if spec.count("/") != 1:
        raise ValueError(f"Expected 'org/repo', got: {spec!r}")
    org, name = spec.split("/", 1)
    if not org or not name:
        raise ValueError(f"Invalid repo spec: {spec!r}")
    return org.strip(), name.strip()


def _run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()


def _resolve_branch(repo_dir: Path, preferred: str, try_master: bool) -> str:
    code, out = _run(["git", "-C", str(repo_dir), "branch", "-a"], cwd=None)
    if code != 0:
        return preferred
    text = out.lower()
    if f"origin/{preferred}" in text or f"remotes/origin/{preferred}" in text:
        return preferred
    if try_master and ("origin/master" in text or "remotes/origin/master" in text):
        return "master"
    return preferred


def clone_url(org: str, repo: str, ssh: bool) -> str:
    if ssh:
        return f"git@github.com:{org}/{repo}.git"
    return f"https://github.com/{org}/{repo}.git"


def sync_one(
    root: Path,
    org: str,
    repo: str,
    *,
    branch: str,
    try_master: bool,
    ssh: bool,
    dry_run: bool,
) -> tuple[bool, str]:
    dest = root / org / repo
    url = clone_url(org, repo, ssh)

    if (dest / ".git").is_dir():
        br = _resolve_branch(dest, branch, try_master)
        cmds = [
            (["git", "-C", str(dest), "fetch", "origin"], "fetch"),
            (["git", "-C", str(dest), "checkout", br], f"checkout {br}"),
            (["git", "-C", str(dest), "pull", "--ff-only", "origin", br], f"pull {br}"),
        ]
        for cmd, label in cmds:
            if dry_run:
                print(f"  [dry-run] {' '.join(cmd)}")
                continue
            code, out = _run(cmd)
            if code != 0:
                return False, f"{label} failed in {dest}:\n{out or '(no output)'}"
        return True, f"pulled {org}/{repo} @ {br} → {dest}"

    if dry_run:
        print(f"  [dry-run] git clone {url} {dest}")
        return True, f"would clone {org}/{repo} → {dest}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    code, out = _run(["git", "clone", url, str(dest)])
    if code != 0:
        return False, f"clone failed:\n{out or '(no output)'}"

    br = _resolve_branch(dest, branch, try_master)
    code, out = _run(["git", "-C", str(dest), "checkout", br])
    if code != 0:
        return False, f"checkout {br} failed after clone:\n{out or '(no output)'}"

    return True, f"cloned {org}/{repo} @ {br} → {dest}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Clone or pull org/repo list from main (or --branch).")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--repos-file",
        metavar="PATH",
        help="YAML with top-level 'repos: [org/repo, ...]' (same as generate_summary)",
    )
    src.add_argument(
        "--repos",
        metavar="LIST",
        help="Comma-separated org/repo values, e.g. acme/a,acme/b",
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("REPO_SYNC_ROOT", "./workspace"),
        help="Parent directory for clones (default: ./workspace or REPO_SYNC_ROOT env)",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("REPO_SYNC_BRANCH", "main"),
        help="Branch to checkout/pull (default: main or REPO_SYNC_BRANCH)",
    )
    parser.add_argument(
        "--try-master",
        action="store_true",
        help="If origin/main is missing, try master",
    )
    parser.add_argument(
        "--ssh",
        action="store_true",
        help="Use git@github.com: URLs instead of https",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only",
    )
    args = parser.parse_args()

    if args.repos_file:
        repos = _load_repos_yaml(Path(args.repos_file).expanduser().resolve())
    else:
        repos = [r.strip() for r in args.repos.split(",") if r.strip()]

    if not repos:
        print(
            "No repositories listed under `repos:` in the YAML (or empty --repos). "
            "Add real `org/repo` lines — placeholders like acme-org/foo are not valid on GitHub.",
            file=sys.stderr,
        )
        return 1

    root = Path(args.root).expanduser().resolve()
    print(f"Root: {root}")
    print(f"Branch preference: {args.branch}" + (" (+ master fallback)" if args.try_master else ""))
    print()

    failed = 0
    for spec in repos:
        try:
            org, name = _parse_repo(spec)
        except ValueError as e:
            print(f"[SKIP] {spec}: {e}")
            failed += 1
            continue
        print(f"→ {org}/{name}")
        ok, msg = sync_one(
            root,
            org,
            name,
            branch=args.branch,
            try_master=args.try_master,
            ssh=args.ssh,
            dry_run=args.dry_run,
        )
        if ok:
            print(f"  OK — {msg}")
        else:
            print(f"  FAIL — {msg}")
            failed += 1
        print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
