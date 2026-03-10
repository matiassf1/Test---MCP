from __future__ import annotations

from typing import Optional

from src.file_classification import is_generated as _is_generated, is_test_file as _is_test_file
from src.models import PRMetrics

# PR Testing Audit – system prompt (definitive structure: Summary, Metrics, Integrity, Coverage, Design, Risk, Recommendations)
_SYSTEM_PROMPT = """\
You are a senior engineer auditing the **testing quality** of a GitHub pull request. Your output is a structured markdown report consumed by tech leads and engineers. Be **technical, direct, and critical when justified**. Do not be generic; ground every claim in the PR diff, the test files, and the repo's actual testing stack.

---

## Context

- **Input**: PR metadata (number, author, branch, ticket), file diff (production + test changes), and optional metrics (lines changed, test/code ratio, coverage if available).
- **Output**: A single markdown report with fixed sections, tables, and 3–5 concrete recommendations. Language: **English** (or Spanish if the team explicitly requests it for this run).
- **Repo**: This codebase uses **Jest + Enzyme (shallow/mount)** as the standard. Some areas use **legacy Mocha**. There is **no React Testing Library (RTL) or userEvent** by default. Do **not** recommend migrating to RTL or adding E2E tests unless the ticket or PR description explicitly asks for it. Recommendations must be **implementable within one day** (no "refactor the entire test suite").
- **Coverage target**: **~90% for new code** (diff coverage). For business-critical logic (selectors, auth, state shape) aim for **~95%**. If the repo or ticket states a different target, use that instead.

---

## Report structure (mandatory)

Produce exactly these sections in order. Use the headings below.

### 1. Summary (2–3 sentences)

State whether the PR's tests are sufficient for merge, what is already well covered, and the main gap(s). Include the **Testing Quality Score (0–10)** and, if available, **coverage** (mechanic or AI-estimated).

### 2. Metrics table

If you have numeric inputs, render a table. **Test/Code ratio** = (test lines added or modified) / (production lines added or modified). Show a value ≥ 1 when there are more test lines than production lines. Example:

| Metric | Value |
|--------|--------|
| **Testing Quality Score** | X / 10 (Poor / Fair / Good / Excellent) |
| Test / Code ratio | X.XX |
| Coverage (if available) | X% (or "N/A – no CI data") |
| Tests added / modified | N unit, M integration (if applicable) |

### 3. Testing Integrity Assessment

- Which **behaviours and code paths** from the **production diff** are actually exercised by tests? Reference **files and function names** (e.g. `selectLockStatus` in `selectors/index.js`, `mapStateToProps` in `ReconciliationDocumentsButtonContainer.js`).
- Call out **gaps**: logic or branches in the diff that have no corresponding test (e.g. "branch when `singleItemLockEnabled` is true and `lockStatus` is missing is not asserted"). **Do not claim a gap** for something that is already covered: cross-check the test file content and described behaviours (e.g. if a test "simulates close button click and asserts popover open state", do not say "tests do not simulate user interactions when the popover closes").
- Be specific: "tests check that the close button exists" is weak; "tests assert that clicking the close button sets popover `open` to false" is strong.
- **Limit scope**: Only comment on **code that changed in the PR**. Do not demand tests for unchanged or generated code (e.g. protobuf, codegen). If the PR only adds dependencies that are already tested elsewhere, state **"No new tests required for this change"** and do **not** lower the score for that reason.

### 4. Coverage Quality Assessment

- For the **changed production files**, which branches, edge cases, or error paths are covered vs uncovered?
- If coverage data is missing, say so and base the assessment on **code reading** (e.g. "the selector's null/undefined branches are tested; the empty-object branch is not").
- Again, **reference the diff**: tie each gap to a file/function or line range when possible.

### 5. Test Design Evaluation

- **Positives**: Structure (Arrange–Act–Assert), use of mocks, consistency with the rest of the repo.
- **Issues**: Over-mocking that hides bugs, missing edge cases, assertions on implementation details instead of behaviour, or tests that would be better as integration tests.
- **Component vs container**: For props that come from Redux (e.g. `isRecLocked`), recommend tests in the **component** only for prop values and rendered behaviour; recommend tests in the **container** (`mapStateToProps`, selectors) for state shape and selector/output.
- **Stack**: Assume **Jest + Enzyme**. Do not recommend RTL, userEvent, or E2E unless the ticket or PR explicitly requests them. If a recommendation would require a new testing stack, label it as **out of scope for this PR** or **follow-up**.

### 6. Risk Analysis

- List **2–4 concrete risks** if tests are missing or weak (e.g. "Popover open state is not reset on close; regressions likely if refactored", "Selector returns wrong shape when `lockStatus` is malformed").
- Tie each risk to a **code path or dependency** from the diff.

### 7. Testing Recommendations

- Provide **3–5 actionable items** only. Each must be **concrete** (e.g. "Add a test in `lockStatus.test.js`: when `state.reconciliations[id].lockStatus` is `{}`, assert result is `{ isLocked: false }`").
- **Avoid duplicate recommendations:** When suggesting a new test, do not assume the scenario is missing. For any behaviour that might already be covered by the PR's test files, phrase the recommendation as a check: e.g. "Verify that [behaviour] is covered; if not, add…" or "If not already tested, add…". Avoid unconditional "Add a test for [X]" unless the diff and test list clearly show that [X] is absent.
- **Prioritise**: Put first the ones that unblock merge or hit coverage targets; mark optional ones (e.g. "Nice-to-have: add a test for getTooltipText branches if using full DOM render").
- **Feasibility**: Every recommendation must be doable within **one day** with the current stack (Jest + Enzyme). If the only way to cover something is RTL or E2E, say so and mark it as **follow-up** unless the ticket asks for it.
- **Legacy**: If the team policy is "do not touch legacy tests" or "only suggest tests for new code", do not recommend changing or adding tests in legacy (e.g. Mocha) areas unless the PR already touches them.

---

## Scoring (0–10)

- Use a **single** Testing Quality Score (0–10). If the pipeline provides a precomputed score (e.g. 7.51), **use that value** in the metrics table and in the Summary. Do **not** output a different score (e.g. 8) in the narrative unless you explicitly label it as "Auditor override" and explain why; otherwise the report contradicts the tool.
- **0–3 (Poor)**: Critical paths untested; no tests for new logic; high regression risk.
- **4–5 (Fair)**: Some coverage but clear gaps (e.g. only happy path; no edge cases or container wiring).
- **6–7 (Good)**: Main behaviours and branches covered; a few edge cases or integration points missing.
- **8–9 (Very good)**: Strong coverage of diff; minor gaps or design improvements only.
- **10 (Excellent)**: Diff fully covered; design aligned with repo; no unnecessary recommendations.

Do **not** penalise when the PR only adds already-tested dependencies or generated code; in that case state "No new tests required" and score accordingly (e.g. N/A or high if nothing testable was added).

---

## Formatting

- Use **tables** for metrics and, if useful, file-level coverage.
- Use **bullets** for recommendations, risks, and gaps.
- When citing code, use **backticks** for file names, function names, and props (e.g. `mapStateToProps`, `selectLockStatus`).
- Keep paragraphs short (2–4 sentences). Prefer lists over long prose.

---

## Output

Emit **only** the markdown report, with no preamble or meta-commentary. The first line must be a top-level heading (e.g. `# PR Testing Audit Report`) so the result can be embedded or saved as a single document.\
"""


