from __future__ import annotations

from typing import Optional

from src.models import PRMetrics

_SYSTEM_PROMPT = (
    "You are a Senior Software Quality Architect auditing the testing quality of a Pull Request, "
    "aligned with FloQast's testing standards (Code Coverage & Unit Testing Guide, Testing Guidelines, Mocking in Unit Tests).\n\n"
    "You will receive the actual code diffs: production files that changed and test files that were added or modified.\n\n"
    "Your process:\n"
    "1. Read the production diffs carefully — identify every function, branch, and logic path introduced or modified.\n"
    "2. Read the test diffs carefully — identify exactly what each test exercises and asserts.\n"
    "3. Cross-reference: for each production change, determine whether a test actually exercises that path with meaningful assertions.\n\n"
    "FloQast testing context (use when evaluating):\n"
    "- Test types: True Unit (isolated logic, mocks for deps), Component tests (RTL, one component), Component Integration (RTL, small group), E2E only for critical path.\n"
    "- Prefer Arrange-Act-Assert; one purpose per test; behavior-focused naming (what the system should do, not how).\n"
    "- Mock: external APIs, side effects, React Query / data-fetching when you need to control behavior. Do not mock: React core, routing, UI components under test, pure utilities.\n"
    "- Backend: endpoint tests (one endpoint, mock externals), workflow tests for user journeys; cover positives, negatives (valid/invalid input), and error handling.\n"
    "- Good tests survive refactoring when behavior is unchanged; they do not dictate implementation; a failure should indicate real broken behavior (e.g. broken UI or wrong output).\n\n"
    "Specifically detect:\n"
    "- Superficial tests: tests that exist but do not meaningfully validate the new behavior\n"
    "- Coverage inflation: coverage appears adequate but critical logic paths lack real assertions (FloQast emphasizes meaningful tests over trivial ones that inflate metrics)\n"
    "- Missing behavioral testing: production logic was changed but tests only cover it indirectly or not at all\n"
    "- Mock overuse: too many dependencies are mocked so tests do not validate real system behavior; or mocking of things that should stay real (e.g. React core, components under test)\n"
    "- Test imbalance: significant production logic added with very few meaningful tests\n"
    "- Implementation-detail coupling: tests that would break on refactor even when behavior is unchanged, or that assert on internal calls rather than observable behavior\n"
    "- Risk areas: parts of the change that could cause regressions but appear weakly tested\n\n"
    "Do NOT rely on metric numbers for coverage or test type counts — derive your judgment from reading the actual code.\n"
    "Be direct and critical when necessary. This report is for senior engineers and technical leads."
)


_MAX_PATCH_CHARS = 3000  # per file, to stay within context limits
_MAX_PROD_FILES = 5
_GENERATED_SEGMENTS = {"/generated/", "/__generated__/", "/gen/", "/.generated/"}
_GENERATED_SUFFIXES = (".generated.ts", ".generated.js", ".generated.py", ".g.ts", ".pb.ts", "_pb2.py")
_TEST_PATTERNS = (".test.", ".spec.", "test_", "_test.", "/tests/", "/test/", "/__tests__/")


def _is_generated(filename: str) -> bool:
    n = filename.replace("\\", "/").lower()
    return any(seg in n for seg in _GENERATED_SEGMENTS) or any(n.endswith(s) for s in _GENERATED_SUFFIXES)


def _is_test_file(filename: str) -> bool:
    import os
    base = os.path.basename(filename).lower()
    n = filename.replace("\\", "/").lower()
    return (
        base.startswith("test_") or base.endswith("_test.py")
        or ".test." in base or ".spec." in base
        or "/tests/" in n or "/test/" in n or "/__tests__/" in n
    )


def _format_patch(patch: str, max_chars: int = _MAX_PATCH_CHARS) -> str:
    if len(patch) <= max_chars:
        return patch
    return patch[:max_chars] + "\n...[truncated]"


