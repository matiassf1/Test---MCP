# DOMAIN CONTEXT

## 0. INITIATIVES & FLAGS (quick reference)

| Shorthand | Name | Epic | Feature flag |
|-----------|------|------|--------------|
| **SIL** | **Single Item Lock** | **CLOSE-9949** | `close_locking_single-item-lock` |
| **SSO** (context) | **Separate Strict Sign-Off** (not enterprise SSO) | **CLOSE-8615** | `close_entity-settings_separate-strict-sign-off` |

---

## 1. SYSTEM OVERVIEW

### apps/JEM-migrations  
- Responsibility: Manage database schema and data migrations impacting journal entries and financial close cycles.

### apps/adhoc-projects_api  
- Responsibility: API backend for adhoc project CRUD with authorization, feature flag checks, and data validation.

### apps/ai-matching-migrations  
- Responsibility: Migrations for AI-driven matching features and account settings updates.

### apps/apollo_email-event-trigger  
- Responsibility: Trigger transactional emails via third-party services based on event workflows.

### apps/autorec-amortization-migrations  
- Responsibility: Migration scripts for amortization and auto-recurring accounting schema/data changes.

### apps/autorec-amortization_main  
- Responsibility: Core amortization and auto-recurring accounting domain logic, APIs, authorization, and helpers.

### Shared Utilities (implicit)  
- Responsibility: Common helpers for feature flags, HTTP, and storage across modules.

---

## 2. DOMAIN INVARIANTS (CRITICAL RULES)

### Authorization model invariants (account / entity / compliance)

- A user’s effective permissions are determined by the combination of **account_role**, **entity_role**, and **compliance_program_role** (when applicable).
- **Permissions MUST NOT** be derived from **UI state alone**.
- **Authorization decisions MUST NOT** rely **only** on **feature flags** (flags may gate features but must not replace role resolution).
- **Sign-off authorization MUST** always respect: **assigned user**, **role permissions**, and **strict sign-off mode** when enabled.
- When **strict sign-off** mode is enabled: users **MUST NOT** sign off items **assigned to others**; **bulk sign-off** may be restricted.
- **Auditor** users **MUST** have **read-only** or **restricted** access and **MUST NOT** perform state mutations (**signoff**, **edits**, **deletes**).

### Signoff + locking invariants

- **Locked** items or folders **MUST NOT** allow **signoff** state mutation.
- **UI restrictions MUST** be **backed by backend enforcement** (disabling controls alone is insufficient).
- **Signoff** state transitions **MUST**: preserve **ordering** (e.g. **preparer** before **reviewer** when strict) and be recorded in **immutable history**.

### Single Item Lock / **SIL** (Epic **CLOSE-9949**) — product / data model

- **Team shorthand: SIL** = **Single Item Lock** = this epic.
- **Feature flag:** `close_locking_single-item-lock` (distinct from strict sign-off epic **CLOSE-8615** / `close_entity-settings_separate-strict-sign-off`).
- **Entity-level setting** (companies schema / `companySettings`): policy enum persisted as **`SingleItemLock`** (or equivalent path), values include at least **`LOCK_ALL`**, **`LOCK_DOCS`**, **`DISABLED`**.
- **Semantics:**
  - **`LOCK_ALL`:** restrict **sign-offs**, **editing**, and **documents** for locked items (full lock UX).
  - **`LOCK_DOCS`:** restrict **modifying documents** only — **not** the same as LOCK_ALL (distinction is **critical** for checklist/table UI).
  - **`DISABLED`:** company turns off single-item lock at the policy control level.
- **Frontend gating (current AC — Kelly / team):** **Sign-offs** and **slideout** are locked **only when both:** (1) the **single-item lock feature flag** is **enabled**, and (2) the company has **`LOCK_ALL`** selected (**not** `LOCK_DOCS`, **not** `DISABLED`).
- **One policy for manual + auto lock:** The **Single Item Lock** setting (**`LOCK_DOCS` / `LOCK_ALL` / `DISABLED`**) drives **both** (a) **manual** item lock (e.g. dropdown in UI) **and** (b) **auto lock** on **signature completion**. There is **not** a separate granular company toggle “only auto lock” vs “only manual” — same enum semantics for both paths.
- **V1 vs V2 on company settings (naming — align code review):**
  - **V1:** **`isSingleTaskAutoLockEnabled`** (legacy auto-lock flag / “old” gate).
  - **V2:** **`singleItemLockEnabled`** + **`SingleItemLock`** enum (**`LOCK_ALL`**, **`LOCK_DOCS`**, **`DISABLED`**).
  - Do **not** treat V2 as merely “V1 renamed”; V2 is the **policy model** for both manual and auto lock behavior once shipped.