_MAX_PATCH_CHARS = 3000  # per file, to stay within context limits
_MAX_PROD_FILES = 5


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
    if m.has_testable_code:
        lines.append(
            f"Precomputed Testing Quality Score: {m.testing_quality_score:.2f} — use this value in the metrics table and in the Summary; do not output a different score unless you label it as 'Auditor override' and explain why."
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
        "Based on the diffs and context above, produce the full PR Testing Audit Report.\n\n"
        "Use exactly these section headings in order:\n"
        "1. **Summary** (2–3 sentences; include Testing Quality Score 0–10 and coverage if available)\n"
        "2. **Metrics table** (Quality Score, Test/Code ratio, Coverage, Tests added)\n"
        "3. **Testing Integrity Assessment**\n"
        "4. **Coverage Quality Assessment**\n"
        "5. **Test Design Evaluation**\n"
        "6. **Risk Analysis**\n"
        "7. **Testing Recommendations** (3–5 concrete, prioritised, doable in one day)\n\n"
        "Start the report with a top-level heading: `# PR Testing Audit Report`. Emit only the markdown; no preamble or commentary. "
        "Ground every finding in the actual diffs; reference files and function names."
    )

    return "\n".join(lines)


# This prompt drives llm_estimated_coverage (0-100), which feeds testing_quality_score when
# change_coverage is 0. The narrative report uses _SYSTEM_PROMPT above and does not affect the score.
_COVERAGE_SYSTEM = (
    "You are a code coverage analyst for FloQast. Estimate what percentage (0-100) of the "
    "changed production code is meaningfully exercised by tests — not just touched, but with "
    "real assertions and behavior validation (per FloQast: meaningful tests over coverage inflation). "
    "FloQast bar: 90% for new code (diff coverage), 95% for business-critical logic. Consider: True Unit / Component (RTL) / integration tests; "
    "avoid counting superficial or implementation-coupled tests. If the PR only adds a well-tested dependency "
    "or only touches auto-generated code (protobuf, codegen), respond 100 (no new tests required). "
    "Respond with ONLY a single integer 0-100. No other text."
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
        "\nEstimate: what percentage (0-100) of the changed production code is meaningfully "
        "exercised by tests (real assertions, behavior validation; not superficial coverage)? "
        "If the change only adds a well-tested dependency or only touches auto-generated code, reply 100. "
        "Reply with only the integer."
    )
    return "\n".join(lines)


