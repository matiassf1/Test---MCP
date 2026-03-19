# Domain Knowledge Pipeline — Production Design

**Staff+ Systems Design**  
A modular, domain-agnostic pipeline that infers domain knowledge from repositories and feeds it into PR risk analysis.

**Positioning:** This system is **not** “an analyzer of code” — it is a **compiler of organizational knowledge**. Code changes → the system learns; incidents happen → the system gets stricter; teams grow → knowledge is preserved and versioned.

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DOMAIN KNOWLEDGE PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐    ┌─────────────────────┐    ┌──────────────────────────┐   │
│  │   Repo       │    │  Signal              │    │  Scoring & Promotion     │   │
│  │   Analyzer   │───▶│  Classification      │───▶│  (source-weighted,       │   │
│  │   Module     │    │  Layer               │    │   evidence-based)        │   │
│  └──────┬───────┘    └──────────┬──────────┘    └────────────┬─────────────┘   │
│         │                       │                            │                  │
│         │  raw signals          │  typed signals              │  scored +        │
│         │  (snippets, AST)      │  (invariant_candidate,      │  conflict-       │
│         │                       │   guard_pattern, etc.)      │  checked         │
│         │                       │                            │                  │
│         ▼                       ▼                            ▼                  │
│  ┌──────────────┐    ┌─────────────────────┐    ┌──────────────────────────┐   │
│  │  Incident    │    │  Conflict           │    │  Domain Context          │   │
│  │  Ingestion   │───▶│  Detector           │───▶│  Generator               │   │
│  │  (optional)  │    │  (contradictions →  │    │  (evidence + status)      │   │
│  └──────────────┘    │   ambiguous / cap)  │    └────────────┬─────────────┘   │
│                      └──────────┬──────────┘                 │                  │
│                                 │                            │                  │
│                                 ▼                            ▼                  │
│                      ┌─────────────────────┐    ┌──────────────────────────┐   │
│                      │  Versioned Store    │    │  domain_context.json/.md  │   │
│                      │  (domain_context)   │◀───│  (traceable, explainable)  │   │
│                      └──────────┬──────────┘    └──────────────────────────┘   │
└─────────────────────────────────┼──────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PR ANALYSIS / RISK ENGINE                               │
│  • Load domain_context (invariants, failure patterns, roles, flags, conflicts)   │
│  • Precedence: hard domain rules > heuristics > LLM                              │
│  • Behavioral diffing: “before vs after” inferred behavior, not just “touched X”│
│  • Ambiguous / conflicting areas → surface as high risk                          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Data flow (summary):**  
Repo → **Repo Analyzer** → raw signals → **Signal Classification** → typed signals → **Scoring & Promotion** (source-weighted, evidence-based) → **Conflict Detector** (contradictions → lower confidence / status `ambiguous`) → **Domain Context Generator** (with evidence model) → **Versioned Store** → **PR Analysis** (invariant checks + **behavioral diffing** + ambiguous-area warnings). **Incident Ingestion** feeds into Scoring and can create/promote invariants or failure patterns.

---

## 2. Where It Can Break (Design Risks)

### 2.1 Garbage in → Smart garbage out

The pipeline depends on **correct signals** from the repo. But:

- **Tests can be wrong** (assert the wrong behavior, or missing edge cases).
- **Code can contain hacks** (temporary bypasses, tech debt).
- **Comments can lie** (outdated, aspirational, or incorrect “must/never”).

**Risk:** The system infers **incorrect invariants with high confidence** (e.g. “reviewers can sign anytime” because one path allows it and no test contradicts it).

**Mitigations:** Source weighting (Section 5) and **evidence model** (Section 6): confidence is backed by counts (tests, files, negative cases, incidents), so humans can see *why* a rule is trusted. Single-source rules (e.g. one comment, one guard) never reach invariant tier without test or incident backing.

### 2.2 Missing layer: conflict resolution

In large repos you often get:

- **Invariant A:** “Reviewers must wait for preparer.”
- **Invariant B:** “Reviewers can sign anytime.” (e.g. different module or legacy path.)

**Risk:** Without explicit handling, both can be emitted; PR analysis or humans get contradictory guidance.

**Mitigation:** **Conflict Detector** (Section 5.7): detect contradictory rules (same concept, opposite polarity), **lower confidence** for both, mark **status: ambiguous**, and in PR analysis surface: *“This area of the domain is inconsistent → high risk; human judgment required.”*

### 2.3 Intention vs implementation

Example: `if (!isAdmin) return false;`

