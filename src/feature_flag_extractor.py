"""Feature flag extractor — mines Harness flag keys and tlcModules entries from GitHub source.

Scans file trees of priority repos via the GitHub API (no clone required).
Writes results to domain_knowledge/feature_flags.md.

Usage:
    extractor = FeatureFlagExtractor()
    result = extractor.extract(repos=["FloQastInc/close", "FloQastInc/close-ui"])
    extractor.write_output(result)
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Harness flag key constants / assignments (close_ prefix)
_HARNESS_CONST_RE = re.compile(r'["\'](?P<key>close_[a-z0-9_\-]+)["\']', re.IGNORECASE)

# Usage-site patterns: useFeatureFlag / getFeatureFlag / featureFlagClient.variation
_HARNESS_USAGE_RE = re.compile(
    r'(?:useFeatureFlag|getFeatureFlag|featureFlagClient\.variation|isFeatureFlagEnabled)'
    r'\s*\(\s*["\'](?P<key>close_[a-z0-9_\-]+)["\']',
    re.IGNORECASE,
)

# tlcModules access patterns
_TLC_ACCESS_RE = re.compile(
    r'(?:tlcModules\s*\[\s*|getTlcModule\s*\(\s*|isTlcModuleEnabled\s*\(\s*)'
    r'["\'](?P<key>[a-zA-Z0-9_\-]+)["\']',
)

# File patterns for constant/definition files (higher priority for owning module)
_FLAG_CONST_FILE_RE = re.compile(
    r'(?:featureFlag|feature-flag|constants/flag|featureFlags|feature_flags)',
    re.IGNORECASE,
)
_TLC_REGISTRY_RE = re.compile(
    r'(?:tlcModules|module-registry|moduleConfig|moduleRegistry)',
    re.IGNORECASE,
)

# Test file exclusions
_TEST_FILE_RE = re.compile(
    r'(?:__tests__/|\.test\.(?:ts|js)|\.spec\.(?:ts|js))',
    re.IGNORECASE,
)

# Extensions to scan
_SCANNABLE_EXTS = {".ts", ".js", ".tsx", ".jsx"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class FlagEntry:
    __slots__ = ("key", "owning_file", "file_count", "is_const_file", "flag_type")

    def __init__(self, key: str, owning_file: str, is_const_file: bool, flag_type: str) -> None:
        self.key = key
        self.owning_file = owning_file
        self.file_count = 1
        self.is_const_file = is_const_file
        self.flag_type = flag_type  # "harness" | "tlcmodules"

    def merge(self, file_path: str, is_const: bool) -> None:
        self.file_count += 1
        if is_const and not self.is_const_file:
            self.owning_file = file_path
            self.is_const_file = True


class ExtractionResult:
    def __init__(self) -> None:
        self.harness: dict[str, FlagEntry] = {}   # key -> FlagEntry
        self.tlcmodules: dict[str, FlagEntry] = {}

    def add(self, flag_type: str, key: str, file_path: str, is_const: bool) -> None:
        store = self.harness if flag_type == "harness" else self.tlcmodules
        if key in store:
            store[key].merge(file_path, is_const)
        else:
            store[key] = FlagEntry(key=key, owning_file=file_path, is_const_file=is_const, flag_type=flag_type)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class FeatureFlagExtractor:
    """Scans priority repos via GitHub API for Harness flags and tlcModules entries."""

    def __init__(self, github_service=None) -> None:
        from src.github_service import GitHubService
        self._gh = github_service or GitHubService()

    def extract(self, repos: list[str]) -> ExtractionResult:
        """Scan all repos and return aggregated extraction result."""
        result = ExtractionResult()
        for repo_name in repos:
            try:
                self._scan_repo(repo_name, result)
            except Exception as exc:
                logger.warning("FeatureFlagExtractor: skipping %s — %s", repo_name, exc)
        return result

    def write_output(
        self,
        result: ExtractionResult,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Write feature_flags.md, merging with existing content on re-run."""
        out = output_path or Path(settings.feature_flags_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Load existing entries to update seen-in counts
        existing = self._load_existing(out)
        self._merge_into_existing(existing, result)

        lines: list[str] = ["# Feature Flags (mined)\n\n## Harness Flags\n"]
        if existing["harness"]:
            for key, entry in sorted(existing["harness"].items()):
                lines.append(
                    f"- `{key}`: owning module: `{entry.owning_file}`; seen in: {entry.file_count} files\n"
                )
        else:
            lines.append("(none found)\n")

        lines.append("\n## tlcModules\n")
        if existing["tlcmodules"]:
            for key, entry in sorted(existing["tlcmodules"].items()):
                lines.append(
                    f"- `{key}`: owning module: `{entry.owning_file}`; seen in: {entry.file_count} files\n"
                )
        else:
            lines.append("(none found)\n")

        out.write_text("".join(lines), encoding="utf-8")
        logger.info("Wrote %d Harness flags and %d tlcModules to %s",
                    len(existing["harness"]), len(existing["tlcmodules"]), out)
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan_repo(self, repo_name: str, result: ExtractionResult) -> None:
        if not self._gh._client:
            logger.warning("FeatureFlagExtractor: GitHub client unavailable")
            return

        try:
            gh_repo = self._gh._client.get_repo(repo_name)
            tree = gh_repo.get_git_tree(gh_repo.default_branch, recursive=True)
        except Exception as exc:
            logger.warning("FeatureFlagExtractor: skipping %s — tree fetch failed: %s", repo_name, exc)
            return

        for item in (tree.tree or []):
            if item.type != "blob":
                continue
            path = item.path
            ext = Path(path).suffix.lower()
            if ext not in _SCANNABLE_EXTS:
                continue
            if _TEST_FILE_RE.search(path):
                continue

            try:
                blob = gh_repo.get_git_blob(item.sha)
                import base64
                content = base64.b64decode(blob.content).decode("utf-8", errors="replace")
            except Exception:
                continue

            is_flag_const = bool(_FLAG_CONST_FILE_RE.search(path))
            is_tlc_registry = bool(_TLC_REGISTRY_RE.search(path))

            # Harness: constant definitions
            if is_flag_const:
                for m in _HARNESS_CONST_RE.finditer(content):
                    result.add("harness", m.group("key").lower(), path, is_const=True)

            # Harness: usage sites
            for m in _HARNESS_USAGE_RE.finditer(content):
                result.add("harness", m.group("key").lower(), path, is_const=is_flag_const)

            # tlcModules: registry definitions
            if is_tlc_registry:
                for m in _TLC_ACCESS_RE.finditer(content):
                    result.add("tlcmodules", m.group("key"), path, is_const=True)

            # tlcModules: usage sites
            for m in _TLC_ACCESS_RE.finditer(content):
                result.add("tlcmodules", m.group("key"), path, is_const=is_tlc_registry)

    def _load_existing(self, path: Path) -> dict:
        """Parse existing feature_flags.md back into dicts for merging."""
        stores: dict = {"harness": {}, "tlcmodules": {}}
        if not path.exists():
            return stores

        current_section = None
        entry_re = re.compile(
            r"^- `(?P<key>[^`]+)`: owning module: `(?P<owning>[^`]+)`; seen in: (?P<count>\d+) files"
        )
        for line in path.read_text(encoding="utf-8").splitlines():
            if "## Harness Flags" in line:
                current_section = "harness"
            elif "## tlcModules" in line:
                current_section = "tlcmodules"
            elif current_section:
                m = entry_re.match(line)
                if m:
                    key = m.group("key")
                    entry = FlagEntry(
                        key=key,
                        owning_file=m.group("owning"),
                        is_const_file=False,
                        flag_type=current_section,
                    )
                    entry.file_count = int(m.group("count"))
                    stores[current_section][key] = entry
        return stores

    def _merge_into_existing(self, existing: dict, new_result: ExtractionResult) -> None:
        """Merge new extraction result into existing entries dict."""
        for flag_type, store in [("harness", new_result.harness), ("tlcmodules", new_result.tlcmodules)]:
            for key, entry in store.items():
                if key in existing[flag_type]:
                    existing[flag_type][key].file_count = entry.file_count
                    if entry.is_const_file:
                        existing[flag_type][key].owning_file = entry.owning_file
                        existing[flag_type][key].is_const_file = True
                else:
                    existing[flag_type][key] = entry
