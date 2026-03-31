# Consolidated Domain Model

---

## 1. Modules

### apps/JEM-migrations
- Responsibility: Database schema and data migrations related to Journal Entry Management (JEM), especially affecting journal entries and accounting entities.
- Key Differences: Focused solely on backend migrations for Close system's accounting domain, manages post-status signoff state updates during migration.

### apps/adhoc-projects_api
- Responsibility: API service for managing ad-hoc projects including CRUD operations, user access control, and project-specific feature flag handling.
- Key Differences: Serves project management domain with strong emphasis on authorization middleware and dynamic feature toggling; handles client-facing API workflows.

### apps/ai-matching-migrations
- Responsibility: Migrations and data transformations specific to AI matching features such as account setting adjustments and deduplication of access states.
- Key Differences: Specialized in AI domain schema changes; overlaps with auto reconciliation but focuses on AI-driven processes and deduplication.

### apps/apollo_email-event-trigger
- Responsibility: Integration with email event systems (Mandrill, SES, SNS); manages email receipt, event processing, and notification controls.
- Key Differences: Isolated email integration module focused on event-driven notifications, separate from core business logic.

### apps/autorec-amortization-migrations
- Responsibility: Performs database migrations related to auto-reconciliation and amortization configurations including depreciation items and journal entry enhancements.
- Key Differences: Migration focus on amortization and auto-reconciliation related data; complements main autorec-amortization app.

### apps/autorec-amortization_main
- Responsibility: Core handling of auto-reconciliation, amortization processing, configuration management, and journal entry workflows.
- Key Differences: Business logic module managing financial workflows involving reconciliation and amortization; rich in constants and domain-specific policies.

---

## 2. Domain Rules (Invariants)

### Checklist Signoff / Workflow Rules
- Signoffs must proceed in defined sequential order: Preparers sign off before Reviewers.
- Only authorized roles may create or remove signoffs.
- Signoff removal is restricted by role: preparers may remove their own, reviewers may remove theirs; admins may override.
- Signoff operations link to checklist items and signature IDs; creating and removing signoffs use distinct HTTP verbs and idempotent requests.
- Signed-off statuses lock checklist items from editing and enable progress to subsequent workflow stage.
- Feature flags governing migration ensure signoff state consistency regardless of route (Lambda or ECS).

### Replication Workflow Rules
- Replication is orchestrated via Step Functions ensuring exactly-once, ordered processing of replication batches.
- Monthly scheduled replication triggers ensure chronological, consistent data replication.
- Replication preserves folder/template/checklist creation order and validates via dedicated review workers.
- Undo/reversal of replication updates states and allows corrections without data corruption.
- Concurrency controls prevent overlapping processing of identical data during replication.

### Export Workflow Rules
- Export requests trigger asynchronous Excel generation and S3 upload pipelines.
- Notifications sent post-export via WebSocket or email with retrieval links.
- Only one active export per user or entity is allowed; subsequent requests queue or cancel prior exports.
- Export processes emit audit/log events to enable monitoring and traceability.

---

## 3. Roles

### Checklist Domain Roles
- **Preparer**: Creates/removes own signoffs, edits checklist items before signoff, cannot override reviewer signoffs.
- **Reviewer**: Creates/removes own signoffs only after preparer signoff; reviews checklist progress.
- **Admin/Manager**: Overrides signoff restrictions, removes any signoff, accesses audit trails for compliance.
- **Client User**: Read-only access to checklist statuses; no signoff permissions.

### Replication Domain Roles
- **Replication Worker**: Executes replication steps—data preparation, folder creation, template application.
- **Replication Manager**: Initiates replication batches and monitors queues.
- **Reviewer**: Validates replicated data and approves replication completions.
- **System Roles (Automated Lambdas/Services)**: Operate with scoped permissions targeting specific MongoDB collections and storage interactions.

### Export Domain Roles
- **Export Requester**: Initiates export jobs.
- **Export Processor**: Runs asynchronous file generation and S3 upload.
- **Export Notifier**: Sends user notifications upon export completion.

---

## 4. Failure Patterns

### Long-Running UI Blocking APIs
- **Issue**: Synchronous API endpoints running long tasks block front-end responsiveness.
- **Symptoms**: UI freezes, users cannot navigate or proceed while awaiting completion.
- **Prevention**: Shift long-running processes to async background jobs; return immediately with job status.
- **Reference**: Background uploads moved to async job queues (CLOSE-12749).

### Incorrect Transaction State Transitions
- **Issue**: Transactions move incorrectly between states causing UI and data discrepancies.
- **Symptoms**: Mismatched UI tabs, stale reports, inconsistent journal entry posting.
- **Prevention**: Explicit, idempotent state transitions triggered by events; avoid implicit state assumptions.
- **Reference**: Enforced state changes post-JE creation and posting (CLOSE-13442, CLOSE-13441).

### AI Sync Loop and Partial Failure Handling
- **Issue**: Triggered AI sync processes recursively invoke themselves causing infinite loops.
- **Symptoms**: System hangs or stuck journal entries; incomplete or inconsistent AI-generated data.
- **Prevention**: Flag/track sync re-entries to prevent loops; implement partial failure handling to allow continuation with error tracking.
- **Reference**: Sync loop prevention and partial failure APIs (CLOSE-13438, CLOSE-13436).

### Inconsistent AI Suggestion Lifecycle
- **Issue**: UI actions on AI suggestions (dismiss, accept) do not persist backend state correctly.
- **Symptoms**: Dismissed suggestions reappear; inconsistent UX; data state confusion.
- **Prevention**: Backend persistency APIs for suggestion state; UI logic to hide based on persisted state.
- **Reference**: Persistent dismiss/accept API integration (CLOSE-13432, CLOSE-13425).

### Feature Flag Cleanup and Management Oversights
- **Issue**: Feature flags remain active or code behind deprecated flags remains uncleared.
- **Symptoms**: Increased code complexity, risk of unwanted feature activation, maintenance difficulties.
- **Prevention**: Timely removal of obsolete flags and code; maintain flag lifecycle practices.
- **Reference**: Multiple flag removals documented (CLOSE-11710, CLOSE-11894, CLOSE-14083).

### Large Embedded Document Size Limits Ignored
- **Issue**: Large arrays embedded in MongoDB documents exceed 16MB limit causing failures.
- **Symptoms**: MongoDB errors, slow queries, failed migrations.
- **Prevention**: Normalize large embedded arrays into linked collections; use feature flags for gradual migration.
- **Reference**: Migration from embedded procedures/reconciliations (CLOSE-14081 and related).

---

# Summary

This unified domain model distills core modules, rules, roles, and failure patterns. It enforces:

- Strict signoff sequencing and role-based access in checklist workflows.
- Orchestrated batch replication with concurrency safeguards.
- Async, monitored export pipelines with notification and queuing.
- Clear domain separation: migration modules focus on schema/data changes; application modules implement business logic.
- Awareness and prevention of past failure modes through explicit state management, async processing, and backend validation.
- Role definitions scale across domains with clear permissions and boundaries.

This model supports code review heuristics by highlighting common pitfalls (e.g., sync blocking, state transition mistakes) and advocates for clean modularization, migrating from duplicated utilities toward shared, centralized patterns.