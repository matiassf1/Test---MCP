# Alignment with fq-skills (FloQastInc/fq-skills)

The pr-analysis MCP server’s AI prompts are aligned with two skills from the **fq-skills** repo:

- **floqast-testing-standards** — General FloQast testing: 80%+ coverage for new code, test philosophy, unit/integration patterns, naming, TestDataManager, mocking.
- **react-testing-standards** — React Testing Library: test like a user, query priority (getByRole, getByLabelText), userEvent, MSW, no implementation-detail testing.

## What we use from each skill

### From floqast-testing-standards

- **Coverage bar**: 80% for new code (diff coverage); 90% business logic, 95% utilities, 70% controllers. Prompts tell the LLM to use this bar when estimating coverage and scoring.
- **Naming**: Tests should follow “should [expected behavior] when [condition]”; one behavior per test (if a test name uses “and”, consider splitting).
- **Test types**: True Unit, Component (RTL), Component Integration, E2E for critical path.
- **Mocking**: Mock externals; prefer real internal modules when practical.
- **Exceptions**: No penalty when the PR only adds a well-tested dependency or touches auto-generated code (protobuf, codegen).

### From react-testing-standards

- **Query priority**: Prefer `getByRole`, `getByLabelText` over `getByTestId` (testId as last resort). The LLM is instructed to flag React tests that overuse test IDs.
- **Interactions**: Prefer `userEvent` over `fireEvent` for user actions.
- **Behavior vs implementation**: Test user-visible behavior and rendered output; do not test internal state, instance methods, or shallow implementation details.

## Where it’s applied

- **`src/ai_reporter.py`**: Narrative report system prompt (`_SYSTEM_PROMPT`), coverage-estimate prompt (`_COVERAGE_SYSTEM`), and OpenRouter quality-score prompt (`_QUALITY_SCORE_SYSTEM`) all reference these standards and include the criteria above.
- **`src/ai_analyzer.py`**: Claude-based qualitative analyzer (`_SYSTEM_PROMPT`) uses the same coverage bar, naming convention, and React/RTL criteria.

The skills themselves live in **FloQastInc/fq-skills** (`skills/floqast-testing-standards/SKILL.md`, `skills/react-testing-standards/SKILL.md`). This doc summarizes how we incorporate them into the pr-analysis server; for full detail, see those SKILL.md files.
