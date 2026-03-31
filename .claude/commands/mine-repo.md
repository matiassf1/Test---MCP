---
name: "Mine Repo Domain Knowledge"
description: Analyze a locally cloned repo and populate domain_knowledge/ with feature flags, business rules, failure patterns, and cross-module differences
category: Domain
tags: [domain, knowledge, analysis]
---

Analyze a locally cloned repository and extract structured domain knowledge to populate the domain layer.

**Input**: Path to a local repo clone, e.g. `/mine-repo /path/to/close` or `/mine-repo /path/to/checklist-client`

If no path provided, ask the user for it.

---

## Steps

### 1. Read context

Read the following files before starting:
- `domain_context.md` — understand what's already captured; don't duplicate
- `domain_knowledge/feature_flags.md` — existing flags to avoid duplicating
- `domain_knowledge/confluence_rules.md` — existing domain rules

Also read `docs/AUTHORING_DOMAIN_CONTEXT.md` to understand the vocabulary and structure needed.

### 2. Explore the repo

Systematically explore the target repo path. For each area below, use Glob + Read + Grep — do NOT summarize speculatively, only report what you actually find:

**A. Feature Flags — Harness**
- Glob: `**/featureFlag*.ts`, `**/feature-flag*.ts`, `**/constants/flag*.ts`, `**/flags.ts`, `**/featureFlags.ts`
- Grep: pattern `close_[a-z0-9_\-]+` in `.ts`/`.js` files
- Grep: `useFeatureFlag\(`, `getFeatureFlag\(`, `isFeatureFlagEnabled\(`, `variation\(`
- For each flag found: record the key, the file it's defined in, and what behavior it gates (read surrounding code)
- Skip test files (`*.test.ts`, `*.spec.ts`, `__tests__/`)

**B. Feature Flags — tlcModules**
- Grep: `tlcModules\[`, `getTlcModule\(`, `isTlcModuleEnabled\(`
- Read module registry files if found (`**/tlcModules*`, `**/moduleConfig*`, `**/moduleRegistry*`)
- For each module key: record the key and what it enables/disables

**C. Business Rules & Invariants**
- Read authorization middleware/guards: `**/auth*.ts`, `**/guard*.ts`, `**/middleware/auth*`, `**/permission*`
- Read signoff logic: grep `signoff`, `lockItem`, `isLocked`, `canSignoff`, `authorization` in service/controller files
- Read state machine logic: grep `status`, `transition`, `state` in domain service files
- Read validation logic: look for `must`, `cannot`, `forbidden`, `unauthorized` in error messages and comments
- For each rule found: state it as a normative sentence ("X must always...", "Y must never...")

**D. Cross-module Patterns**
- Look for logic duplicated across sibling directories (similar function names, similar file names)
- Look for shared utilities that are copy-pasted instead of imported
- Look for modules that explicitly differ in behavior (comments like "unlike recs, checklist does...")
- Note any `!isWorkflow`, `isWorkflow`, workflow-gating patterns

**E. Failure Patterns**
- Read `CHANGELOG.md`, `HISTORY.md`, or git log messages if accessible
- Grep for `TODO`, `FIXME`, `HACK`, `BUG`, `workaround` comments
- Read any `*.test.ts` files that test edge cases or error conditions — these reveal what breaks
- Look for `try/catch` blocks with meaningful error messages

**F. Config & Environment**
- Read `package.json` for repo name and dependencies
- Read top-level `README.md` for architectural intent
- List top-level directories to understand module structure

### 3. Produce structured output