This could be:

- **Business rule:** “Only admins may do X.”
- **Workaround:** “We don’t support non-admin yet.”
- **Bug:** “Wrong check; should be `isEditor`.”

**Risk:** The pipeline promotes **bugs or workarounds to invariants** (e.g. “must be admin” when the real rule is different).

**Mitigation:** **Source weighting** and **minimum evidence**: single guards stay low (heuristic at most). Invariants require **multiple files**, **tests**, or **incident** backing. Optional: tag signals with `intent_hint: "business_rule" | "workaround" | "unknown"` from comment/test context (e.g. “TODO remove after migration” → don’t promote).

### 2.4 PR analysis is still reactive

Today the design is: *compare PR diff to context → report violations.*

**Gap:** We don’t **simulate the impact** of the change (e.g. “before: reviewer blocked until preparer signed; after: reviewer allowed earlier” as an inferred **behavioral diff**). Doing that would make the system **proactive**: “this PR changes inferred behavior → possible invariant violation.”

**Mitigation:** **Behavioral diffing** (Section 8.4): infer “before” and “after” behavior from the diff (e.g. guard removed, branch added) and compare to invariants, not just “touched auth.”

---

## 3. Repo Analyzer Module

### 3.1 Responsibilities

- **Parse** source code, test files, and comments (no assumptions about language or framework).
- **Detect patterns** via structure and repetition, not business semantics.
- **Extract test intent** from test names and assertions.
- **Emit raw signals** (snippet, location, pattern type, optional AST slice).

### 3.2 Inputs

| Input | Purpose |
|-------|--------|
| File tree | Scope (which paths to scan), module boundaries |
| Source files | AST or line-based parsing |
| Test files | describe/it names, assertion patterns |
| Comments | Must/never/should/required wording |

### 3.3 Pattern Detection (Inference-Only)

All detection is **structural and lexical**; no hardcoded business rules.

| Pattern | How to infer | Example signal |
|--------|----------------|----------------|
| **Guard clause** | Early return/throw with condition; repeated condition shape | `if (!hasPermission) return;` at line X |
| **Repeated condition** | Same condition string or normalized form in N places | `isLocked` in 5 call sites |
| **Feature flag usage** | Identifier/string matching flag-like names (e.g. `useFeatureFlag`, `isEnabled`, `getFlag`) | `featureFlags.close_locking_single_item` |
| **Role/permission check** | Function/variable names containing role/auth/permission/can/hasAccess | `canSign`, `isAuthorizedForSignoff` |
| **Error handling path** | Catch blocks, error branches, throw sites | `catch (AuthError)` → rethrow |
| **Invariant-like comment** | Comments with must/never/should/required + verb | "must not allow signoff when locked" |
| **Test intent** | describe/it strings + assertion type (e.g. throws, equals) | "does not allow signoff when locked" → expect(…).toThrow |

### 3.4 Output: Raw Signals

Each raw signal is a **candidate** only; no meaning is assumed until classification and scoring.

```
RawSignal:
  id: string
  source_file: string
  location: { line_start, line_end?, column? }
  pattern_kind: "guard" | "repeated_condition" | "feature_flag" | "role_check" | "error_path" | "comment_invariant" | "test_assertion"
  snippet: string
  normalized_condition?: string   # for deduping repeated conditions
  language?: string
```

### 3.5 Agnosticism in the Analyzer

- **No domain dictionary:** No list of "signoff", "reconciliation", etc. Terms appear only if they show up in code/comments/tests.
- **No framework assumptions:** Parsers are language-aware (syntax) but not "React" or "REST" specific; patterns are generic (early return, flag read, catch block).
- **Test intent:** Derived from test **structure** (name, assertion type), not from a fixed list of scenarios.

---

## 4. Signal Classification Layer

### 4.1 Purpose

Map raw signals into **typed buckets** used by scoring and by the domain context generator. Still no business interpretation—only structural grouping.

### 4.2 Signal Types

| Type | Description | Source patterns |
|------|-------------|-----------------|
| `invariant_candidate` | Possible "must/never" rule | comment_invariant, test_assertion (negative case), repeated guard with same condition |
| `guard_pattern` | Conditional guard (if/return, if/throw) | guard, repeated_condition |
| `role_pattern` | Role or permission check | role_check |
| `feature_flag_behavior` | Flag read or gate | feature_flag |
| `test_behavior` | Test intent (positive or negative) | test_assertion, describe/it names |
| `failure_pattern_candidate` | Possible known failure mode | test_assertion (expect error), error_path + comment |

