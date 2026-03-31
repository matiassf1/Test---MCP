# DOMAIN CONTEXT

## 1. SYSTEM OVERVIEW

### Modules
- apps/JEM-migrations
  - Responsibility: Backend database schema and data migrations focused on journal entry accounting domain with state updates tied to signoffs.
- apps/adhoc-projects_api
  - Responsibility: API service managing ad-hoc project lifecycle, with strong authorization and feature flag driven logic.
- apps/ai-matching-migrations
  - Responsibility: Database migrations for AI-specific account settings and deduplication in matching domain.
- apps/apollo_email-event-trigger
  - Responsibility: Handles inbound email event processing via Mandrill, SES, SNS integrations, separate from core business workflows.
- apps/autorec-amortization-migrations
  - Responsibility: Schema and data migrations specific to auto-reconciliation and amortization financial modules.
- apps/autorec-amortization_main
  - Responsibility: Core business logic for financial auto-reconciliation, amortization processing, configuration, and journal entry handling.

---

## 2. DOMAIN INVARIANTS (CRITICAL RULES)

### Checklist Signoff and Workflow Integrity:
- Signoffs must be applied sequentially: Preparers first, Reviewers only after Preparers complete.
- Only authorized roles may create or remove signoffs; no cross-role overrides except Admin/Manager.
- Signoff removal permissions strictly enforced: prep and reviewer remove own; admins override.
- Signed checklist items lock editing until signoff removal.
- Signoff creation/removal requests must be idempotent with appropriate HTTP verb usage.
- Feature flags governing migrations must preserve signoff state integrity regardless of deployment route (Lambda or ECS).

### Replication Workflow Guarantees:
- Replication batches enforced exactly-once via Step Functions; idempotent and ordered.
- Monthly scheduled triggers maintain chronological replication order.
- Folder/template/checklist creation order preserved for data consistency.
- Undo operations permitted, updating replication states without data corruption.
- Concurrency controls prevent duplicate or overlapping data processing during replication.

### Export Workflow Safeguards:
- Exports trigger asynchronous jobs for Excel generation and S3 upload; synchronous waits forbidden.
- Notifications dispatched via WebSocket/email only after export completion and upload.
- Only one active export per user/entity at a time; later requests either queued or prior exports cancelled.
- Audit logs and events emitted for every export request, progress, and completion.

---

## 3. ROLE MODEL

### Checklist Domain
- Preparer
  - Can: create/remove own signoffs; edit checklist pre-signoff.
  - Cannot: override Reviewer signoffs or edit locked items.
- Reviewer
  - Can: create/remove own signoffs only after Preparer signoff; review progress.
  - Cannot: signoff before Prep; override Admin removals.
- Admin/Manager
  - Can: override any signoff restrictions; remove any signoff; access audit trails.
- Client User
  - Can: read-only checklist and status views.
  - Cannot: create or remove signoffs; edit checklists.

### Replication Domain
- Replication Worker
  - Can: execute replication pipeline steps with scoped collection access.
- Replication Manager
  - Can: initiate replication batches; monitor processing queues.
- Reviewer
  - Can: validate and approve replication completions.
- System Roles (Automated Lambdas/Services)
  - Can: operate on specific DB collections and storage per least privilege.

### Export Domain
- Export Requester
  - Can: trigger export jobs; only one active per entity.
- Export Processor
  - Can: asynchronously generate and upload export files.
- Export Notifier
  - Can: notify users post-export completion with results.

---

## 4. FEATURE FLAGS

- MigrationSignoffConsistency
  - Controls: Enables enforced signoff state preservation during migrations on both Lambda and ECS routes.
  - Risk: Partial implementation leads to signoff state mismatches causing checklist inconsistencies.
- AdhocProjectAuthToggle
  - Controls: Toggles enhanced authorization middleware in adhoc-projects_api.
  - Risk: Partial coverage risks unauthorized operations or blocked valid users.
- AI_Matching_Dedupe_Enable
  - Controls: Enables AI-domain access state deduplication in migrations.
  - Risk: Disabled or partial flag results in data duplication or loss during AI matching sync.

---

## 5. CROSS-MODULE DIFFERENCES (CRITICAL)

- apps/JEM-migrations vs apps/autorec-amortization-migrations:
  - JEM-migrations: Focus on journal entry accounting data and signoff states; complex post-signoff state updates included.
  - autorec-amortization-migrations: Centered on amortization and autorec configurations; no signoff state logic applied.
