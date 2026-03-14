# Workflow Documentation for Single Item Separate Strict Sign Off

## 1. Feature Overview
This feature introduces granular, per-item strict sign-off controls to enhance approval workflows on financial review items. It allows administrators to configure sign-off requirements such as enforcing that preparers sign off before reviewers, limiting each user to a single sign-off per item, and restricting who can sign off. These controls apply across different platforms including folders, checklists, reconciliation slideouts, Slack, and MS Teams notifications, ensuring consistent and enforceable sign-off rules for financial accuracy and compliance.

## 2. Key Concepts / Glossary
- **Sign-off**: The action of approving or marking a review item as completed.
- **Preparer**: The user responsible for preparing the item before review.
- **Reviewer**: The user responsible for reviewing the prepared item.
- **Strict Sign-off**: A set of business rules that enforce granular controls on who can sign off, in what order, and whether multiple signatures are allowed.
- **Preparer sequence**: A rule requiring all preparers to sign off before reviewers can review.
- **Single sign-off per user**: A control preventing users from signing off an item more than once.
- **Sign-off toggles/buttons**: UI elements that users click to approve/sign off items.
- **Feature flag**: A toggle to enable or disable the new strict sign-off functionality.
- **Organizational Role**: Admins, managers, preparers, reviewers involved in sign-off processes.
- **SSO (Single Sign-On)**: Authentication system that manages user permissions and roles for signoff validation.

## 3. Core Workflows

### A. Configuring Sign-off rules in Company Settings
- **User story**: As an admin, I want to configure strict sign-off rules for my organization so that all review processes follow the desired approval controls.
- **Flow**:
  1. Admin navigates to Company Settings.
  2. Admin toggles the "Separate Strict Sign-Off" feature flag to ON.
  3. Admin enables granular options:
     - "Items can only be signed off once."
     - "Users cannot sign off as both preparer and reviewer."
     - "Preparer signatures must precede reviewer signatures."
     - "Automatically lock files upon item completion" (future feature, currently optional).
  4. Changes are saved and propagated to relevant modules.
- **Rules/Constraints**:
  - Defaults to previous boolean setting if granular options are not configured.
  - Backward compatibility is maintained.
- **Acceptance criteria**:
  - When enabled, the system enforces rules individually per item.
  - UI accurately reflects the configured options.
  - Sign-off validation adheres to new settings across all platforms.

### B. Sign-off validation during item review
- **User story**: As a user, I want to see whether I can sign off an item based on current settings to ensure compliance.
- **Flow**:
  1. User views an item’s details in folder, checklist, or reconciliation slideout.
  2. Sign-off button/status appears as "Mark as Reviewed/Prepared" if signing is allowed.
  3. If preparers must sign before reviewers, and preparers haven't signed yet, the system disables the sign-off button and shows "Still Being Prepared."
  4. User clicks sign-off button.
  5. Validation logic (based on feature flag and settings) verifies:
     - User role (preparer/reviewer/admin)
     - Whether the user has already signed off (if single sign-off is enforced)
     - If all preparers are signed (if preparer-before-reviewer rule is active)
     - Whether the user is authorized (via SSO permissions)
  6. If validation passes, the signature is recorded; otherwise, an error message is shown.
- **Rules/Constraints**:
  - Validation strictly respects granular options when feature flag is on.
  - When feature flag is off, previous simple rules apply.
  - Sign-off attempts that violate rules are rejected with a detailed message.
- **Acceptance criteria**:
  - Sign-off buttons accurately reflect enabled/disabled state based on rules.
  - Users cannot sign off if rules disallow it; attempts are blocked.
  - Validation logic is consistent across all modules and notifications.

### C. Sign-off behavior in notifications (Slack & MS Teams)
- **User story**: As a reviewer, I want sign-off buttons in notifications to be enabled only when I am authorized according to rules.
- **Flow**:
  1. User receives a notification with sign-off options.
  2. Buttons display as "Mark As Reviewed/Prepared" if sign-off permitted.
  3. If preparers haven't signed as required, buttons show "Still Being Prepared."
  4. User clicks sign-off button.
  5. System validates according to active settings:
     - Checks if the user role aligns.
     - Ensures preparers/signatures are completed before allowing reviewers.
     - Enforces single sign-off per user if configured.
  6. Validation results are conveyed via notification UI and error messages if applicable.
- **Rules/Constraints**:
  - Messaging format differs between Slack and MS Teams.
  - Role checks are based on SSO permissions.
  - All rules are enforced regardless of notification platform.
- **Acceptance criteria**:
  - Notifications display correct sign-off button states.
  - Validation triggers correctly upon button interaction.
  - Error messages clearly indicate rule violations.