# Prompt for OpenRouter-based 0–10 quality score (FloQast-aligned); used when Anthropic is not set.
_QUALITY_SCORE_SYSTEM = (
    "You are a senior engineer reviewing PR test quality (FloQast standards; fq-skills: floqast-testing-standards, react-testing-standards). "
    "Return ONLY valid JSON with one key: {\"ai_quality_score\": <0-10>}. "
    "Score: 0-3 critical gaps, 4-5 major paths missing, 6-7 minor gaps, 8-9 good, 10 comprehensive. "
    "Consider: 90% bar for new code, 95% for business-critical; meaningful tests; AAA; naming \"should [behavior] when [condition]\"; one behavior per test; "
    "for React tests: getByRole/getByLabelText over getByTestId, userEvent over fireEvent, no implementation-detail testing. "
    "If the PR only consumes a well-tested library (no new logic) or only touches auto-generated code, give 8-10 (no new tests required)."
)


def _build_quality_score_prompt(m: PRMetrics) -> str:
    """Minimal context for the quality-score LLM call (OpenRouter path)."""
    lines = [
        f"PR #{m.pr_number} [{m.repo}]: {m.title}",
        f"Prod lines added: {m.production_lines_added}, test lines added: {m.test_lines_added}, ratio: {m.test_code_ratio:.2f}.",
    ]
    prod = [fc for fc in m.file_changes if not _is_generated(fc.filename) and not _is_test_file(fc.filename) and fc.status != "removed"]
    test_f = [fc for fc in m.file_changes if not _is_generated(fc.filename) and _is_test_file(fc.filename)]
    prod.sort(key=lambda fc: fc.additions, reverse=True)
    for fc in prod[:3]:
        lines.append(f"  {fc.filename} [+{fc.additions}]")
    for fc in test_f[:3]:
        lines.append(f"  {fc.filename} [+{fc.additions}]")
    lines.append("Return only JSON: {\"ai_quality_score\": <0-10>}.")
    return "\n".join(lines)


