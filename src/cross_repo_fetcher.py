"""Cross-repo sibling fetcher — fetch equivalent files from sibling modules for reference."""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_SIBLINGS = 3
_MAX_FILE_CHARS = 3000


@dataclass
class SiblingRef:
    module: str
    relative_path: str
    content: str


@dataclass
class SiblingContext:
    refs: list[SiblingRef] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.refs

    def as_text(self) -> str:
        if not self.refs:
            return ""
        parts: list[str] = []
        for ref in self.refs:
            parts.append(f"### {ref.module}/{ref.relative_path}")
            parts.append(f"```\n{ref.content}\n```")
        return "\n".join(parts)


def _infer_module_paths(file_paths: list[str]) -> dict[str, list[str]]:
    """Infer (parent_dir, module_name) → [relative_paths] from a list of file paths.

    Looks for a common parent directory shared by ≥ 2 files, then extracts the
    module segment immediately under that parent.

    Returns a dict: module_name → list of relative paths within that module.
    """
    from collections import Counter

    # Count how often each depth-2 prefix appears (e.g. "ui/checklist-client")
    prefix_count: Counter[str] = Counter()
    for p in file_paths:
        parts = p.replace("\\", "/").split("/")
        if len(parts) >= 3:
            prefix = "/".join(parts[:2])
            prefix_count[prefix] += 1

    # Use prefix with the most files
    if not prefix_count:
        return {}

    top_prefix, count = prefix_count.most_common(1)[0]
    if count < 2:
        return {}

    prefix_parts = top_prefix.split("/")
    parent_dir = prefix_parts[0]
    source_module = prefix_parts[1]

    rel_paths: list[str] = []
    for p in file_paths:
        parts = p.replace("\\", "/").split("/")
        if len(parts) >= 3 and parts[0] == parent_dir and parts[1] == source_module:
            rel_paths.append("/".join(parts[2:]))

    return {
        "_parent": parent_dir,
        "_source": source_module,
        "_rel_paths": rel_paths,  # type: ignore[dict-item]
    }


class CrossRepoSiblingFetcher:
    """Fetch equivalent files from sibling modules in the same repository."""

    def __init__(self, github_repo: object) -> None:
        """github_repo: a PyGithub Repository object (or compatible)."""
        self._repo = github_repo

    def fetch(self, file_changes: list, enabled: bool = True) -> SiblingContext:
        """Main entry point. Returns empty SiblingContext when disabled or on error."""
        if not enabled:
            return SiblingContext()

        try:
            return self._fetch_impl(file_changes)
        except Exception as exc:
            logger.warning("CrossRepoSiblingFetcher failed: %s", exc)
            return SiblingContext()

    def _fetch_impl(self, file_changes: list) -> SiblingContext:
        from src.file_classification import is_test_file

        prod_paths = [
            fc.filename for fc in file_changes
            if not is_test_file(fc.filename)
        ]

        if not prod_paths:
            return SiblingContext()

        info = _infer_module_paths(prod_paths)
        if not info:
            return SiblingContext()

        parent_dir: str = info["_parent"]  # type: ignore[index]
        source_module: str = info["_source"]  # type: ignore[index]
        rel_paths: list[str] = info["_rel_paths"]  # type: ignore[index]

        if not rel_paths:
            return SiblingContext()

        # Discover sibling modules
        siblings = self._discover_siblings(parent_dir, source_module)
        if not siblings:
            return SiblingContext()

        # Fetch the first rel_path from up to MAX_SIBLINGS siblings
        refs: list[SiblingRef] = []
        target_path = rel_paths[0]  # Most representative file

        for sibling in siblings[:_MAX_SIBLINGS]:
            full_path = f"{parent_dir}/{sibling}/{target_path}"
            content = self._fetch_file(full_path)
            if content:
                refs.append(SiblingRef(
                    module=sibling,
                    relative_path=target_path,
                    content=content,
                ))

        return SiblingContext(refs=refs)

    def _discover_siblings(self, parent_dir: str, source_module: str) -> list[str]:
        """List subdirectories of parent_dir that are not the source module."""
        try:
            contents = self._repo.get_contents(parent_dir)
            siblings = [
                c.name for c in contents
                if c.type == "dir"
                and c.name != source_module
                and not c.name.startswith(".")
            ]
            return siblings
        except Exception as exc:
            logger.warning("Failed to list siblings under %s: %s", parent_dir, exc)
            return []

    def _fetch_file(self, path: str) -> Optional[str]:
        """Fetch file content at path; return truncated string or None on error."""
        try:
            file_content = self._repo.get_contents(path)
            raw = base64.b64decode(file_content.content).decode("utf-8", errors="replace")
            if len(raw) > _MAX_FILE_CHARS:
                raw = raw[:_MAX_FILE_CHARS] + "\n[truncated]"
            return raw
        except Exception as exc:
            err = str(exc)
            # 404 = sibling MFE often has no mirror path — expected, not worth stderr noise
            if "404" in err or '"status": "404"' in err:
                logger.debug("Sibling reference missing (404): %s", path)
                return None
            if "403" in err or "429" in err:
                logger.warning("Skipped sibling file %s: %s", path, exc)
                return None
            logger.debug("Could not fetch %s: %s", path, exc)
            return None