### D. Daily Sign-off Reminders
- **User story**: As a user, I want daily notifications of items due today with sign-off buttons that respect strict rules.
- **Flow**:
  1. System sends reminders with list of pending items.
  2. Sign-off buttons are shown as "Mark As Reviewed/Prepared" or "Still Being Prepared" based on current signatures and rules.
  3. When a user clicks sign-off:
     - Validation occurs per the configured strict sign-off options.
     - Sign-off is recorded if valid; otherwise, error is shown.
- **Rules/Constraints**:
  - Only items applicable to the user's permissions and current sign-off state are interactable.
  - Sign-off attempt failures are communicated via notifications.
- **Acceptance criteria**:
  - Notifications display correct button states.
  - Users cannot bypass sign-off rules.
  - Sign-off status updates correctly across reminders.

### E. Sign-off in Reconciliation Slideout
- **User story**: As an accountant, I want to see whether I can add my signatures in the reconciliation slideout respecting strict rules.
- **Flow**:
  1. User opens the reconciliation slideout.
  2. The "Add Preparer" button is enabled or disabled:
     - Disabled if *preparers must sign off before reviewers* is active and a reviewer has already signed.
  3. User attempts to add their signature.
  4. Validation logic runs:
     - Checks if the user role is authorized.
     - Confirms if preparers have signed when required.
  5. Record the signature or prevent sign-off with a message.
- **Rules/Constraints**:
  - No automatic opening of “Add Preparer” dropdown if disallowed.
  - Validations mirror those on other modules.
- **Acceptance criteria**:
  - Button disable/enable behavior matches rules.
  - Sign-off attempts are validated and logged.
  - No unintended action occurs when sign-off is disallowed.

### F. Cloning and Creating Entities with Sign-off Settings
- **User story**: As an administrator, I want new or cloned entities to have the correct strict sign-off settings based on the organization’s configuration.
- **Flow**:
  1. When creating a new entity via the wizard or cloning an existing one, the system:
     - Preserves existing `strictSignoffEnabled` boolean.
     - Sets `settings.strictSignOff` nested object, mapping from that boolean:
       - All rules enabled if boolean is true.
       - Defaults or disabled if false.
  2. Ensures backward compatibility with legacy `strictSignoffEnabled`.
- **Rules/Constraints**:
  - Cloning retains previous configuration.
  - New entities get the full granular settings structure upon creation.
- **Acceptance criteria**:
  - Entities have consistent sign-off configurations upon creation or cloning.
  - Settings are correctly mapped and stored.
  - Backward compatibility is maintained for legacy data.

### G. API and Schema Updates
- **User story**: As a developer, I want the backend to support the new granular strict sign-off settings through API contracts.
- **Flow**:
  1. API schema is extended with new paths and request/response models for GET and PATCH of settings.
  2. The server updates the company settings with nested `settings.strictSignOff`.
  3. Clients fetch and update the new nested object.
  4. Data migrations ensure existing data continues to work with minimal disruption.
- **Rules/Constraints**:
  - Backwards compatible schema design.
  - Support partial updates.
  - Default values applied if data missing.
- **Acceptance criteria**:
  - API responses include `settings.strictSignOff`.
  - PATCH updates correctly modify nested rules.
  - Schema validation passes.
  - Existing clients can fetch and update settings seamlessly.

## 4. Edge Cases and Backward Compatibility
- When the feature flag for separate strict sign-off is disabled, all previous simple boolean rules are enforced.
- Existing entities without the new `strictSignOff` object continue to function; defaults are applied until updated.
- Cloning entities preserves legacy `strictSignoffEnabled` boolean and maps it to new nested options.
- Sign-off attempts from users who already signed off are disabled if "items can only be signed off once" is active.
- Validation of permissions integrates with SSO to prevent unauthorized sign-offs.
- Notifications and slideouts reflect current rules, with behaviors toggled based on feature flag states.
- Schema updates are backward compatible, supporting both old and new data contracts during migration.

## 5. Repos and Components Involved
| Repository/Component | Role |
|------------------------|-------|
| `platform/apps/companies_service` | API contract, data transformation, schema management |
| `platform/apps/companies_create` | Entity creation and cloning with sign-off settings |
| `ui/company-settings-client` | UI for configuring and displaying sign-off rules |
| `ui/checklist-client` | Sign-off validation, toggle controls, slideout UI |
| `ui/recs-client` | Sign-off validation, slideouts, reconciliation workflows |
| `ui/slack-integrations` | Signoff buttons and validation in Slack notifications |
| `apps/notification-integrations_handler` | MS Teams/Slack notification handling with signoff controls |
| `ui/close` | Frontend components for company info, settings, and feature flag gating |
| `shared/utils/signoff.utils.js` | Signoff validation logic, including support for new settings |

---

This document should guide end-to-end testing to verify correct enforcement of granular strict sign-off rules, proper UI behavior, validation logic, notification handling, API integration, and data consistency across the platform.