# Authoring `domain_context.md` for heuristic inference

The analyzer matches **production diffs** to bullets in §2, §3, §5, and §6 using **shared vocabulary** (words ≥4 chars, stopwords removed). No product names are hardcoded in code—**your text is the model.**

## §2 Domain invariants (hard signals)

- Use **must not**, **must never**, **always**, **shall not** on lines you want to trigger as **invariant_violation**.
- Repeat **concrete terms** that appear in real code: function names, flag keys, file areas, API nouns.
- One idea per bullet (or short sub-bullets); long prose reduces word overlap with diffs.

**Good (high match chance on signoff PRs):**

```markdown
- `isAuthorizedForSignoff` and strict signoff helpers must never bypass preparer-before-reviewer ordering when `close_entity-settings_separate-strict-sign-off` is enabled.
```

**Weaker (generic, rarely matches diffs):**

```markdown
- Authorization must be correct.
```

## §5 Cross-module (hard)

- Name **both sides** of a contrast (module path segments, package names, or folder names that appear in `git` paths).
- Describe **anti-patterns** with verbs: *import*, *copy*, *replicate*, *port*.
- The diff or changed file paths should share **≥2 significant words** with the bullet for a hit.

## §6 Known failure patterns (hard)

- Start lines with **Pattern:** or use `### Pattern: Name`.
- Body lines should include **distinctive tokens** (error symptoms, bad states, wrong APIs) that might appear in commits.

## §3 Role model

- Role bullets contribute **role tokens** (5+ letter words from the label line). Those tokens in **prod diff** but not **test diff** → `missing_role` (capped).

## §4 Feature flags

- Not scanned by the same overlap rules; use §2/§6 to mention risky flags by **exact key substring**.

## §10 INFERRED FROM CODE (optional, automated)

When you run `build_domain_context` with **`--repo-path`** or **`--repo-signals-json`**, the pipeline appends this section from the **repo analyzer** (structural scan). It is **not** used today by the same overlap heuristics as §2/§5/§6 — it is **context for humans and LLMs** and a bridge toward future auto-invariants.

- Prefer to keep **authoritative** rules in §2–§6; treat §10 as **telemetry from the codebase**.
- If a §10 pattern is important, **copy distilled wording** into §2 or §6 with your vocabulary so diffs match.

## Checklist before shipping a new `domain_context.md`

1. Pick 2–3 recent risky PRs; grep their diffs for words you used in §2/§6.
2. Add missing **must never** lines until at least one bullet would fire on each PR.
3. Keep §5 bullets **asymmetric** (A vs B) with path-like tokens.

See **`domain_context.INFERENCE_TEMPLATE.md`** for an empty skeleton.