- **Code hygiene:** Internal unlock state naming may use **`SIL_UNLOCKED`** (or successor names) after refactors — keep **grep** and constants aligned with PRs (e.g. CLOSE-12509 area).
- **Ship blocker / review heuristic:** Avoid an **early return** in the **V2** code path that runs **only when V1 is enabled** (or bails when V1 is disabled). That pattern “worked during dev” but **fails** after ship when: a **new entity** has **V1 off** and **V2 on**, or **V1 is deprecated** but the early return remains — users would **always** hit the short-circuit and never get V2 behavior. **Prefer independent V2 checks** (flag + `singleItemLockEnabled` + enum) per product AC.
- **Product nuance (policy changes):** If the company sets **`DISABLED`**, the stored enum may **overwrite** the prior value — UX/product want **items already locked** to **retain** effective behavior (**LOCK_ALL** vs **LOCK_DOCS**) rather than retroactively unlocking or guessing wrong. Ideal: **persist lock behavior at time of locking**; if not feasible, fallback is a **single default** for “locked under unknown policy” or keep unlocked — align with PM/engineering.
- **Planned / WIP data shape (dev sync):** Add **`singleItemLockEnabled: boolean`** alongside **`singleItemLock: string`** (enum). Together they express “company has feature off” **without** losing the last enum for **item-level** checks. Example patterns:
  - Company-wide **strict gating:** `singleItemLockEnabled && singleItemLock === 'LOCK_ALL'` (for FE behaviors tied to company toggle).
  - **Item lock UX / unlock:** may need to rely on **per-item lock metadata** and/or **`singleItemLock`** even when `singleItemLockEnabled` is false — **blast radius TBD** (do not assume one client-only check).
- **Unlock in kebab (open question):** When **`DISABLED`** but item **still locked**, whether **Unlock Item** appears — product to confirm; implementation must match AC once decided.
- **Backend / services (blast radius notes):** `companies_schema`, **companies_service**, **company-settings-client**; evaluate **checklist-service**, **reconciliations_core-service**, **checklist_lambdas**, **reconciliations_lambdas** for item lock reads/writes vs new fields.

### Feature flag invariants

- Feature flags **MUST** be evaluated at **runtime** and have **safe defaults** (off unless explicitly enabled).
- Feature flags **MUST NOT** **bypass authorization logic** or introduce **alternative permission paths**.
- Behavior behind flags **MUST** be **consistent across modules** (e.g. **checklist-client** vs **recs-client**).

### Operational invariants (APIs, migrations, data)

- **Authorization:** Every API call must verify user authorization via validated middleware before accessing or modifying any resource; authorization logic must be consistent across modules.
- **State / signoff:** Journal entry and financial close status transitions must follow allowed sequences; signoff and reconciliation histories are immutable; state rollback must be based on recorded signoff history.
- **Feature flags:** No test-only or temporary flags may remain active in production without explicit governance.
- **Data integrity:** Requests must be validated to prevent duplication and invalid formats; middleware must block invalid data before business logic.

### Close UI — checklist signoff (keyword anchor for diffs)

- Changing `isAuthorizedForSignoff`, `signoffAuthorization`, `signaturePermission`, `strictSignoff`, or `getEffectiveStrictFlags` in **checklist-client** must never weaken preparer-before-reviewer ordering or skip feature-flag checks for `close_entity-settings_separate-strict-sign-off` when that flag gates strict behavior.
- `authorization.js` and `signoffs.js` in **ui/checklist-client** must always keep signoff authorization consistent with immutable signoff history rules; must never silently bypass `canSign` or `authorizationManager` expectations in production paths.

---

## 3. ROLE MODEL

### Account roles (formal model)

- **Admin**, **Manager**, **Advanced User**, **Ops User**, **Sys Admin**, **Auditor** (and similar labels in product copy).

### Role hierarchy expectations

- **Admin / Sys Admin:** full configuration and permission control.
- **Manager:** operational control, limited admin capabilities.
- **Advanced User:** standard execution + limited modification.
- **Ops User:** restricted operational capabilities.
- **Auditor:** read-only or restricted access; must not mutate protected state.

### Entity-level roles

- A user may have **different roles per entity**; **entity_role** overrides **account_role** behavior **within that entity**.
- **Critical rule:** permission checks **MUST** resolve **account_role** + **entity_role** + **context** (**module**: Checklist, Reconciliation, etc.).