def _build_prompt(m: PRMetrics) -> str:
    lines: list[str] = []

    # Header
    lines.append(f"PR #{m.pr_number} [{m.repo}]: {m.title}")
    if m.jira_issue:
        ji = m.jira_issue
        lines.append(f"Jira: {ji.key} ({ji.issue_type}) — {ji.summary or ''}")
    lines.append(
        f"Context: {m.production_lines_added} prod lines added, "
        f"{m.test_lines_added} test lines added, "
        f"ratio={m.test_code_ratio:.2f}"
    )
    lines.append("")

    # Production file diffs
    prod_files = [
        fc for fc in m.file_changes
        if not _is_generated(fc.filename) and not _is_test_file(fc.filename)
        and fc.status != "removed"
    ]
    prod_files.sort(key=lambda fc: fc.additions, reverse=True)

    lines.append(f"## Production Files Changed ({len(prod_files)})")
    for fc in prod_files[:_MAX_PROD_FILES]:
        lines.append(f"\n### {fc.filename} [{fc.status}, +{fc.additions} lines]")
        if fc.patch:
            lines.append(f"```diff\n{_format_patch(fc.patch)}\n```")
        else:
            lines.append("_(no diff available)_")

    if len(prod_files) > _MAX_PROD_FILES:
        rest = prod_files[_MAX_PROD_FILES:]
        lines.append("\nAdditional files (no diff): " + ", ".join(fc.filename for fc in rest))

    lines.append("")

    # Test file diffs
    test_files = [
        fc for fc in m.file_changes
        if not _is_generated(fc.filename) and _is_test_file(fc.filename)
    ]

    if not test_files:
        lines.append("## Test Files: none added or modified")
    else:
        lines.append(f"## Test Files Changed ({len(test_files)})")
        for fc in test_files:
            lines.append(f"\n### {fc.filename} [{fc.status}, +{fc.additions} lines]")
            if fc.patch:
                lines.append(f"```diff\n{_format_patch(fc.patch)}\n```")

    lines.append("")
    lines.append(
        "Based on the diffs above, produce a structured markdown audit report with exactly these sections:\n"
        "## Testing Integrity Assessment\n"
        "Evaluate whether the tests truly validate the behavior introduced by the production changes. "
        "Reference specific functions or branches from the diffs.\n\n"
        "## Coverage Quality Assessment\n"
        "Determine whether coverage reflects real testing or artificial inflation. "
        "Call out any logic paths in the production diff that have no corresponding test assertion.\n\n"
        "## Test Design Evaluation\n"
        "Assess whether the tests are meaningful or superficial. "
        "Flag mock overuse, missing edge cases, or assertions that only verify happy paths.\n\n"
        "## Risk Analysis\n"
        "Identify specific areas of the production diff that could cause regressions. "
        "Be concrete — name the file, function, or branch that is at risk.\n\n"
        "## Testing Recommendations\n"
        "Provide 3-5 actionable, specific suggestions to improve test coverage for this PR. "
        "Where relevant, align suggestions with FloQast practices: AAA structure, behavior-focused tests, appropriate mocking (externals vs. core/UI under test), and coverage of positives, negatives, and error paths.\n\n"
        "Ground every finding in the actual diffs. Do not make generic statements."
    )

    return "\n".join(lines)


_COVERAGE_SYSTEM = (
    "You are a code coverage analyst. You must respond with ONLY a single integer between 0 and 100. "
    "No explanation, no text, no punctuation — just the number."
)


def _build_coverage_prompt(m: PRMetrics) -> str:
    """Build a short prompt asking the LLM to estimate a numeric coverage % from the diffs."""
    lines: list[str] = []
    lines.append(
        f"PR #{m.pr_number}: {m.title}\n"
        f"{m.production_lines_added} production lines added, "
        f"{m.test_lines_added} test lines added.\n"
    )

    prod_files = [
        fc for fc in m.file_changes
        if not _is_generated(fc.filename) and not _is_test_file(fc.filename)
        and fc.status != "removed" and fc.patch
    ]
    prod_files.sort(key=lambda fc: fc.additions, reverse=True)

    lines.append("## Production diffs")
    for fc in prod_files[:3]:
        lines.append(f"\n### {fc.filename}")
        lines.append(f"```diff\n{_format_patch(fc.patch, 2000)}\n```")

    test_files = [
        fc for fc in m.file_changes
        if not _is_generated(fc.filename) and _is_test_file(fc.filename) and fc.patch
    ]
    if test_files:
        lines.append("\n## Test diffs")
        for fc in test_files[:3]:
            lines.append(f"\n### {fc.filename}")
            lines.append(f"```diff\n{_format_patch(fc.patch, 2000)}\n```")
    else:
        lines.append("\n## Test diffs\nNone.")

    lines.append(
        "\nEstimate: what percentage (0-100) of the changed production code is exercised "
        "by the test code in this PR? Reply with only the integer."
    )
    return "\n".join(lines)


