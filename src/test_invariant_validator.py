"""Test invariant validator — derive always-true domain conditions from existing test files."""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MIN_TEST_CASES = 3
_DEFAULT_THRESHOLD = 0.8

# Match property: value or property=value literals inside test/describe/it blocks
_PROP_COLON_RE = re.compile(
    r"""(?P<prop>\b[a-zA-Z_][a-zA-Z0-9_]{1,30})\s*:\s*(?P<val>true|false|null|undefined|"[^"]{0,60}"|'[^']{0,60}'|\d+)""",
    re.IGNORECASE,
)
_PROP_EQ_RE = re.compile(
    r"""(?P<prop>\b[a-zA-Z_][a-zA-Z0-9_]{1,30})\s*=\s*(?P<val>true|false|null|undefined|"[^"]{0,60}"|'[^']{0,60}'|\d+)""",
    re.IGNORECASE,
)

# Detect test block boundaries
_TEST_BLOCK_RE = re.compile(r"""(?:it|test|describe)\s*\(""")


@dataclass
class TestInvariant:
    property: str
    value: str
    frequency: float
    module: str


@dataclass
class TestInvariantContext:
    invariants: list[TestInvariant] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.invariants

    def as_text(self) -> str:
        if not self.invariants:
            return ""
        lines = ["**Test-derived domain invariants:**"]
        for inv in self.invariants:
            lines.append(
                f"- In `{inv.module}` tests, `{inv.property}` is always `{inv.value}` "
                f"(found in {inv.frequency:.0%} of test cases)"
            )
        return "\n".join(lines)


def _extract_test_blocks(content: str) -> list[str]:
    """Split test file content into individual test case blocks (it/test bodies)."""
    blocks: list[str] = []
    # Find positions of each it/test/describe opening
    for m in _TEST_BLOCK_RE.finditer(content):
        start = m.start()
        # Find the opening paren and matching close brace
        depth = 0
        i = content.find("(", start)
        if i == -1:
            continue
        # Find the opening brace of the callback
        brace_start = content.find("{", i)
        if brace_start == -1:
            continue
        depth = 0
        for j in range(brace_start, min(brace_start + 5000, len(content))):
            if content[j] == "{":
                depth += 1
            elif content[j] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(content[brace_start: j + 1])
                    break
    return blocks


def _extract_pairs(block: str) -> list[tuple[str, str]]:
    """Extract (property, value) pairs from a single test block."""
    pairs: list[tuple[str, str]] = []
    for m in _PROP_COLON_RE.finditer(block):
        pairs.append((m.group("prop"), m.group("val").strip("\"'")))
    for m in _PROP_EQ_RE.finditer(block):
        prop = m.group("prop")
        # Skip JS assignment patterns like `let x = true` at statement level
        # (prefer object literal patterns from _PROP_COLON_RE)
        if prop not in {p for p, _ in pairs}:
            pairs.append((prop, m.group("val").strip("\"'")))
    return pairs


def _infer_module(file_path: str) -> str:
    """Extract module name from file path (e.g. ui/checklist-client/... → checklist-client)."""
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return parts[1] if len(parts) > 2 else parts[0]
    return parts[0] if parts else "unknown"


class TestInvariantValidator:
    """Derive always-true property-value invariants from test files in the diff's module."""

    def validate(
        self,
        file_changes: list,
        repo_root: Optional[str] = None,
        threshold: float = _DEFAULT_THRESHOLD,
        enabled: bool = True,
    ) -> TestInvariantContext:
        if not enabled:
            return TestInvariantContext()

        try:
            return self._validate_impl(file_changes, repo_root, threshold)
        except Exception as exc:
            logger.warning("TestInvariantValidator failed: %s", exc)
            return TestInvariantContext()

    def _validate_impl(
        self,
        file_changes: list,
        repo_root: Optional[str],
        threshold: float,
    ) -> TestInvariantContext:
        from src.file_classification import is_test_file

        # Collect all test file patches from the diff
        test_patches: dict[str, str] = {}
        for fc in file_changes:
            if is_test_file(fc.filename) and fc.patch:
                test_patches[fc.filename] = fc.patch

        # Also try to read full test files from disk when repo_root is available
        if repo_root:
            for fc in file_changes:
                if is_test_file(fc.filename) and fc.filename not in test_patches:
                    try:
                        full_path = Path(repo_root) / fc.filename
                        content = full_path.read_text(encoding="utf-8", errors="replace")
                        test_patches[fc.filename] = content
                    except Exception:
                        pass

        if not test_patches:
            return TestInvariantContext()

        # Group by module
        module_blocks: dict[str, list[list[tuple[str, str]]]] = defaultdict(list)

        for filename, content in test_patches.items():
            module = _infer_module(filename)
            try:
                blocks = _extract_test_blocks(content)
                if not blocks:
                    # Fallback: treat the whole content as a single block
                    blocks = [content]
                for block in blocks:
                    pairs = _extract_pairs(block)
                    if pairs:
                        module_blocks[module].append(pairs)
            except Exception as exc:
                logger.warning("Skipping %s due to parse error: %s", filename, exc)
                continue

        invariants: list[TestInvariant] = []

        for module, all_block_pairs in module_blocks.items():
            n_blocks = len(all_block_pairs)
            if n_blocks < _MIN_TEST_CASES:
                continue

            # Count how many blocks contain each (prop, val) pair
            pair_counter: Counter[tuple[str, str]] = Counter()
            for block_pairs in all_block_pairs:
                seen = set(block_pairs)
                for pair in seen:
                    pair_counter[pair] += 1

            for (prop, val), count in pair_counter.items():
                freq = count / n_blocks
                if freq >= threshold and count >= _MIN_TEST_CASES:
                    # Skip trivially common pairs (e.g. wrapper: true) that are noise
                    if len(prop) > 2 and prop.lower() not in {"key", "ref", "id", "type"}:
                        invariants.append(TestInvariant(
                            property=prop,
                            value=val,
                            frequency=round(freq, 2),
                            module=module,
                        ))

        # Sort by frequency descending; cap at 10 to avoid prompt bloat
        invariants.sort(key=lambda x: x.frequency, reverse=True)
        return TestInvariantContext(invariants=invariants[:10])
