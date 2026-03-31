## Domain Rules

### Checklist Item Signoff / Workflow Rules
- Signoff ordering must respect a sequential workflow: preparer signs off before reviewer can sign.
- Only authorized roles can sign or remove signoffs.
- Removal of a signoff should be allowed only by roles with explicit permission (e.g., preparer can remove their own signoff, reviewers can remove theirs).
- Signoff actions are tied to checklist items and signature IDs; POST requests create signoffs, DELETE or PUT/POST to remove.
- Signed-off statuses trigger state changes on items, such as locking further edits or enabling next workflow steps.
- During migration from Lambda to ECS, feature flag toggles route between old and new API endpoints transparently without affecting signoff state or ordering.

### Replication Workflow Rules
- Replication involves multiple orchestrated Step Functions ensuring exactly-once processing per replication request.
- Monthly scheduled jobs trigger replication batches via cron Lambda.
- Replication must preserve data integrity: folders, templates, checklists are sequentially created and applied.
- The review worker validates replicated data before marking replication complete.
- Undo replication (unreplicate) reverses prior replication actions and updates states to allow corrective reapplication.
- Concurrent worker management ensures no overlapping processing on the same data items.

### Export Workflow Rules
- Export requests trigger asynchronous Excel generation and S3 upload.
- Users are notified by WebSocket or email with retrieval link once export completes.
- Only one export per user/entity can be active; new requests queue or cancel prior pending exports.
- Export flows trigger audit/log events for monitoring.

## Roles

### Checklist Roles
- Preparer: can create and remove own signoffs, edit checklist items before signoff.
- Reviewer: can create and remove own signoffs after preparer signoff, review checklist entries.
- Admin/Manager: can override signoff restrictions, remove any signoffs, access audit trails.
- Client User: limited to viewing checklist item statuses, cannot sign off.
- Role capabilities enforced via authorization middleware, and role context differs per module (e.g., checklist vs replication).

### Replication Roles
- Replication Worker: executes data preparation, folder creation, template application.
- Replication Manager: triggers batch processes, views replication queues.
- Reviewer: approves replication status updates.
- System Roles (Lambda functions): run with permissions scoped to relevant MongoDB collections and storage actions.

### Export Roles
- Export Requester: triggers exports.
- Export Processor: async background role generating/exporting files.
- Export Notifier: sends notifications post-export.

## Feature Flags

- Checklist ECS Migration Flag:
  - OFF: Checklist item API endpoints route to Lambda (/item*).
  - ON: Routes client calls to ECS service via /checklist/v1/items/* endpoints.
  - Controls progressive migration phases: item CRUD + signoffs, documents, JEM routes.
  - Enables blue/green deployment, rollback, and gradual switch-over without user impact.

- Export Flow Flag (implicit):
  - Controls whether export requests use legacy synchronous API or asynchronous S3-based export pipeline.
  - ON enables async export with notification.

## Domain Differences

- Checklist vs Recommendations (Recs):
  - Checklist domain includes signoff workflows with strict ordering and role-based permissions.
  - Recommendations focus on entity progress, trends, and analytics without signoff.
  - Checklist modules have document attachments and journal entries tightly coupled with signoff state machines.
  - Recommendations domain uses separate analytics DB for metrics; checklist uses core MongoDB collections tightly integrated.

- Replication Domain:
  - Data and folders explicitly replicated month-to-month preserving procedural fidelity.
  - Use of Step Functions enforcing strict multi-step orchestration.
  - Additional integration with ReMind intermediate queue after checklist replication.
  - Multi-Lambda design with concurrency control and error handling.

- AI Domains:
  - AI modules operate with strong tenant isolation and data minimization.
  - Runtime execution occurs in stateless, sandboxed environments with no external network access.
  - AI does not impact workflows directly but provides assisted task generation and transaction matching.
  - AI data usage governed by zero-retention and encrypted transport policies.

---

This extraction summarizes runtime domain logic for the TASKS, CHECKLIST, REPLICATION, and associated systems per the provided architecture and specification documents.