### 4.3 Per-Signal Schema

```
ClassifiedSignal:
  raw_signal_id: string
  type: invariant_candidate | guard_pattern | role_pattern | feature_flag_behavior | test_behavior | failure_pattern_candidate
  source: { file, location }
  frequency: int          # same pattern elsewhere in repo
  confidence: float       # 0..1, from scoring
  example_snippet: string
  normalized_key?: string # for grouping (e.g. condition hash, flag name)
```

### 4.4 Classification Rules (Pseudocode)

- **invariant_candidate:** comment contains must/never/should/required OR test name suggests "must not X" / "never Y"; or guard appears in 3+ places with same normalized condition.
- **guard_pattern:** any guard clause; if same condition in 2+ files → also count toward invariant_candidate.
- **role_pattern:** identifier or call matches role/permission/can/isAuthorized pattern.
- **feature_flag_behavior:** identifier or string matches flag naming (e.g. camelCase/snake_case with "flag", "feature", "enabled").
- **test_behavior:** from describe/it; tag as positive (expect success) or negative (expect throw/false).
- **failure_pattern_candidate:** test expects error or comment describes "when X fails" / "prevents Y".

---

## 5. Scoring & Promotion Logic

### 5.1 Goals

- **Promote** high-confidence, high-support signals to **invariant** or **trusted rule**.
- **Keep** medium support as **heuristic** (advisory in PR analysis).
- **Discard** low-support or high-noise signals.

Avoid: noise, overfitting to legacy code, false positives from one-off comments.

### 5.2 Source Weighting (Explicit)

Not all sources of truth are equal. Scoring **must** reflect this explicitly:

| Source | Weight | Rationale |
|--------|--------|-----------|
| **Incident** | Maximum | Prod proved the rule; highest trust. |
| **Test** (especially negative cases) | High | Intent encoded; executable. |
| **Multiple files** (same pattern) | Medium | Consistency across codebase. |
| **Comment** (must/never) | Low | Can be outdated or wrong. |
| **Single guard** (no test, one file) | Very low | Could be workaround or bug. |

Implementation: base score is a **weighted sum** of evidence counts (see 5.3); no single low-weight source can push a rule to invariant by itself.

### 5.3 Scoring Model (Evidence-Based)

Each classified signal gets a **score** and an **evidence** object (see Section 6). Inputs:

| Factor | Weight | How (aligned with source weighting) |
|--------|--------|-------------------------------------|
| **Incident** | Max | Incident linked → floor 0.85; evidence.incidents += 1 |
| **Test presence** | High | Matching test (same condition/flag) → +0.25; evidence.tests += 1 |
| **Negative test cases** | High | Test expects deny/throw → +0.15; evidence.negative_cases += 1 |
| **Frequency** | Medium | Same pattern in N locations → min(1, N/5) * 0.20 |
| **Cross-file** | Medium | Pattern in 2+ files → +0.15; evidence.files = count |
| **Keyword (must/never)** | Low | Comment/source → +0.10 |
| **Single guard, no test** | Very low | Cap contribution at 0.20 so it cannot reach invariant alone |
| **Uniqueness penalty** | Negative | 1 place + no test → −0.20 |
| **Legacy dilution** | Negative | Only under legacy/deprecated paths → cap at 0.5 |

### 5.4 Thresholds

| Bucket | Score range | Use in domain context |
|--------|-------------|------------------------|
| **Invariant** | ≥ 0.85 | Section "Domain Invariants"; hard rule in PR analysis |
| **Heuristic** | 0.5 – 0.84 | Section "Heuristics" or "Review heuristics"; advisory |
| **Discard** | < 0.5 | Not emitted (or stored only for debugging) |

### 5.5 Avoiding Noise and Overfitting

- **Minimum frequency:** Invariant promotion requires pattern in ≥2 distinct files or 1 file + test coverage.
- **No single-comment invariant:** A single "must never X" in a comment is at most heuristic unless backed by test or repetition.
- **Legacy cap:** Paths matching `legacy/`, `deprecated/`, `old/` (configurable) cannot produce invariants.
- **Failure patterns:** Require either (a) test that expects failure, or (b) incident reference, or (c) 2+ mentions in comments/tests.

### 5.6 Pseudocode: Scoring (Evidence + Source Weighting)