### Compliance program role

- Where applicable, **compliance_program_role** constrains effective permissions together with account and entity roles.

### Application-specific roles (modules in this repo)

- Project User (adhoc-projects_api)  
  - Can: perform CRUD operations on projects permitted by assigned authorization.  
  - Cannot: bypass authorization or validation checks.  
  - Special behavior: Subject to frequent ACL validations on every action.  
  - Risk: Authorization and validation coverage often incomplete in edge cases.

- Accounting Manager (autorec-amortization_main)  
  - Can: Manage amortization schedules, trigger reconciliations, advance signoff states per rules.  
  - Cannot: Alter signoff history or perform invalid state transitions.  
  - Special behavior: State transitions are audited and must be consistent with domain invariants.  
  - Risk: High risk if state mutation logic is inconsistent or bypassed.

- System Administrator / Migration Operator  
  - Can: Execute database and domain migrations on behalf of system.  
  - Cannot: Violate data integrity or signoff constraints via migration scripts.  
  - Special behavior: Responsible for coordinating migrations preserving cross-domain consistency.  
  - Risk: Migration duplication and uncoordinated changes cause corruption.

---

## 4. FEATURE FLAGS

- adhoc_projects_new_ui  
  - Controls: Whether new UI and API middleware logic for adhoc projects is enabled.  
  - Risk: Partial rollouts cause inconsistent user experiences and possible permission bypass.

- autorec_amortization_enhancements  
  - Controls: Activate new amortization calculation logic and signoff workflows.  
  - Risk: Incomplete flag check could allow mixing old and new state management causing reconciliation errors.

- email_event_trigger_sns_integration  
  - Controls: Whether SNS events trigger email sends in apollo_email-event-trigger.  
  - Risk: Misconfigured flags cause email spam or suppression.

- **close_locking_single-item-lock** (Epic **CLOSE-9949** — Single Item Lock)  
  - Controls: Single-item **lock** UX (sign-off / slideout / docs per **LOCK_ALL** vs **LOCK_DOCS** policy).  
  - **Must** be combined with entity **`LOCK_ALL`** (per current FE AC) for full sign-off + slideout lock — not `LOCK_DOCS` or `DISABLED` alone.  
  - Risk: Flag ON but policy misread → inconsistent lock vs **CLOSE-8615** strict sign-off; cross-client drift on **`SingleItemLock`** enum.

---

## 5. CROSS-MODULE DIFFERENCES (CRITICAL)

### checklist-client vs recs-client (Close UI)

- **checklist-client** (`ui/checklist-client`, `AssigneeSignature`, `ChecklistRow`): must never use **isWorkflow** guards or **workflow**-conditional signoff; **strict** preparer reviewer ordering must always apply; **featureFlag** changes must not copy **recs-client** relaxed paths.
- **recs-client** (`ui/recs-client`): may use **isWorkflow** and relaxed signoff ordering in some flows.
- 🚨 **Anti-pattern:** **import** or **require** from **recs-client** into **checklist-client** for **signoff**, **authorization**, **isAuthorizedForSignoff**, or **strictSignoff** logic — duplicate code with **recs** patterns in **checklist-client** files triggers cross-module review.

### Cross-module authorization (formal)

- **checklist-client** and **recs-client** **MUST NOT** share authorization logic via **copy/paste** or **diverge** in permission enforcement.
- Authorization logic **SHOULD** be **centralized** or shared via **common utilities**.
- **Feature flag** behavior **MUST** be **consistent** across **checklist-client** and **recs-client**.
- **UI** behavior **MUST NOT** **diverge** from **backend** enforcement for the same user/role/entity.

### Single Item Lock — cross-surface parity (CLOSE-9949)

- **`LOCK_ALL`** vs **`LOCK_DOCS`** must be interpreted **identically** in **table UI**, **slideout**, and **services** that enforce item lock (checklist vs reconciliations paths).
- **Company settings** payload (**GET/PATCH** companies_service / settings client) must stay in sync with what **checklist-service** / **reconciliations_core** / **lambdas** use for lock decisions once **`singleItemLockEnabled`** ships.
- Do not conflate **strict sign-off** settings (**CLOSE-8615**) with **single-item lock** policy (**CLOSE-9949**); PRs may touch both — differentiate in review.

---

- apps/autorec-amortization-main vs apps/autorec-amortization-migrations:  
  - autorec-amortization-main: Implements runtime amortization logic, API, and state enforcement.  
  - autorec-amortization-migrations: Only defines data and schema migrations, no runtime logic or API.  