- apps/adhoc-projects_api vs apps/ai-matching-migrations:
  - adhoc-projects_api: Strong authorization middleware and dynamic feature flag handling.
  - ai-matching-migrations: Stateless migrations focused on deduplication and AI-specific data transformations; no user session or auth.
- apps/autorec-amortization_main vs apps/apollo_email-event-trigger:
  - autorec-amortization_main: Contains financial business logic and workflow.
  - apollo_email-event-trigger: Pure integration module receiving and parsing inbound email events; no internal business workflows.
- ⚠️ apps/adhoc-projects_api vs apps/autorec-amortization_main:
  - adhoc-projects_api uses API-layer middleware for authorization and feature flags.
  - autorec-amortization_main enforces domain invariants in business logic internally.
  - Never replicate adhoc-projects_api authorization logic inside autorec-amortization_main or vice versa.

---

## 6. KNOWN FAILURE PATTERNS

### Pattern: Long-Running UI Blocking APIs
- Description: Synchronous API endpoints performing lengthy processing block frontend UI.
- Root cause: Absence of async job architecture; direct synchronous processing on HTTP layer.
- Impact: Frontend freezes, degraded user experience, potential data entry stalls.
- Example: Background upload endpoints blocked UI before migration to async job queues (CLOSE-12749).

### Pattern: Incorrect Transaction State Transitions
- Description: Journal and accounting transactions enter inconsistent states due to implicit or incorrect transition logic.
- Root cause: Missing explicit idempotent event-driven state updates; conflated UI and backend state assumptions.
- Impact: UI displays mismatch, stale reports, inconsistent accounting entries.
- Example: JE posted flag set without proper status update causing stale data in user reports (CLOSE-13442).

### Pattern: AI Sync Infinite Loops
- Description: AI sync triggers recursively fire without termination condition leading to stuck journal entries and system hangs.
- Root cause: Lack of re-entry flags to detect and prevent repeated AI sync invocations.
- Impact: System resource exhaustion, blocked workflows, incomplete data sync.
- Example: Journal entries stuck in pending AI sync status due to recursive AI matching calls.

### Pattern: Signoff State Divergence During Migration
- Description: Signoff states diverge between Lambda-based and ECS-based migration routes.
- Root cause: Partial feature flag rollout and inconsistent state update logic during migration.
- Impact: Checklist items show incorrect lock states; audit discrepancies.
- Example: Checklist item remained editable post-preparer signoff after incomplete MigrationSignoffConsistency flag deployment.

### Pattern: Replication Batch Overlap and Data Corruption
- Description: Overlapping replication batch processing causes data collisions and corrupted checklist/template state.
- Root cause: Missing or faulty concurrency controls and locking in Step Function workflows.
- Impact: Checklist data inconsistent; replication rollbacks needed.
- Example: Duplicate folder creation from concurrent replication triggered by close scheduling error.

---

<!-- BEGIN MINED -->
<!-- mined duplicate: Long-Running UI Blocking APIs suppressed -->
<!-- mined duplicate: Incorrect Transaction State Transitions suppressed -->
### Pattern: AI Sync Loop and Partial Failure Handling
- **Description**: AI matching and sync-triggered JE creation cause infinite loops or partial failures are not handled gracefully, resulting in stuck processes or incomplete journal entries.
- **Root cause**: Assumption that triggering sync processes will not recursively invoke themselves, and that partial failures can be ignored or cause total abort.
- **Impact**: System stability risks with infinite loops, inaccurate JE creation, and unclear failure statuses.
- **Example**: CLOSE-13438 prevents infinite sync loops by flagging re-syncs; CLOSE-13436 implements partial failure handling allowing continuation and failure reason tracking.

---
### Pattern: Inconsistent AI Suggestion Lifecycle
- **Description**: AI-generated rule suggestions are not properly persisted, dismissed, accepted, or rerendered, leading to poor UX and data inconsistencies.
- **Root cause**: Assumption that UI dismiss/accept actions automatically persist backend state and that stale suggestions won't resurface.
- **Impact**: Users see suggestions that should be hidden, or lose dismissed/accepted state; confusion and inefficiency.
- **Example**: CLOSE-13432 and CLOSE-13425 implemented persistent dismiss/accept APIs and UI hiding logic.

---
### Pattern: Feature Flag Cleanup and Management Oversights
- **Description**: Legacy or deprecated feature flags remain active or code paths behind flags are not cleaned, causing unnecessary complexity and potential bugs.
- **Root cause**: Assumption that feature flags, once transitioned, will be cleaned up promptly.
- **Impact**: Codebase complexity, maintenance burden, risk of accidentally toggling old functionality.
- **Example**: CLOSE-11710 deprecated autoAccrual flag and CLOSE-11894, CLOSE-14083 cleaned Q4 feature flag code.