```python
def score_signal(signal: ClassifiedSignal, repo_context: RepoContext) -> Tuple[float, Evidence]:
    evidence = Evidence(tests=0, files=0, negative_cases=0, incidents=0)
    base = 0.0

    # Incident (max weight)
    if signal.incident_id:
        evidence.incidents = 1
        base = max(base, 0.85)
    # Test presence (high)
    if repo_context.has_matching_test(signal):
        evidence.tests = repo_context.count_matching_tests(signal)
        base += 0.25
    if repo_context.has_negative_case_test(signal):  # expect throw / expect false
        evidence.negative_cases = repo_context.count_negative_tests(signal)
        base += 0.15
    # Cross-file (medium)
    file_count = repo_context.file_count(signal.normalized_key)
    evidence.files = file_count
    if file_count >= 2:
        base += 0.15
    # Frequency (medium)
    freq = repo_context.count_same_pattern(signal.normalized_key)
    base += min(1.0, freq / 5) * 0.20
    # Keyword (low)
    if signal.has_must_never:
        base += 0.10
    elif signal.has_should_required:
        base += 0.05
    # Single guard, no test → cap so it cannot alone reach invariant
    if freq == 1 and evidence.tests == 0 and not signal.incident_id:
        base -= 0.20
    if repo_context.is_legacy_path(signal.source.file):
        base = min(base, 0.5)
    return (clamp(base, 0, 1), evidence)
```

### 5.7 Conflict Detector (Critical)

**Purpose:** Detect contradictory rules (e.g. “reviewers must wait” vs “reviewers can sign anytime”) so the system does not emit conflicting invariants.

**Behavior:**

1. **Input:** Scored signals (invariant_candidates and promoted invariants) with normalized semantic keys (e.g. same role + action: “reviewer”, “sign”, “before preparer”).
2. **Detection:** Group by (concept, subject); if two rules have **opposite polarity** (must vs can, must_not vs allowed), mark as **conflict**.
3. **Resolution (non-destructive):**
   - **Lower confidence** for both rules (e.g. cap at 0.6 or multiply by 0.7).
   - Set **status: "ambiguous"** on both; emit them still so humans see the tension.
   - Add a **conflict** entry in domain_context: “Area X has inconsistent inferred rules → high risk in PRs touching this area.”
4. **PR impact:** When PR analysis loads context, any finding in an **ambiguous** area surfaces: *“This area has conflicting domain rules; verify intended behavior.”*

**Pseudocode:**

```python
def find_conflicts(scored_signals: List[ScoredSignal]) -> List[Conflict]:
    by_concept = group_by_concept(scored_signals)  # e.g. (reviewer, sign_ordering)
    conflicts = []
    for concept, rules in by_concept.items():
        for a, b in combinations(rules, 2):
            if opposite_polarity(a.statement, b.statement):  # must vs can, never vs allowed
                conflicts.append(Conflict(rule_a=a, rule_b=b, concept=concept))
                a.confidence = min(a.confidence, 0.6)
                b.confidence = min(b.confidence, 0.6)
                a.status = b.status = "ambiguous"
    return conflicts
```

---

## 6. Domain Context Generator

### 6.1 Output Artifact

Two representations of the same content:

- **Machine-readable:** `domain_context.json` (or YAML) for tooling.
- **Human-readable:** `domain_context.md` for review and PR analysis prompts.

### 6.2 Evidence Model (Confidence ≠ Truth)

Replace bare `confidence: 0.91` with **evidence-backed** fields so the system is **explainable, auditable, and debuggable**:

```yaml
# Per-rule (invariant, failure pattern, role, etc.):
confidence: 0.91
evidence:
  tests: 5
  files: 3
  negative_cases: 2
  incidents: 1
status: "trusted" | "heuristic" | "ambiguous"
```

- **confidence:** Single number for thresholds (invariant ≥ 0.85, heuristic 0.5–0.84).
- **evidence:** Counts that **justify** the score; if someone asks “why is this an invariant?”, the answer is in evidence (tests, files, negative_cases, incidents).
- **status:** `ambiguous` when the rule is in a conflict (Conflict Detector); PR analysis treats ambiguous areas as high risk.

### 6.3 Schema (Structured)