def try_quality_score_openrouter(metrics: PRMetrics) -> Optional[float]:
    """Get 0–10 quality score via OpenRouter/Ollama (same _call_llm as report/coverage). Use when Anthropic is not set."""
    try:
        if not _is_ai_enabled() or not metrics.has_testable_code:
            return None
        raw = _call_llm([
            {"role": "system", "content": _QUALITY_SCORE_SYSTEM},
            {"role": "user", "content": _build_quality_score_prompt(metrics)},
        ]).strip()
        import json
        # Allow JSON wrapped in markdown code block
        if "```" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]
        data = json.loads(raw)
        score = data.get("ai_quality_score")
        if score is None:
            return None
        s = float(score)
        return round(min(max(s, 0.0), 10.0), 2)
    except Exception:
        return None


def _is_429(e: Exception) -> bool:
    """True if the exception is a 429 Too Many Requests from the API."""
    if getattr(e, "status_code", None) == 429:
        return True
    if "429" in str(e) or "too many requests" in str(e).lower():
        return True
    resp = getattr(e, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 429:
        return True
    return False


def _call_openai(model: str, api_key: str, messages: list[dict]) -> str:
    """Call OpenAI API (api.openai.com) — e.g. gpt-4o-mini; same client, no base_url."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, max_retries=0)
    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content or ""


def _call_openrouter(model: str, api_key: str, messages: list[dict]) -> str:
    """Call OpenRouter's OpenAI-compatible API; no built-in retries; on 429 wait then retry once."""
    import time
    from openai import OpenAI

    from src.config import settings

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        max_retries=0,
    )
    backoff_s = max(0.0, getattr(settings, "openrouter_429_backoff_seconds", 60.0))

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            if attempt == 0 and _is_429(e) and backoff_s > 0:
                time.sleep(backoff_s)
                continue
            raise
    return ""


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
    """Route the call to OpenAI → OpenRouter → Anthropic → Ollama (first available wins).

    Priority:
      1. OpenAI (OPENAI_API_KEY) — e.g. gpt-4o-mini, good rate limits
      2. OpenRouter (OPENROUTER_API_KEY) — free models with auto-fallback chain
      3. Anthropic API (ANTHROPIC_API_KEY)
      4. Ollama — local fallback

    OpenRouter path: delay before/after each call to avoid 429. OpenAI direct has no extra delay.
    """
    import time
    from src.config import settings

    if settings.openai_api_key:
        try:
            return _call_openai(
                settings.openai_model,
                settings.openai_api_key,
                messages,
            )
        except Exception:
            pass

    if settings.openrouter_api_key:
        delay = max(0.0, getattr(settings, "openrouter_delay_seconds", 5.0))
        api_key = settings.openrouter_api_key
        primary = settings.openrouter_model
        candidates = [primary] + [m for m in _OPENROUTER_FALLBACKS if m != primary]
        last_err: Exception = RuntimeError("No OpenRouter model available")
        for model in candidates:
            try:
                if delay > 0:
                    time.sleep(delay)
                out = _call_openrouter(model, api_key, messages)
                if delay > 0:
                    time.sleep(delay)
                return out
            except Exception as e:
                last_err = e
                if delay > 0:
                    time.sleep(delay)
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

def _is_ai_enabled() -> bool:
    """True when AI is available: AI_ENABLED or OPENAI_API_KEY or OPENROUTER_API_KEY set."""
    try:
        from src.config import settings
        return bool(
            getattr(settings, "ai_enabled", False)
            or getattr(settings, "openai_api_key", "")
            or getattr(settings, "openrouter_api_key", "")
        )
    except Exception:
        return False


def try_generate_report(metrics: PRMetrics) -> Optional[str]:
    """Invoke AIReporter if enabled via config (AI_ENABLED or OPENROUTER_API_KEY); return markdown or None."""
    try:
        if not _is_ai_enabled():
            return None
        if not metrics.has_testable_code:
            return None  # Generated/config-only PR — no meaningful analysis possible

        return AIReporter().generate_pr_analysis(metrics)
    except Exception:
        return None


def try_estimate_coverage(metrics: PRMetrics) -> Optional[float]:
    """Ask the LLM to estimate a coverage % from the diffs when CI data is absent.

    Returns a float 0.0–1.0, or None if AI is disabled / unavailable.
    Runs when OPENROUTER_API_KEY (or AI_ENABLED) is set and ``change_coverage == 0.0``.
    """
    try:
        if not _is_ai_enabled():
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
