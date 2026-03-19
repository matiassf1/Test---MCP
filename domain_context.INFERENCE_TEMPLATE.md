# DOMAIN CONTEXT — inference template

Replace placeholders. Keep bullets **keyword-rich** (terms from real code paths and logs).

---

## 1. SYSTEM OVERVIEW

### `<module-or-service-a>`
- Responsibility: `<one line>`

### `<module-or-service-b>`
- Responsibility: `<one line>`

---

## 2. DOMAIN INVARIANTS (CRITICAL RULES)

- `<Concrete API or flow> must never <bad thing>; must always <good thing>.`
- `<Feature flag or config key> must not enable <behavior> without <guard>.`
- `<Data shape or state> must never be mutated without <audit or validation>.`

_(Add 4–10 lines. Use **must never** / **must always**.)_

---

## 3. ROLE MODEL

- **`<RoleName>`** (`<area>`)
  - Can: `<verbs>`
  - Cannot: `<verbs>`
  - Risk: `<testing gap>`

---

## 4. FEATURE FLAGS

- `<flag_key>`
  - Controls: `<behavior>`
  - Risk: `<if wrong>`

---

## 5. CROSS-MODULE DIFFERENCES (CRITICAL)

- **`<package-a>`** vs **`<package-b>`**:
  - `<package-a>`: `<rules>`
  - `<package-b>`: `<different rules>`
- 🚨 Never **import** or **replicate** `<logic>` from `<b>` into `<a>`.

---

## 6. KNOWN FAILURE PATTERNS

### Pattern: `<Short name>`
- Description: `<what breaks>`
- Root cause: `<wrong assumption>`
- Impact: `<blast radius>`
- Example: `<one sentence with real tokens>`

---

## 7. REVIEW HEURISTICS (HOW TO THINK)

- Check if `<question>`?
- Verify `<verification>`?

---

## 8. HIGH-RISK AREAS

- `<path/glob or subsystem>`

---

## 9. CONFIDENCE GUIDELINES

Raise risk if:
- `<condition>`

Lower risk if:
- `<condition>`