```yaml
version: "1.0"
generated_at: ISO8601
source_repo: string
source_commit?: string

invariants:
  - id: string
    statement: string
    source: { file, location, snippet }
    confidence: float
    evidence: { tests: int, files: int, negative_cases: int, incidents: int }
    status: "trusted" | "heuristic" | "ambiguous"
    promoted_from: "invariant_candidate" | "incident"

conflicts:
  - concept: string
    rule_ids: [string, string]
    message: "Inconsistent inferred rules in this area → high risk in PRs."

known_failure_patterns:
  - id: string
    name: string
    description: string
    root_cause: string
    impact: string
    example: string
    sources: [{ file, location }]
    confidence: float
    evidence: { tests, files, negative_cases, incidents }
    status: "trusted" | "heuristic" | "ambiguous"

role_permission_models:
  - role_or_concept: string
    can: [string]
    cannot: [string]
    sources: [{ file, location }]
    confidence: float
    evidence: { tests, files, negative_cases, incidents }

feature_flag_rules:
  - flag_id: string
    behavior: string
    risk_note: string
    sources: [{ file, location }]
    confidence: float
    evidence: { tests, files, negative_cases, incidents }

cross_module_constraints:
  - constraint: string
    modules: [string]
    sources: [{ file, location }]
    confidence: float
    evidence: { tests, files, negative_cases, incidents }

heuristics:
  - statement: string
    source: string
    confidence: float
    evidence: { tests, files, negative_cases, incidents }
```

### 6.4 Traceability and Confidence

- Every rule lists **sources** (file + location), **confidence**, and **evidence**.
- **Examples** are copied from snippets when available.
- **Provenance:** Optional field (e.g. `from incident #PROJ-123` or `from test describe('must not allow...')`).

### 6.5 Markdown Layout (Human-Readable)

Suggested sections, domain-agnostic headings:

1. **System overview** — modules and responsibilities (from file tree + README).
2. **Domain invariants** — critical rules (must/never); traceability + confidence.
3. **Role / permission model** — inferred can/cannot; sources.
4. **Feature flags** — flag id, behavior, risk note.
5. **Cross-module constraints** — differences and anti-patterns between modules.
6. **Known failure patterns** — description, root cause, impact, example.
7. **Review heuristics** — how to think when analyzing a PR (advisory).
8. **High-risk areas** — files/areas with many guards or flags (optional).
9. **Confidence guidelines** — when to raise/lower risk (optional).

---

## 7. Incident Feedback Loop

### 7.1 Ingestion

- **Input:** Incident/bug ticket (e.g. Jira) or structured payload: title, description, root cause, affected area (files/modules), labels.
- **Normalization:** Map to (affected paths, failure description, suggested invariant or failure pattern text).

### 7.2 Conversion

- **To invariant:** If incident describes "X must never happen" and is confirmed (e.g. label `domain-invariant`), add or strengthen an invariant; set confidence to 0.9+ and attach incident id.
- **To failure pattern:** If incident describes a recurring failure mode (e.g. "duplicate auth logic led to bypass"), add or update a known failure pattern; link to affected paths so PR analysis can match diffs in those areas.

### 7.3 Overriding Weaker Signals

- If an incident contradicts a **heuristic** (e.g. "we thought it was optional but prod showed it's required"), **promote** to invariant and mark source = incident.
- If an incident matches an existing **failure_pattern_candidate** with low score, **promote** that pattern and set confidence from incident.
- **Precedence:** Incident-derived invariant > repo-derived invariant > heuristic.

### 7.4 Data Flow (Pseudocode)

```python
def ingest_incident(incident: Incident) -> None:
    pattern = extract_failure_pattern(incident)  # from title + description + root cause
    affected_paths = extract_affected_paths(incident)
    if incident.labels.get("domain-invariant"):
        add_or_strengthen_invariant(pattern.statement, confidence=0.95, source=incident.id)
    add_or_strengthen_failure_pattern(pattern, affected_paths, confidence=0.9, source=incident.id)
```

---

## 8. PR Analysis Integration

### 8.1 How Domain Context Is Used

1. **Load** `domain_context` (invariants, failure patterns, roles, flags, cross-module constraints).
2. **For each changed file/hunk** in the PR:
   - **Invariant check:** Does the diff **remove** or **weaken** a guard that backs an invariant? (e.g. delete `if (!canSign) return` where canSign backs "must not allow signoff without permission".)
   - **Failure pattern check:** Does the diff **introduce** code that matches a known failure pattern (e.g. copy-paste from module A into B where cross-module constraint says "never copy A's auth into B")?
   - **Risky regions:** Diffs touching role checks, feature flag gates, or state transitions get higher scrutiny.
3. **Compare PR behavior vs inferred rules:** e.g. "PR adds a new flag gate; invariant says flags must be checked at runtime → verify the new gate is actually used in the execution path."

### 8.2 Precedence

