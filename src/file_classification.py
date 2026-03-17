"""Shared file classification helpers.

Centralises is_test_file / is_generated / is_contract_or_spec logic used by
change_analyzer, ai_reporter, ai_analyzer, test_detector, and pipeline.
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

# Path segments that indicate API contract / spec / generated route code (no business logic).
# PRs that are mostly these are "contract-only" — testing is expected in follow-up PRs.
CONTRACT_SPEC_PATH_SEGMENTS = frozenset({
    "domain.oas3.json", ".oas3.json", "/generated/", "/__generated__/",
    "schemas.ts", "schemas.js", "/dtos/", "/mappers.ts", "/mappers.js",
    "express/handlers", "express/router-factory", "route-middleware-builder",
    "authorization-middleware", "authorization.ts", "constants/policies",
    "types.ts",  # often generated DTO types
})


def is_contract_or_spec_file(filename: str) -> bool:
    """True if the file is part of an API contract/spec or generated route layer (no business logic)."""
    normalized = filename.replace("\\", "/").lower()
    return any(seg in normalized for seg in CONTRACT_SPEC_PATH_SEGMENTS)


def is_contract_only_pr(production_paths: list[str], min_ratio: float = 0.75) -> bool:
    """True if the PR is predominantly contract/spec-only (OpenAPI, generated routes, stubs).

    Such PRs typically do not add tests; testing is done in follow-up PRs when logic is implemented.
    """
    if not production_paths or len(production_paths) < 2:
        return False
    contract_count = sum(1 for p in production_paths if is_contract_or_spec_file(p) or is_generated(p))
    return (contract_count / len(production_paths)) >= min_ratio


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
