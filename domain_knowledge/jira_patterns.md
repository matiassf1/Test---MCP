# Jira Patterns
Mined: 50 tickets (latest 50 of 50) updated in last 90 days

## Failure Patterns

### Pattern name: Long-Running UI Blocking APIs
- **Description**: User interface becomes unresponsive or blocked while long-running backend tasks complete.
- **Root cause**: Assumption that API endpoints can run synchronously without negatively impacting user experience or UI responsiveness.
- **Impact**: Users experience delays, cannot navigate away or perform other actions, leading to poor UX and workflow friction.
- **Example**: CLOSE-12749 changed a background upload of Chart of Accounts from a blocking synchronous API to an asynchronous background job via a POST to /template/jobs to avoid UI blocking.

---

### Pattern name: Incorrect Transaction State Transitions
- **Description**: Transactions do not properly transition between states (e.g., from Pending to Matched, or to Pending after JE creation), causing UI and data inconsistencies.
- **Root cause**: Assumption that transaction state transitions happen automatically or in a certain order without explicit, idempotent updates.
- **Impact**: UI tabs show incorrect transactions, reports are inaccurate, and users may see stale or misleading information.
- **Example**: CLOSE-13442 and CLOSE-13441 enforce explicit state transitions of transactions after JE posting and creation, respectively.

---

### Pattern name: AI Sync Loop and Partial Failure Handling
- **Description**: AI matching and sync-triggered JE creation cause infinite loops or partial failures are not handled gracefully, resulting in stuck processes or incomplete journal entries.
- **Root cause**: Assumption that triggering sync processes will not recursively invoke themselves, and that partial failures can be ignored or cause total abort.
- **Impact**: System stability risks with infinite loops, inaccurate JE creation, and unclear failure statuses.
- **Example**: CLOSE-13438 prevents infinite sync loops by flagging re-syncs; CLOSE-13436 implements partial failure handling allowing continuation and failure reason tracking.

---

### Pattern name: Inconsistent AI Suggestion Lifecycle
- **Description**: AI-generated rule suggestions are not properly persisted, dismissed, accepted, or rerendered, leading to poor UX and data inconsistencies.
- **Root cause**: Assumption that UI dismiss/accept actions automatically persist backend state and that stale suggestions won't resurface.
- **Impact**: Users see suggestions that should be hidden, or lose dismissed/accepted state; confusion and inefficiency.
- **Example**: CLOSE-13432 and CLOSE-13425 implemented persistent dismiss/accept APIs and UI hiding logic.

---

### Pattern name: Feature Flag Cleanup and Management Oversights
- **Description**: Legacy or deprecated feature flags remain active or code paths behind flags are not cleaned, causing unnecessary complexity and potential bugs.
- **Root cause**: Assumption that feature flags, once transitioned, will be cleaned up promptly.
- **Impact**: Codebase complexity, maintenance burden, risk of accidentally toggling old functionality.
- **Example**: CLOSE-11710 deprecated autoAccrual flag and CLOSE-11894, CLOSE-14083 cleaned Q4 feature flag code.

---

### Pattern name: Large Embedded Document Size Limits Ignored
- **Description**: Large embedded arrays in MongoDB collections cause exceeding document size limits (16MB), leading to errors and degraded system behavior.
- **Root cause**: Assumption that embedding large arrays inside single documents is sustainable at scale.
- **Impact**: DB errors, performance degradation, migration complexity.
- **Example**: CLOSE-14081 through CLOSE-14080 and others migrate embedded arrays (procedures and reconciliations) out of templates collection into linked collections via a feature-flagged new template DAL.

---

### Pattern name: Backend Assumptions of Default or "Primary" Sides
- **Description**: Backend processes incorrectly assume balance or source sides in journal entries, causing inaccurate balances or misplaced references.
- **Root cause**: Assumption that the GL is always the primary side and some fixed assignment logic.
- **Impact**: Data export errors, incorrect financial data representation.
- **Example**: CLOSE-13705 updated functions to use explicit isGLSource field rather than fixed side assumptions.

---

### Pattern name: UI Dropdown Filtering Mismatch
- **Description**: UI filtering behavior for large dropdown selection lists returns limited static options rather than dynamic results based on user input, frustrating users.
- **Root cause**: Assumption that static result sets suffice instead of dynamic, input-driven queries.
- **Impact**: User unable to find desired options beyond initial fixed subset.
- **Example**: CLOSE-14037 enhanced Workday JE line-level currency search to return user-input driven filtered options.

---

### Pattern name: Conflict Handling Missing in Rule Management
- **Description**: When saving or running rules, conflicting active rules are not properly handled, leading to silent failures or overwrites.
- **Root cause**: Assumption that users either don’t create conflicting rules or backend silently resolves conflicts.
- **Impact**: Confusing UI, lost rule changes, inconsistent rule behavior.
- **Example**: CLOSE-12974 added conflict resolution UI when saving rules to set priority and prevent silent conflicts.

---

### Pattern name: Missing or Incorrect Condition Logic Evaluation
- **Description**: Condition evaluation logic for rules (e.g., OR vs AND, exact match) is incorrect, resulting in errors or incorrect rule matches.
- **Root cause**: Assumption that condition logic implementations are correctly interpreted from specifications or input.
- **Impact**: Rule test failures, errors during evaluation, wrong results for users.
- **Example**: CLOSE-14066 fixed condition logic for OR selection and exact matches in JE Rules Phase 1.

---

### Pattern name: Data Integrity Bugs in UI Due to Frontend Logic Errors
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