- **Hard domain rules** (invariants from domain_context) **override** any LLM or heuristic that says "no risk."
- **Heuristics** (review heuristics, high-risk areas) are **advisory**; they don't override invariants.
- **LLM reasoning** is **lowest**; used for narrative and suggestions only when no invariant or strong heuristic applies.

So: **invariants > heuristics > LLM.**

### 8.3 Pseudocode: PR Rule Evaluation

```python
def evaluate_pr_against_domain(pr_diff: Diff, domain_context: DomainContext) -> List[Finding]:
    findings = []
    for hunk in pr_diff.hunks:
        for inv in domain_context.invariants:
            if inv.guard_weakened_or_removed(hunk):  # e.g. deleted line matching guard snippet
                findings.append(HardViolation(inv, hunk))
        for fp in domain_context.known_failure_patterns:
            if fp.matches_diff(hunk):  # e.g. new code similar to fp.example or in fp.modules
                findings.append(FailurePatternMatch(fp, hunk))
        if hunk.touches(domain_context.high_risk_areas):
            findings.append(Advisory("High-risk area", hunk))
        if hunk.touches_ambiguous_area(domain_context.conflicts):
            findings.append(Advisory("Domain rules in this area are inconsistent → high risk", hunk))
    findings.extend(behavioral_diff_findings(pr_diff, domain_context))
    return findings
```

### 8.4 Behavioral Diffing (Beyond “Touched X”)

**Goal:** Not only “this PR touches auth” but **“this PR changes inferred behavior”** — e.g. *before: reviewer blocked until preparer signed; after: reviewer allowed earlier* → **possible invariant violation**.

**Mechanics:**

1. **Before:** From the diff’s removed lines (or parent commit), infer **guards and branches** that were present (e.g. “reviewer blocked when !preparerSigned”).
2. **After:** From the diff’s added lines (or child commit), infer the **new** guards/branches (e.g. guard removed, or new branch “allow reviewer early”).
3. **Compare** to invariants: if an invariant says “reviewer must wait for preparer” and the **after** state allows reviewer earlier, emit: **“PR changes inferred behavior: reviewer no longer blocked until preparer signed → VIOLATES inferred invariant.”**

This makes the system **proactive** and “senior paranoico automático”: it reasons about **effect** of the change, not only about which files were touched.

**Pseudocode:**

```python
def behavioral_diff_findings(pr_diff: Diff, domain_context: DomainContext) -> List[Finding]:
    findings = []
    before_behavior = infer_behavior(pr_diff.removed_lines)   # e.g. { "reviewer_can_sign": "only_after_preparer" }
    after_behavior = infer_behavior(pr_diff.added_lines)    # e.g. { "reviewer_can_sign": "anytime" }
    for inv in domain_context.invariants:
        if inv.describes_behavior(before_behavior) and not inv.describes_behavior(after_behavior):
            findings.append(BehavioralViolation(inv, before_behavior, after_behavior))
    return findings
```

---

## 9. Architecture: Components and Data Flow

### 9.1 Components

| Component | Responsibility |
|-----------|----------------|
| **Repo Analyzer** | Scan repo; parse code/tests/comments; emit raw signals. |
| **Signal Classifier** | Map raw → classified types; compute frequency, normalized keys. |
| **Scoring & Promotion** | Score signals (source-weighted, evidence-based); bucket into invariant / heuristic / discard. |
| **Conflict Detector** | Find contradictory rules; lower confidence, set status `ambiguous`; emit conflict entries. |
| **Domain Context Generator** | Build JSON + Markdown artifact from promoted signals + conflicts; include evidence. |
| **Incident Ingest** | Parse incidents; add/strengthen invariants and failure patterns. |
| **Versioned Store** | Persist `domain_context` by repo + optional commit/tag. |
| **PR Risk Engine** | Load context; invariant + failure-pattern + **behavioral diff** checks; ambiguous-area warnings; precedence. |

### 9.2 Integration with Existing Codebase

Map this design to the current repo:

| Design component | Implementation home | Responsibility |
|------------------|---------------------|----------------|
| **Pipeline orchestration** | `domain_knowledge_pipeline.py` | Single entry: run full pipeline. |
| **Scoring, thresholds, weighting, promotion** | `domain_context_heuristics.py` (or dedicated `scoring.py`) | Scoring rules, thresholds, source weighting, promotion logic. **Do not** mix with extraction (parsing stays in Analyzer). |
| **Extraction / parsing** | Repo Analyzer (new or extended) | Raw signals from code/tests/comments only. |
| **Conflict detection** | New module or subsection in pipeline | `find_conflicts(scored_signals)` before Generator. |
| **PR consumption** | `risk_analyzer.py`, `domain_context_heuristics.py` (existing) | Load context; match diffs to invariants/failure patterns; apply precedence; optional behavioral diff. |

