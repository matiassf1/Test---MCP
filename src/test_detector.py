from __future__ import annotations

import os
from typing import Optional

from src.file_classification import is_generated, is_test_file
from src.models import FileChange, TestFile, TestType


# ---------------------------------------------------------------------------
# Framework/library signals for content-based classification
# ---------------------------------------------------------------------------

# Any of these in added lines → e2e
_E2E_SIGNALS = [
    "playwright",
    "from playwright",
    "import playwright",
    "selenium",
    "webdriver",
    "from selenium",
    "import selenium",
    "puppeteer",
    "cypress",
    "cy.visit",
    "cy.get",
    "page.goto",
    "page.click",
    "pyautogui",
]

# Any of these in added lines → integration (lower priority than e2e)
_INTEGRATION_SIGNALS = [
    "supertest",
    "request(app",
    "requests.",
    "httpx.",
    "aiohttp.",
    "urllib.request",
    "testclient",
    "asyncclient",
    "create_engine",
    "sessionmaker",
    "sqlalchemy",
    "django.test",
    "pytest_django",
    "pytest.mark.django_db",
    "pytest.mark.integration",
    "psycopg2",
    "pymongo",
    "motor.",
    "redis.",
    "boto3.",
    "botocore.",
    "grpc.",
]

# Any of these in added lines → unit (Jest/Vitest patterns)
_UNIT_SIGNALS = [
    "jest.mock(",
    "jest.fn(",
    "jest.spyOn(",
    "vi.mock(",
    "vi.fn(",
    "vi.spyOn(",
]


class TestDetector:
    """Detects and classifies test files in a PR's changed file list.

    Classification uses a layered approach (most specific wins):

    1. **Directory path** — ``tests/unit``, ``tests/integration``, ``tests/e2e``
    2. **pytest markers** in added diff lines — ``@pytest.mark.e2e`` etc.
    3. **Framework signals** in added diff lines — imports of e2e / integration libs
    4. **Filename convention** — ``test_*.py`` / ``*_test.py`` → unit (fallback)
    """

    def detect(self, file_changes: list[FileChange]) -> list[TestFile]:
        """Return a ``TestFile`` for every test file touched in the PR."""
        test_files: list[TestFile] = []
        for fc in file_changes:
            if not is_test_file(fc.filename) or is_generated(fc.filename):
                continue
            test_type = self._classify(fc)
            is_new = fc.status == "added"
            lines_added = len(fc.modified_lines) if is_new else fc.additions
            test_files.append(
                TestFile(
                    filename=fc.filename,
                    test_type=test_type,
                    is_new=is_new,
                    lines_added=lines_added,
                )
            )
        return test_files

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify(self, fc: FileChange) -> TestType:
        """Return the most specific TestType for this file."""
        normalized = fc.filename.replace("\\", "/").lower()

        # 1. Directory path (highest priority — most explicit)
        path_type = self._classify_by_path(normalized)
        if path_type is not None:
            return path_type

        # 2. Patch content (framework signals + pytest markers)
        if fc.patch:
            content_type = self._classify_by_content(fc.patch)
            if content_type is not None:
                return content_type

        # 3. Filename convention — default to unit for known test file patterns
        basename = os.path.basename(normalized)
        if (
            basename.startswith("test_")
            or basename.endswith("_test.py")
            or ".test." in basename
            or ".spec." in basename
        ):
            return TestType.unit

        return TestType.unknown

    def _classify_by_path(self, normalized_path: str) -> Optional[TestType]:
        """Return a TestType based on directory names, or None if no match."""
        if "tests/e2e" in normalized_path or "/e2e/" in normalized_path:
            return TestType.e2e
        if "tests/integration" in normalized_path or "/integration/" in normalized_path:
            return TestType.integration
        if "tests/unit" in normalized_path or "/unit/" in normalized_path:
            return TestType.unit
        return None

    def _classify_by_content(self, patch: str) -> Optional[TestType]:
        """Scan added diff lines for framework imports and pytest markers."""
        added_lines = [
            line[1:].lower()
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        if not added_lines:
            return None

        content = "\n".join(added_lines)

        # Explicit pytest markers (very reliable signal)
        if "pytest.mark.e2e" in content:
            return TestType.e2e
        if "pytest.mark.integration" in content:
            return TestType.integration
        if "pytest.mark.unit" in content:
            return TestType.unit

        # Framework-level signals (priority: e2e > integration > unit)
        for signal in _E2E_SIGNALS:
            if signal.lower() in content:
                return TestType.e2e

        for signal in _INTEGRATION_SIGNALS:
            if signal.lower() in content:
                return TestType.integration

        for signal in _UNIT_SIGNALS:
            if signal.lower() in content:
                return TestType.unit

        # describe(/it(/test( with no higher-priority signals → unit
        if "describe(" in content or "\nit(" in content or "\ntest(" in content:
            return TestType.unit

        return None