---
### Pattern: Large Embedded Document Size Limits Ignored
- **Description**: Large embedded arrays in MongoDB collections cause exceeding document size limits (16MB), leading to errors and degraded system behavior.
- **Root cause**: Assumption that embedding large arrays inside single documents is sustainable at scale.
- **Impact**: DB errors, performance degradation, migration complexity.
- **Example**: CLOSE-14081 through CLOSE-14080 and others migrate embedded arrays (procedures and reconciliations) out of templates collection into linked collections via a feature-flagged new template DAL.

---
### Pattern: Backend Assumptions of Default or "Primary" Sides
- **Description**: Backend processes incorrectly assume balance or source sides in journal entries, causing inaccurate balances or misplaced references.
- **Root cause**: Assumption that the GL is always the primary side and some fixed assignment logic.
- **Impact**: Data export errors, incorrect financial data representation.
- **Example**: CLOSE-13705 updated functions to use explicit isGLSource field rather than fixed side assumptions.

---
### Pattern: UI Dropdown Filtering Mismatch
- **Description**: UI filtering behavior for large dropdown selection lists returns limited static options rather than dynamic results based on user input, frustrating users.
- **Root cause**: Assumption that static result sets suffice instead of dynamic, input-driven queries.
- **Impact**: User unable to find desired options beyond initial fixed subset.
- **Example**: CLOSE-14037 enhanced Workday JE line-level currency search to return user-input driven filtered options.

---
### Pattern: Conflict Handling Missing in Rule Management
- **Description**: When saving or running rules, conflicting active rules are not properly handled, leading to silent failures or overwrites.
- **Root cause**: Assumption that users either don’t create conflicting rules or backend silently resolves conflicts.
- **Impact**: Confusing UI, lost rule changes, inconsistent rule behavior.
- **Example**: CLOSE-12974 added conflict resolution UI when saving rules to set priority and prevent silent conflicts.

---
### Pattern: Missing or Incorrect Condition Logic Evaluation
- **Description**: Condition evaluation logic for rules (e.g., OR vs AND, exact match) is incorrect, resulting in errors or incorrect rule matches.
- **Root cause**: Assumption that condition logic implementations are correctly interpreted from specifications or input.
- **Impact**: Rule test failures, errors during evaluation, wrong results for users.
- **Example**: CLOSE-14066 fixed condition logic for OR selection and exact matches in JE Rules Phase 1.

---
### Pattern: Data Integrity Bugs in UI Due to Frontend Logic Errors
- **Description**: Frontend bugs cause data inconsistencies or incorrect states to be presented or stored in UI settings.
- **Root cause**: Assumption that small UI logic details do not affect data integrity.
- **Impact**: Incorrect checklist settings, lost user changes, support incidents.
- **Example**: CLOSE-14048 uncovered frontend bugs during Colonial Group investigation that led to incorrect Checklist Settings.

---

This set of failure patterns helps reviewers focus on domain assumptions about asynchronous processing, transactional state management, feature flag hygiene, data storage sizing, user input filtering, and proper handling of AI-generated suggestions and rule conflicts.