- apps/JEM-migrations vs apps/ai-matching-migrations:  
  - JEM-migrations: Manages migration of journal entries and close process states.  
  - ai-matching-migrations: Focuses on AI matching data migrations unrelated to journal entry state.

⚠️ Never assume logic or state transitions defined in ai-matching-migrations apply to journal entry states managed by JEM-migrations.

- apps/adhoc-projects_api vs apps/autorec-amortization-main:  
  - adhoc-projects_api: Focus on API, authorization, and project lifecycle with feature flags and validation middleware.  
  - autorec-amortization-main: Account management logic with strict signoff state enforcement and reconciliation processes.

⚠️ Authorization and validation mechanisms differ in domain concepts; rules from one module don't implicitly apply to the other.

---

## 6. KNOWN FAILURE PATTERNS

### Pattern: Authorization bypass via UI
- **Description:** UI disables actions but **backend** still allows them.
- **Root cause:** Authorization implemented **only** in **frontend**.
- **Impact:** Users bypass restrictions via **API** or **stale clients**.

### Pattern: Feature flag authorization drift
- **Description:** A **feature flag** changes behavior **inconsistently** across modules.
- **Root cause:** Flag evaluated **differently** in **checklist-client** vs **recs-client** (or other clients).
- **Impact:** Inconsistent **permission enforcement**; audit/compliance risk.

### Pattern: Cross-module authorization inconsistency
- **Description:** Same permission logic implemented **differently** in **checklist-client** and **recs-client**.
- **Root cause:** Lack of **shared authorization** layer.
- **Impact:** **Divergent behavior**; audit and compliance issues.

### Pattern: Signoff state corruption
- **Description:** **Signoff** **order** or **permissions** violated.
- **Root cause:** Missing enforcement of **strict signoff** mode and **role-based sequencing**.
- **Impact:** Invalid **close** process; **audit failure**.

### Pattern: Auditor privilege escalation
- **Description:** **Auditor** can **mutate** state (**signoff**, **edit**, **delete**).
- **Root cause:** Missing **role restriction** checks on server and/or client.
- **Impact:** **Compliance violation**.