**Suggested `run_pipeline()` shape in `domain_knowledge_pipeline.py`:**

```python
def run_pipeline(repo: str, ...) -> Path:
    signals = repo_analyzer.scan(repo)
    classified = classifier.group(signals)
    scored = scorer.score(classified)  # returns (score, evidence) per signal
    conflicts = conflict_detector.find(scored)
    context = generator.build(scored, conflicts)  # evidence + status in output
    store.save(context)
    return store.path(context)
```

Scoring rules, thresholds, and source weights live in **`domain_context_heuristics.py`** (or a sibling `scoring.py`) so they can be tuned without touching extraction.

### 9.3 Data Flow

1. **Batch (full rebuild):** Repo clone → Repo Analyzer → raw signals → Classifier → Scorer → Generator → write to Store.
2. **Incremental (optional):** On new commit, run Analyzer on changed files only; merge new signals into existing; re-run Scorer + Generator for affected modules.
3. **Incident:** Incident Ingest → update Store (add/promote rules); next PR run uses updated context.
4. **PR:** On PR open/update, Risk Engine loads context from Store → runs evaluation → returns findings.

### 9.4 Storage Strategy

- **Versioned domain context:** One artifact per (repo, branch or tag); or per commit for critical branches.
- **Location:** e.g. `domain_context/<repo_slug>/<ref>/domain_context.json` and `.md`.
- **History:** Keep last N versions or append-only log for audit.

### 9.5 Update Strategy

| Mode | When | Use case |
|------|------|----------|
| **Batch** | Nightly, or on release tag | Full repo re-scan; fresh signals and context. |
| **Incremental** | On merge to main | Only changed files; merge signals; re-score and regenerate. |
| **On-demand** | Manual trigger | After major refactors or when adding incident data. |

---

## 10. Agnosticism Guarantees

### 10.1 No Hardcoded Domain Knowledge

- **No** built-in list of "signoff", "reconciliation", "journal entry", etc. Such terms appear only if they appear in code/comments/tests.
- **No** predefined invariants; every invariant is produced by the pipeline from signals + scoring (or incidents).
- **Keywords** (must, never, should) are **generic**; they don't assume accounting or finance.

### 10.2 No Bias Toward Specific Repos

- **Thresholds** (frequency, score cutoffs) are configurable and same for all repos.
- **Pattern names** (guard, role_check, feature_flag) are structural, not business-named.
- **Module names** in the artifact come from the repo (paths, README), not from a fixed taxonomy.

### 10.3 No Coupling to Frontend/Backend

- **Parsers** are per-language (e.g. JS/TS, Python, Java) but **patterns** are generic (early return, flag read, catch).
- **No** assumption that "API" or "UI" have different rule sets; cross-module constraints are **inferred** from paths and repeated patterns, not from "frontend vs backend."

### 10.4 Where Intelligence Comes From

- **Code:** Guard structure, repeated conditions, flag/role identifiers.
- **Tests:** describe/it names, assertion types (expect throw, expect false).
- **Comments:** must/never/should/required + verb phrase.
- **Incidents:** Explicit promotion or creation of invariants and failure patterns.

---

## 11. Example Artifacts

### 11.1 Example `domain_context` Output (Markdown Snippet)

```markdown
# DOMAIN CONTEXT

## 1. SYSTEM OVERVIEW

### packages/auth
- Responsibility: Access checks and permission helpers (inferred from path and exports).

### packages/api
- Responsibility: Request handling and validation (inferred from path and usage).

---

## 2. DOMAIN INVARIANTS

- **Authorization:** Every access to resource X must be gated by `canAccessResource` (inferred from 4 guard sites + 2 tests).  
  _Sources: packages/auth/guard.js:12, packages/api/handler.js:45; confidence 0.88._

- **Feature flags:** Flag reads must be followed by a branch that disables the feature when false (inferred from 3 sites).  
  _Sources: packages/feature/flags.js; confidence 0.72 (heuristic)._

---

## 6. KNOWN FAILURE PATTERNS

### Pattern: Duplicated guard logic
- Description: Same permission check implemented in two modules with different conditions.
- Root cause: No shared guard helper.
- Impact: One path may allow access when the other denies.
- Example: `canEdit` in packages/editor and packages/admin with different logic.
- _Sources: tests/editor.test.js ("must not allow edit without canEdit"); confidence 0.85._
```