## Sources
- [CLOSE-13649: [Close Item Details] - Updates to Rolled Forward UI/UX](https://floqast.atlassian.net/browse/CLOSE-13649) (type: Story)
- [CLOSE-12487: [M7.1] Create Manual Export Endpoint](https://floqast.atlassian.net/browse/CLOSE-12487) (type: Story)
- [CLOSE-12749: Update upload chart of accounts to use POST /template/jobs for background COA upload](https://floqast.atlassian.net/browse/CLOSE-12749) (type: Story)
- [CLOSE-13440: [JE Rules Phase 2] Sync execution status — surface in rule failures UI](https://floqast.atlassian.net/browse/CLOSE-13440) (type: Story)
- [CLOSE-13442: [JE Rules Phase 2] Transaction state — move to Matched after JE posted](https://floqast.atlassian.net/browse/CLOSE-13442) (type: Story)
- [CLOSE-13430: [JE Rules Phase 2] Preview impact — transaction list view](https://floqast.atlassian.net/browse/CLOSE-13430) (type: Story)
- [CLOSE-13429: [JE Rules Phase 2] Impact calculation — display count in suggestion card](https://floqast.atlassian.net/browse/CLOSE-13429) (type: Story)
- [CLOSE-13432: [JE Rules Phase 2] Dismiss suggestion — persist & hide](https://floqast.atlassian.net/browse/CLOSE-13432) (type: Story)
- [CLOSE-13431: [JE Rules Phase 2] Accept suggestion — convert to pre-filled draft rule](https://floqast.atlassian.net/browse/CLOSE-13431) (type: Story)
- [CLOSE-13439: [JE Rules Phase 2] Sync execution logging](https://floqast.atlassian.net/browse/CLOSE-13439) (type: Story)
- [CLOSE-13436: [JE Rules Phase 2] Sync-triggered JE creation — partial failure handling](https://floqast.atlassian.net/browse/CLOSE-13436) (type: Story)
- [CLOSE-13441: [JE Rules Phase 2] Transaction state — move to Pending after JE created](https://floqast.atlassian.net/browse/CLOSE-13441) (type: Story)
- [CLOSE-13437: [JE Rules Phase 2] Re-sync — trigger second AI Matching sync after JE creation](https://floqast.atlassian.net/browse/CLOSE-13437) (type: Story)
- [CLOSE-13428: [JE Rules Phase 2] Impact calculation — backend count of matching DS2 transactions](https://floqast.atlassian.net/browse/CLOSE-13428) (type: Story)
- [CLOSE-13427: [JE Rules Phase 2] Suggested rules section — render suggestion cards](https://floqast.atlassian.net/browse/CLOSE-13427) (type: Story)
- [CLOSE-13426: [JE Rules Phase 2] Suggested rules section — UI shell in JE Rules modal](https://floqast.atlassian.net/browse/CLOSE-13426) (type: Story)
- [CLOSE-13435: [JE Rules Phase 2] Sync-triggered JE creation — call JEM API](https://floqast.atlassian.net/browse/CLOSE-13435) (type: Story)
- [CLOSE-13438: [JE Rules Phase 2] Re-sync — loop prevention](https://floqast.atlassian.net/browse/CLOSE-13438) (type: Story)
- [CLOSE-13434: [JE Rules Phase 2] Sync hook — execute rules in priority order](https://floqast.atlassian.net/browse/CLOSE-13434) (type: Story)
- [CLOSE-13425: [JE Rules Phase 2] Suggestion API — accept & dismiss endpoints](https://floqast.atlassian.net/browse/CLOSE-13425) (type: Story)
- [CLOSE-13424: [JE Rules Phase 2] Suggestion API — list & read endpoints](https://floqast.atlassian.net/browse/CLOSE-13424) (type: Story)
- [CLOSE-13433: [JE Rules Phase 2] Sync hook — identify active rules for synced GL account + legal entity](https://floqast.atlassian.net/browse/CLOSE-13433) (type: Story)
- [CLOSE-14048: [Colonial Group Follow up] Checklist Settings template data integrity ](https://floqast.atlassian.net/browse/CLOSE-14048) (type: Story)
- [CLOSE-12917: [IAC Migration | Frontend] Update Consumers for POST /completeness/build](https://floqast.atlassian.net/browse/CLOSE-12917) (type: Story)
- [CLOSE-13639: [Schema] Add glSourceNumber to account settings schema](https://floqast.atlassian.net/browse/CLOSE-13639) (type: Story)
- [CLOSE-14037: Support Workday line-level currency searching options with user input](https://floqast.atlassian.net/browse/CLOSE-14037) (type: Story)
- [CLOSE-11894: Clean up Q4 feature flag(s) - Checklist Settings](https://floqast.atlassian.net/browse/CLOSE-11894) (type: Story)
- [CLOSE-13705: [Python, API] Use isGLSource to resolve GL balance ](https://floqast.atlassian.net/browse/CLOSE-13705) (type: Story)
- [CLOSE-13415: [JE Rules Phase 2] Historical transaction query — data access layer](https://floqast.atlassian.net/browse/CLOSE-13415) (type: Story)
- [CLOSE-13659: [API] Pass matchSetId during JE creation](https://floqast.atlassian.net/browse/CLOSE-13659) (type: Story)
- [CLOSE-13814: Add new singleItemLockEnabled field to companySettings | fq-schemas](https://floqast.atlassian.net/browse/CLOSE-13814) (type: Story)
- [CLOSE-14084: Add SFTP E2E Export tests to Deployment Configs](https://floqast.atlassian.net/browse/CLOSE-14084) (type: Task)
- [CLOSE-12773: [1] Create updateLockStatus middleware in recs_service](https://floqast.atlassian.net/browse/CLOSE-12773) (type: Story)
- [CLOSE-13087: Update Onboarding Docs](https://floqast.atlassian.net/browse/CLOSE-13087) (type: Task)
- [CLOSE-14083: [checklist-client] Clean up Q4 feature flagged code](https://floqast.atlassian.net/browse/CLOSE-14083) (type: Story)
- [CLOSE-12555: [2] Allow user to manually unlock a Reconciliation | recs-client](https://floqast.atlassian.net/browse/CLOSE-12555) (type: Story)
- [CLOSE-12974: Save + run and conflict handling U6](https://floqast.atlassian.net/browse/CLOSE-12974) (type: Story)
- [CLOSE-14066: [JE Rules Phase 1]: Fix conditions for test rules](https://floqast.atlassian.net/browse/CLOSE-14066) (type: Story)
- [CLOSE-11710: Deprecate and remove autoAccrual feature flag](https://floqast.atlassian.net/browse/CLOSE-11710) (type: Story)
- [CLOSE-13815: Update companies_service contract with singleItemLockEnabled | companies_service](https://floqast.atlassian.net/browse/CLOSE-13815) (type: Story)
- [CLOSE-13991: Fix Invalid Date on dashboard](https://floqast.atlassian.net/browse/CLOSE-13991) (type: Story)
- [CLOSE-14082: Regression test bulk-edit-templates_lambda after template-dal migration](https://floqast.atlassian.net/browse/CLOSE-14082) (type: Story)
- [CLOSE-14081: Migrate platform/companies_delete template collection access to template-dal](https://floqast.atlassian.net/browse/CLOSE-14081) (type: Story)
- [CLOSE-13822: [UI] Add multi-assign rules modal](https://floqast.atlassian.net/browse/CLOSE-13822) (type: Story)
- [CLOSE-14080: Migrate close/remind_recommendations template collection access to template-dal](https://floqast.atlassian.net/browse/CLOSE-14080) (type: Story)
- [CLOSE-14079: Migrate platform/super_company template collection access to template-dal](https://floqast.atlassian.net/browse/CLOSE-14079) (type: Story)
- [CLOSE-14078: Migrate close/item_add-follower template collection access to template-dal](https://floqast.atlassian.net/browse/CLOSE-14078) (type: Story)
- [CLOSE-14077: Migrate integrations-monorepo/folders_api template collection access to template-dal](https://floqast.atlassian.net/browse/CLOSE-14077) (type: Story)
- [CLOSE-14076: Migrate close/bulk-edit-wrap-up template collection access to template-dal](https://floqast.atlassian.net/browse/CLOSE-14076) (type: Story)
- [CLOSE-14068: fq-schemas: Add independent ProcedureTemplate and RecTemplate top-level schemas](https://floqast.atlassian.net/browse/CLOSE-14068) (type: Story)
<!-- END MINED -->
## 7. REVIEW HEURISTICS (HOW TO THINK)

When analyzing a PR:

- Check if logic:
  - Respects strict signoff ordering and role-based creation/removal permissions.
  - Avoids synchronous blocking calls in API layers for long-running processes (prefer async jobs).
- Always verify:
  - Feature flags fully implemented and toggled consistently across all deployment routes.
  - Export workflows enforce single-active-export and notify only upon completion.
- Be suspicious of:
  - Replication logic lacking concurrency control or idempotency guarantees.
  - AI sync or matching code invoking recursive triggers without safeguards.

---

## 8. HIGH-RISK AREAS

Focus extra scrutiny on:

- apps/JEM-migrations/signoff-state-update handlers
- apps/adhoc-projects_api authorization middleware and feature flag branching
- apps/ai-matching-migrations deduplication and sync re-entry logic
- apps/autorec-amortization_main journal entry creation and state transitions
- apps/apollo_email-event-trigger inbound email event parsing and notification triggers
- apps/autorec-amortization-migrations migration scripts with financial config changes

---

## 9. CONFIDENCE GUIDELINES

Raise risk level if:

- Feature flag toggles are incomplete or split between deployment routes without cross-validation.
- PR introduces synchronous/blocking API calls in frontend-facing endpoints.
- Replication or AI sync logic lacks explicit concurrency and re-entry protections.
- Signoff permissions or workflows modified without enforcing strict sequential and role checks.

Lower risk if:

- Changes limited to isolated migration scripts with small scope and database-only side-effects.
- Reusable domain logic verifies idempotency and uses existing audited method calls.
- Feature flags are fully tested across Lambda and ECS deployments with consistent behavior.
- Exports remain strictly asynchronous with proper notification and audit events emitted.

---