### Pattern: Single Item Lock — LOCK_ALL vs LOCK_DOCS confused or overwritten
- **Description:** UI or API treats **`LOCK_DOCS`** like **`LOCK_ALL`** (locks sign-off/slideout incorrectly), or switching company setting to **`DISABLED`** **unlocks** items that should **retain** prior **LOCK_ALL**/**LOCK_DOCS** behavior.
- **Root cause:** Single field **`singleItemLock`** overwritten with **`DISABLED`** with **no** per-item snapshot / no **`singleItemLockEnabled`** companion; FE checks **flag** without **policy** or **policy** without **flag**.
- **Impact:** Wrong table row state, documents editable when they should not be (or vice versa), audit narrative inconsistent with actual lock.
- **Keywords:** `SingleItemLock`, `singleItemLockEnabled`, `LOCK_ALL`, `LOCK_DOCS`, `close_locking_single-item-lock`, **kebab** unlock.

### Pattern: SIL V2 blocked by V1-disabled early return
- **Description:** **V2** Single Item Lock path returns early when **`isSingleTaskAutoLockEnabled`** (V1) is **false**, assuming V1/V2 were mapped as mutually dependent.
- **Root cause:** Transitional dev assumption; V1 and V2 are **not** the same toggle — entities may ship with **V1 off** and **V2 on**, or **V1** may be **removed** later.
- **Impact:** Auto/manual lock under **LOCK_ALL** / **LOCK_DOCS** never runs; silent regression after rollout or deprecation.
- **Keywords:** `isSingleTaskAutoLockEnabled`, `singleItemLockEnabled`, **V2** path, early return.

### Pattern: recs-client logic ported into checklist-client
- Description: **isWorkflow** guards, **recs-client** **import**, relaxed **signoff** **ordering**, **isAuthorizedForSignoff** copied from **recs** into **checklist-client** **authorization.js** **signoffAuthorization.js**.
- Root cause: **checklist-client** treated like **recs-client**; **strictSignoff** and **preparer** **reviewer** rules violated.
- Impact: Wrong **signaturePermission**, **audit** signoff, **CLOSE** checklist compliance failure.
- Example: **`from 'recs-client`** in **checklist-client** or new **!isWorkflow** in **AssigneeSignature** paths.

### Pattern: Duplicated Authorization Logic  
- Description: Authorization checks implemented multiple times independently across modules.  
- Root cause: Lack of centralized authorization helper libraries or shared middleware.  
- Impact: Divergent rule enforcement creating permission leaks or erroneous denials.  
- Example: adhoc-projects_api and autorec-amortization-main validate user rights differently, causing synchronized access issues.

### Pattern: Migration Duplication and Coordination Failures  
- Description: Similar migration scripts repeated independently in multiple modules without coordination.  
- Root cause: Each domain migration manages similar state transitions separately.  
- Impact: Data and state inconsistencies during upgrade/downgrade, with risk of broken reconciliation or close cycles.  
- Example: JEM-migrations and autorec-amortization-migrations applying overlapping state changes causing signoff history mismatches.

### Pattern: Feature Flag Leakage  
- Description: Test or temporary feature flags remain active in production.  
- Root cause: Lack of automated cleanup and environment isolation for flags.  
- Impact: Partial feature rollout causes unpredictable behavior and security bypass.  
- Example: adhoc_projects_new_ui flag left enabled in prod causing incomplete authorization checks.

### Pattern: Validation Gaps Leading to Duplicates  
- Description: Missing or incomplete data validation enabling duplicate project or amortization entries.  
- Root cause: Validation logic residing only in some API layers without enforcement in all entry points.  
- Impact: Data corruption, confusion in reconciliation, audit failures.  
- Example: adhoc-projects_api allowing duplicate project names due to missing middleware checks.

### Pattern: State Transition Inconsistencies  
- Description: Signoff or journal entry states updated out-of-order or lacking recorded history.  
- Root cause: Failure to enforce migration-driven invariant sequences.  
- Impact: Corrupted reconciliation state, irreversible financial close errors.  
- Example: autorec-amortization-main allowing premature reconciliation advance without prior signoff recorded.

---

## 7. REVIEW HEURISTICS (HOW TO THINK)

### Heuristic interpretation rule (reduce false positives)

- **UI-only** changes (rendering, **disabling controls**, labels, **toggle** visibility) **SHOULD NOT** alone be treated as **invariant violations** **UNLESS** they: **remove** an existing **restriction**, **contradict** **backend** enforcement, or **change** **authorization** / **signoff** **API** contracts.
- Prefer asking: did the diff change **guards**, **API** calls, **permission checks**, or **ordering** — not only component props or CSS.

When analyzing a PR:

- Check if logic:  
  - Enforces authorization consistently across all entry points.  
  - Obeys the defined state transition sequences for signoffs and journal entries.

- Always verify:  
  - Feature flags are fully checked before enabling associated behavior, and flags are disabled in prod if test only.  
  - Validation middleware prevents duplicates and malformed requests before reaching domain logic.

- Be suspicious of:  
  - New authorization implementations that duplicate existing logic without reuse.  
  - Migration scripts touching overlapping domain states without coordination.  
  - Feature flag usage that omits runtime condition checks or environment restrictions.
  - PRs that mix **strict sign-off** (**CLOSE-8615** / `close_entity-settings_separate-strict-sign-off`) with **single-item lock** (**CLOSE-9949** / `close_locking_single-item-lock`) without clear separation of **`strictSignOff`** vs **`SingleItemLock`** / **`singleItemLockEnabled`**.

---

## 8. HIGH-RISK AREAS

Focus extra scrutiny on:

- Signoff and reconciliation state mutation functions in autorec-amortization-main.  
- Authorization middleware implementations in adhoc-projects_api and amortization modules.  
- Migration scripts in apps/JEM-migrations and apps/autorec-amortization-migrations for overlapping domain state changes.  
- Feature flag definitions and runtime guards in adhoc-projects_api and autorec-amortization-main.  
- Data validation layers enforcing uniqueness and format in project and amortization APIs.
- **Single Item Lock** (**CLOSE-9949**): companies schema/settings API, **company-settings-client**, checklist vs recs **slideout** and **table** lock behavior; **`LOCK_ALL`** vs **`LOCK_DOCS`** vs policy-to-**DISABLED** transitions; any new **`singleItemLockEnabled`** field rollout.

---

## 9. CONFIDENCE GUIDELINES

Raise risk level if:  
- Authorization logic is independently reimplemented without adequate test coverage or peer review.  
- Migrations affecting the same domain state (e.g., signoff) are uncoordinated or duplicated across modules.  
- Feature flags control critical logic but lack runtime checks or have unclear production status.

Lower risk if:  
- Authorization and validation logic uses shared/reusable middleware or helpers with tests.  
- Migrations are coordinated via shared documentation or override mechanisms ensuring consistent state transitions.  
- Feature flags have explicit environment gating and automated cleanup processes.

---