### 11.2 Example Signals Extracted from a Repo

| Type | Source | Snippet | Frequency | Confidence |
|------|--------|---------|-----------|------------|
| guard_pattern | src/auth.js:20 | `if (!user.canSign) return;` | 3 | 0.7 |
| invariant_candidate | tests/signoff.test.js | describe('must not allow sign when locked') | 1 (with test) | 0.75 |
| feature_flag_behavior | src/featureFlags.js:5 | `useFeatureFlag('close_locking_single_item')` | 2 | 0.8 |
| role_pattern | src/assignee.js:10 | `isAuthorizedForSignoff(user, item)` | 4 | 0.85 |
| failure_pattern_candidate | tests/signoff.test.js | expect(() => sign(item)).toThrow() | 2 | 0.78 |

---

## 12. Pseudocode Summary

### 12.1 Signal Extraction

```python
def extract_signals(repo_root: Path, config: AnalyzerConfig) -> List[RawSignal]:
    signals = []
    for path in repo_root.rglob("*"):
        if not is_source_or_test(path): continue
        tree = parse(path)
        for node in tree.walk():
            if is_guard(node):       signals.append(make_signal("guard", node, path))
            if is_flag_read(node):   signals.append(make_signal("feature_flag", node, path))
            if is_role_check(node):  signals.append(make_signal("role_check", node, path))
        for comment in extract_comments(tree):
            if has_invariant_language(comment): signals.append(make_signal("comment_invariant", comment, path))
    for test_path in repo_root.rglob("*test*"):
        for describe, it in parse_test_names(test_path):
            signals.append(make_signal("test_assertion", (describe, it), test_path))
    return signals
```

### 12.2 Scoring (see 5.6)

Already given in section 5.

### 12.3 PR Rule Evaluation (see 8.3)

Already given in section 8.

---

## 13. MVP Executable (Fast Path)

To ship value quickly, a minimal 4-week path:

| Week | Focus | Deliverable |
|------|--------|-------------|
| **1** | Parse tests; extract `it("should ...")` / `describe(...)`; generate **simple invariants** from test names (e.g. “must not allow X” → one invariant per negative test). | List of invariant candidates from test names only. |
| **2** | Add **guards** (if/return, if/throw); **basic scoring** (test + guard in same area → higher score); thresholds for invariant vs heuristic. | domain_context v0 with invariants + heuristics from tests + guards. |
| **3** | Integrate with **PR tool**: load context; emit **warnings** when diff touches files/lines that back an invariant or failure pattern (no behavioral diff yet). | PR comments or report section “Domain risk” with warnings. |
| **4** | **Incident ingestion**: ingest one source (e.g. Jira); map to failure pattern or invariant; promote/override. | Incidents can strengthen or add rules; next pipeline run uses them. |

After that: add Conflict Detector, evidence model in output, and behavioral diffing.

---

## 14. Summary

- **Repo Analyzer** extracts raw, structural signals (guards, flags, role checks, comments, test intent) with **no** business dictionary.
- **Signal Classification** groups them into invariant_candidate, guard_pattern, role_pattern, feature_flag_behavior, test_behavior, failure_pattern_candidate.
- **Scoring & Promotion** is **source-weighted** (incident > test > multi-file > comment > single guard) and **evidence-based** (counts: tests, files, negative_cases, incidents) so confidence is **explainable**.
- **Conflict Detector** finds contradictory rules, lowers confidence, sets **status: ambiguous**; PR analysis surfaces “inconsistent domain → high risk.”
- **Domain Context Generator** produces a versioned artifact (JSON + MD) with **evidence** and **status** per rule; **intention vs implementation** and **garbage-in** risks are mitigated by evidence and weighting.
- **Incident Feedback Loop** ingests incidents and promotes or creates invariants and failure patterns, overriding weaker repo-only signals.
- **PR Analysis** loads context, checks invariant violations and failure-pattern matches, **behavioral diffing** (before/after inferred behavior), and **ambiguous-area** warnings; precedence **invariants > heuristics > LLM**.
- **Agnosticism** is ensured by inferring everything from code/tests/comments/incidents; no hardcoded domain, no repo or stack bias.

The system is a **compiler of organizational knowledge**: code changes → it learns; incidents → it gets stricter; teams grow → knowledge is preserved. The design is **modular** and **evolvable**; evidence and conflict handling make it **explainable** and **debuggable**.