Write the results to these files (append/merge — don't overwrite existing content):

#### `domain_knowledge/feature_flags.md`

```markdown
## Harness Flags

- `close_<key>`: owning module: `<file path>`; controls: <what behavior it gates>; seen in: <N> files
  - Default: <on/off/unknown>
  - Risk: <what breaks if partially implemented or missing tests>

## tlcModules

- `<module-key>`: owning module: `<file path>`; enables: <what feature>
```

#### `domain_knowledge/repo_rules/<repo-name>.md`

Create one file per repo with this structure:

```markdown
# Domain Rules — <repo-name>

Mined: <date> from local clone at <path>

## Business Invariants

- <Rule stated as "X must always/never Y">
- ...

## Authorization Rules

- <Who can do what, under what conditions>
- ...

## State Transition Rules

- <What transitions are valid, what guards exist>
- ...

## Cross-module Notes

- <Module A> vs <Module B>: <what differs>
- Shared logic that appears duplicated: <what and where>

## Failure Patterns (from code signals)

### Pattern: <Name>
- Description: <what breaks>
- Root cause: <domain assumption violated>
- Signal: <where found in code — file, function, comment>

## Feature Flag Notes

- `<flag-key>` controls: <behavior>
  - Found in: <file paths>
  - Test coverage: <yes/no/partial>
```

### 4. Enrich domain_context.md

After writing the files above, run the domain context enricher:

```bash
cd <project root>
.venv/Scripts/python -c "
from src.domain_context_enricher import DomainContextEnricher
DomainContextEnricher().enrich_feature_flags()
print('Feature flags enriched in domain_context.md')
"
```

Then manually review:
- Do any of the new invariants found belong in `domain_context.md §2`?
- Do any failure patterns complement what's in `§6`?
- Are there cross-module differences to add to `§5`?

For each one that belongs in `§2`, `§5`, or `§6` — ask the user: "I found this rule in `<file>`: `<rule>`. Should I add it to §2 Domain Invariants?"

### 5. Report summary

Show a concise summary:
```
## Mining Complete — <repo-name>

**Harness flags found:** N
**tlcModules found:** N
**Business invariants extracted:** N
**Failure patterns detected:** N
**Files written:**
- domain_knowledge/feature_flags.md (updated)
- domain_knowledge/repo_rules/<repo-name>.md (created)

**Suggested additions to domain_context.md:**
- §2: <rule 1>
- §6: <pattern 1>
(Review and confirm with user before writing)
```

---

## Running in Cursor

Cursor does **not** automatically read `.claude/commands/` — you need to paste this prompt manually.

### Setup

1. Open the cloned repo as a secondary workspace:
   **File → Add Folder to Workspace…** → select the cloned repo root (e.g. `/path/to/close`)

2. In Cursor's chat, reference this file as context:
   ```
   @file:/path/to/testing-internal-tool/.claude/commands/mine-repo.md
   ```
   Then add the repo path argument:
   ```
   /mine-repo /path/to/close
   ```
   Or paste the full prompt content directly and specify the path.

### Output paths

Write output files to the **testing-internal-tool** project, not the cloned repo:

- `domain_knowledge/feature_flags.md` → `testing-internal-tool/domain_knowledge/feature_flags.md`
- `domain_knowledge/repo_rules/<repo-name>.md` → `testing-internal-tool/domain_knowledge/repo_rules/<repo-name>.md`

Ask Cursor to write these files using absolute paths to the testing-internal-tool directory.

### Step 4 — DomainContextEnricher

Skip the Python execution step in Cursor (Step 4 of the command). After Cursor finishes writing the output files, run the enricher manually from the `testing-internal-tool` project:

```bash
cd /path/to/testing-internal-tool
.venv/Scripts/python -c "
from src.domain_context_enricher import DomainContextEnricher
DomainContextEnricher().enrich()
print('Domain context enriched.')
"
```

On Mac/Linux use `.venv/bin/python` instead of `.venv/Scripts/python`.

---

## Guardrails

- Only report what you actually found in the code — never fabricate rules
- When uncertain about a rule's intent, quote the actual code and ask the user
- Skip test files for flag/rule extraction (but DO read them for failure pattern signals)
- If a flag or rule already exists in `domain_knowledge/feature_flags.md` or `domain_context.md`, note "already captured" and skip
- Keep each invariant as a single actionable sentence — no prose paragraphs
- If the repo is very large (>500 files), focus on: auth/, middleware/, services/, controllers/, signoff*, lock*, permission* paths first