def _call_openrouter(model: str, api_key: str, messages: list[dict]) -> str:
    """Call OpenRouter's OpenAI-compatible API and return the response text."""
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return response.choices[0].message.content or ""


def _call_ollama(model: str, messages: list[dict]) -> str:
    """Call local Ollama and return the response text."""
    import ollama

    response = ollama.chat(model=model, messages=messages)
    return response["message"]["content"]


_OPENROUTER_FALLBACKS = [
    "google/gemma-3-27b-it:free",   # Google-hosted, not Venice — try first
    "google/gemma-3-12b-it:free",   # Smaller Gemma, same provider
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-coder:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]


def _call_anthropic(messages: list[dict]) -> str:
    """Call Claude via the Anthropic SDK and return the response text."""
    import anthropic

    from src.config import settings

    # Extract system prompt if present as first message
    system = ""
    user_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            user_messages.append(msg)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5",  # fast + cheap for analysis tasks
        max_tokens=4096,
        system=system,
        messages=user_messages,
    )
    return response.content[0].text


def _call_llm(messages: list[dict]) -> str:
    """Route the call to OpenRouter → Anthropic → Ollama (first available wins).

    Priority:
      1. OpenRouter (OPENROUTER_API_KEY) — free models with auto-fallback chain
      2. Anthropic API (ANTHROPIC_API_KEY) — fallback if OpenRouter unavailable
      3. Ollama — local fallback
    """
    from src.config import settings

    if settings.openrouter_api_key:
        api_key = settings.openrouter_api_key
        primary = settings.openrouter_model
        # Build ordered list: configured model first, then fallbacks (deduplicated)
        candidates = [primary] + [m for m in _OPENROUTER_FALLBACKS if m != primary]
        last_err: Exception = RuntimeError("No OpenRouter model available")
        for model in candidates:
            try:
                return _call_openrouter(model, api_key, messages)
            except Exception as e:
                last_err = e
                continue
        raise last_err

    if settings.anthropic_api_key:
        try:
            return _call_anthropic(messages)
        except Exception:
            pass  # No credits or other error — fall through to Ollama

    return _call_ollama(settings.ai_model, messages)


class AIReporter:
    """Generates a free-form markdown analysis of PR testing quality.

    Uses OpenRouter (if ``OPENROUTER_API_KEY`` is set) or Ollama (local fallback).
    Gracefully degrades: returns ``None`` on any failure so the pipeline continues.
    """

    def generate_pr_analysis(self, metrics: PRMetrics) -> Optional[str]:
        """Return a markdown-formatted AI analysis string, or None on any failure."""
        try:
            return _call_llm([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(metrics)},
            ])
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Safe factory
# ---------------------------------------------------------------------------

def try_generate_report(metrics: PRMetrics) -> Optional[str]:
    """Invoke AIReporter if enabled via config; return markdown string or None."""
    try:
        from src.config import settings

        if not getattr(settings, "ai_enabled", False):
            return None
        if not metrics.has_testable_code:
            return None  # Generated/config-only PR — no meaningful analysis possible

        return AIReporter().generate_pr_analysis(metrics)
    except Exception:
        return None


def try_estimate_coverage(metrics: PRMetrics) -> Optional[float]:
    """Ask the LLM to estimate a coverage % from the diffs when CI data is absent.

    Returns a float 0.0–1.0, or None if AI is disabled / Ollama is unavailable.
    Only runs when ``change_coverage == 0.0`` and the PR has testable code.
    """
    try:
        from src.config import settings

        if not getattr(settings, "ai_enabled", False):
            return None
        if not metrics.has_testable_code:
            return None
        if metrics.change_coverage > 0.0:
            return None  # We already have real CI coverage

        import re

        raw = _call_llm([
            {"role": "system", "content": _COVERAGE_SYSTEM},
            {"role": "user", "content": _build_coverage_prompt(metrics)},
        ]).strip()
        # Extract the first integer found in the response
        match = re.search(r"\b(\d{1,3})\b", raw)
        if not match:
            return None
        pct = int(match.group(1))
        pct = max(0, min(100, pct))  # clamp to [0, 100]
        return round(pct / 100, 2)
    except Exception:
        return None
