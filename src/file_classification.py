"""Shared file classification helpers.

Centralises is_test_file / is_generated logic used by change_analyzer,
ai_reporter, ai_analyzer, and test_detector.
"""
from __future__ import annotations

import os

GENERATED_PATH_SEGMENTS = frozenset({
    "/generated/", "/__generated__/", "/gen/", "/.generated/",
})

GENERATED_FILE_SUFFIXES = (
    ".generated.ts", ".generated.js", ".generated.py",
    ".g.ts", ".g.js", ".pb.ts", ".pb.js", ".pb.go", "_pb2.py",
)


def is_generated(filename: str) -> bool:
    """True if the file is auto-generated and should be excluded from metrics."""
    normalized = filename.replace("\\", "/").lower()
    if any(seg in normalized for seg in GENERATED_PATH_SEGMENTS):
        return True
    return any(normalized.endswith(suffix) for suffix in GENERATED_FILE_SUFFIXES)


def is_test_file(filename: str) -> bool:
    """True if the file is a test file (any language convention)."""
    base = os.path.basename(filename).lower()
    normalized = filename.replace("\\", "/").lower()
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or ".test." in base
        or ".spec." in base
        or "/tests/" in normalized
        or "/test/" in normalized
        or "/__tests__/" in normalized
    )
