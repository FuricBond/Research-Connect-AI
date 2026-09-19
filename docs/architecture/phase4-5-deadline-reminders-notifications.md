# Phase 4.5 — Deadline Reminders, Notifications & Scheduled Alerts

## Executive Summary

Phase 4.5 establishes a production-grade, deterministic, and idempotent notification and reminder engine for ResearchConnect AI. Built on top of Phase 2.7 canonical deadline intelligence, Phase 4.1 researcher workspace, Phase 4.2 research submissions, Phase 4.3 submission documents, and Phase 4.4 research calendar, this phase enables researchers to receive timely advance alerts for both canonical opportunity deadlines and user-created research calendar planning milestones.

The system enforces strict multi-milestone isolation, extension/revision-aware recalculation, zero mutation of canonical deadline evidence, zero impact on ranking or personalization, and bounded database complexity (Zero N+1) capable of processing 1,000 researchers in under 800 milliseconds.

---

## 1. Architectural Overview

```text
  Phase 2.7 Canonical Deadline View (Normalized UTC, Timezone, AoE, Milestone)
                            ↓
               ReminderSchedulerService
               ├── Canonical Resolution Cache (per-opportunity)
               ├── Milestone Isolation Filter (Abstract, Submission, Camera-Ready, etc.)
               └── Revision Evaluator (Extensions, Moves, Conflicts)
                            ↓
                      ReminderRule
               (e.g., 14d, 7d, 3d, 24h before submission via IN_APP / EMAIL)
                            ↓
               Deterministic Deduplication Key
    (SHA-256: profile_id + source_id + milestone + rule_id + target_instant + channel)
                            ↓
                      Notification
               (Status: PENDING → DELIVERED / FAILED)
                            ↓
                   NotificationChannel
         ┌──────────────────┼──────────────────┐
         ↓                  ↓                  ↓
 InAppNotificationChannel  EmailNotificationChannel  PushNotificationChannel
         ↓                  ↓ (MockEmailProvider)      ↓ (MockPushProvider)
 Notification Center       User Inbox                 Device Push
         └──────────────────┼──────────────────┘
                            ↓
              NotificationDeliveryAttempt
             (Audit trail with status & timestamp)
```

---

## 2. Domain Models

### `NotificationPreferenceModel` (`researcher_notification_preferences`)
Per-researcher preferences controlling active delivery channels and notification triggers:
- `profile_id`: Foreign key referencing `research_profiles.id` (Unique, Cascading)
- `email_enabled`: Boolean (default `True`)
- `in_app_enabled`: Boolean (default `True`)
- `deadline_reminders_enabled`: Boolean (default `True`)
- `extension_notifications_enabled`: Boolean (default `True`)
- `conflict_notifications_enabled`: Boolean (default `True`)
- `calendar_event_reminders_enabled`: Boolean (default `True`)

### `ReminderRuleModel` (`reminder_rules`)
Configurable advance reminder schedules per researcher:
- `profile_id`: Foreign key referencing `research_profiles.id`
- `event_type`: Target milestone (e.g., `OPPORTUNITY_SUBMISSION`, `ABSTRACT_DEADLINE`, `CAMERA_READY`, or `None` for all)
- `offset_amount`: Integer (e.g., 14, 7, 3, 24, 1)
- `offset_unit`: Enum (`DAYS`, `HOURS`, `MINUTES`)
- `delivery_channel`: Enum (`IN_APP`, `EMAIL`, `PUSH`)
- `is_active`: Boolean flag

### `NotificationModel` (`notifications`)
Discrete notification instances generated for researchers:
- `profile_id`: Recipient researcher profile ID
- `notification_type`: Typed taxonomy (`DEADLINE_UPCOMING`, `DEADLINE_TODAY`, `DEADLINE_EXTENDED`, `DEADLINE_MOVED_EARLIER`, `DEADLINE_CONFLICT`, `CALENDAR_EVENT_UPCOMING`, `SUBMISSION_STATUS_CHANGE`, `SYSTEM`)
- `title` & `body`: Human-readable alert text
- `source_type`: `OPPORTUNITY`, `CALENDAR_EVENT`, `SUBMISSION`, `SYSTEM`
- `source_id`, `opportunity_id`, `calendar_event_id`, `submission_id`: Source references
- `deadline_type`: Milestone type (e.g. `SUBMISSION`, `ABSTRACT`, `CAMERA_READY`)
- `scheduled_for`: Scheduled delivery instant (UTC)
- `delivered_at` & `read_at`: Timestamps for delivery and user read state
- `delivery_status`: `PENDING`, `DELIVERED`, `FAILED`, `CANCELLED`, `SKIPPED`
- `delivery_channel`: `IN_APP`, `EMAIL`, `PUSH`
- `deduplication_key`: Unique deterministic SHA-256 hash
- `metadata_json`: Contextual payload (opportunity title, canonical deadline, original timezone, venue)

### `NotificationDeliveryAttemptModel` (`notification_delivery_attempts`)
Immutable delivery audit log:
- `notification_id`: Foreign key referencing `notifications.id`
- `channel`: Channel used (`IN_APP`, `EMAIL`, `PUSH`)
- `attempt_number`: Sequential attempt integer (1, 2, ...)
- `status`: `DELIVERED`, `FAILED`, `PENDING`
- `provider_reference`: External delivery receipt / message ID
- `error_message`: Scrubbed error information (no secrets or credentials)
- `attempted_at`: Timestamp (UTC)

---

## 3. Idempotency & Deduplication Engine

The scheduler may execute periodically (every minute, 5 minutes, or hourly) or restart upon system redeployment. To guarantee **0 duplicate notifications**, every notification computes a deterministic SHA-256 hash:

$$\text{Key} = \text{SHA256}(\text{profile\_id} : \text{source\_type} : \text{source\_id} : \text{milestone} : \text{rule\_id} : \text{channel} : \text{target\_utc} : \text{type})$$

### Invariant Guarantees:
1. **Uniqueness Constraint**: Enforced at the database level via `uq_notifications_deduplication_key`.
2. **In-Memory Cache**: During scheduler evaluation, all existing deduplication keys are loaded in O(1) sets, eliminating database roundtrips.
3. **Repeated Runs**: Subsequent runs with identical inputs produce 0 created notifications and increment `skipped_duplicates`.

---

## 4. Milestone Isolation & Deadline Revision Intelligence

### Milestone Isolation:
- An `EVENT_START` never generates a paper submission reminder.
- A `NOTIFICATION` date is never conflated with a submission deadline.
- A `CAMERA_READY` deadline never replaces a paper submission deadline.
- `REGISTRATION` deadlines remain strictly isolated to registration activities.

### Revision Intelligence:
- **Extensions (`EXTENDED`)**: When an authoritative source announces an extension (e.g., Aug 20 → Aug 27), the system creates a `DEADLINE_EXTENDED` notification and calculates future reminders based on the new target UTC instant without duplicating past notifications.
- **Moved Earlier (`MOVED_EARLIER`)**: Alerts the researcher to review their submission timeline and recalculates future reminders.
- **Unresolved Conflicts (`SOURCE_CONFLICT`)**: When two equal-authority sources disagree, the system **never fabricates a winner** and surfaces an informational `DEADLINE_CONFLICT` alert.

---

## 5. Scheduler & Bounded Database Complexity (Zero N+1)

The `ReminderSchedulerService.run_scheduled_reminders` engine is designed with bounded query complexity:
1. **Bulk Ingestion**: Profile preferences, active rules, saved opportunities, and existing notifications are loaded in chunked batches (chunks of 400), avoiding SQLite parameter limits and eliminating N+1 queries.
2. **Canonical View Caching**: When multiple researchers track the same opportunity, canonical resolution is cached per opportunity ID, avoiding duplicate evidence extraction.
3. **Single Transaction Commit**: All generated notifications and delivery attempts are flushed and committed in a single transaction pass.

### Benchmarks (In-Memory SQLite on Windows):
| Researcher Scale | Run 1 (Eval + Creation) | Per-User Latency | Run 2 (Deduplication) | Per-User Latency |
|:---|:---|:---|:---|:---|
| **10 Researchers** | 22.15 ms | 2.215 ms | 5.26 ms | 0.526 ms |
| **50 Researchers** | 45.91 ms | 0.918 ms | 19.28 ms | 0.386 ms |
| **100 Researchers** | 79.85 ms | 0.798 ms | 35.64 ms | 0.356 ms |
| **500 Researchers** | 361.55 ms | 0.723 ms | 165.62 ms | 0.331 ms |
| **1,000 Researchers** | 728.80 ms | 0.729 ms | 331.80 ms | 0.332 ms |

---

## 6. REST API Endpoints

All endpoints require authentication and enforce strict `X-User-ID` researcher ownership. Cross-tenant access returns `403 Forbidden`.

### User-Scoped Notification Endpoints
- `GET /api/v1/notifications`: List notifications with pagination, `unread_only`, and `notification_type` filters.
- `GET /api/v1/notifications/unread-count`: Fast unread notification counter for navigation badges.
- `POST /api/v1/notifications/{id}/read`: Mark a single notification as read.
- `POST /api/v1/notifications/read-all`: Mark all unread notifications as read.
- `GET /api/v1/notifications/preferences`: Retrieve notification preferences.
- `PATCH /api/v1/notifications/preferences`: Update delivery channels and category toggles.
- `GET /api/v1/notifications/rules`: List configured reminder rules.
- `POST /api/v1/notifications/rules`: Create a new reminder rule.
- `PATCH /api/v1/notifications/rules/{id}`: Update an existing reminder rule.
- `DELETE /api/v1/notifications/rules/{id}`: Delete a reminder rule (204 No Content).
- `POST /api/v1/notifications/trigger-reminders`: Manually trigger scheduler evaluation pass.

### Researcher-Scoped Endpoints
- `GET /api/v1/researchers/{id}/notifications`
- `POST /api/v1/researchers/{id}/notifications/{notification_id}/read`
- `POST /api/v1/researchers/{id}/notifications/read-all`
- `GET /api/v1/researchers/{id}/notification-preferences`
- `PATCH /api/v1/researchers/{id}/notification-preferences`
- `GET /api/v1/researchers/{id}/reminder-rules`
- `POST /api/v1/researchers/{id}/reminder-rules`
- `PATCH /api/v1/researchers/{id}/reminder-rules/{rule_id}`
- `DELETE /api/v1/researchers/{id}/reminder-rules/{rule_id}`

---

## 7. Frontend User Experience

### Notification Center (`/notifications`)
- Complete alert stream with unread visual indicators and category icons.
- Filter tabs for "All Alerts" and "Unread" with dynamic counts.
- Milestone and venue badges with links directly to `/workspace` or `/calendar`.
- One-click "Mark All Read" and individual "Mark Read" actions.
- "Evaluate Now" button for testing reminder triggers.

### Notification Preferences (`/settings/notifications`)
- Channel toggles for In-App and Email notifications.
- Category toggles for Upcoming Deadlines, Extensions, Conflicts, and Planning Events.
- Reminder rule manager: Add, view, pause, or delete custom advance reminder offsets.

### Navigation Integration (`DiscoveryNavbar.tsx`)
- Integrated `Bell` icon link to `/notifications` with active path detection.

---

## 8. Safety Invariants Verified

| Invariant | Description | Status |
|:---|:---|:---|
| **Inv 1 & 2** | Missing, ambiguous, or invalid deadlines do not schedule reminders | **VERIFIED** |
| **Inv 3 & 4** | Invalid/unknown timezones do not silently default to UTC without flag | **VERIFIED** |
| **Inv 5 to 8** | Milestone isolation: Event start, notification, camera-ready never confuse submission | **VERIFIED** |
| **Inv 9** | Equal-authority conflicts do not fabricate deadline reminders | **VERIFIED** |
| **Inv 10** | Higher-authority supersession follows Phase 2.7 semantics | **VERIFIED** |
| **Inv 11 & 12** | Deadline extensions recalculate reminders without duplicates | **VERIFIED** |
| **Inv 13** | Deadline moved earlier recalculates reminders | **VERIFIED** |
| **Inv 14** | Equivalent temporal representations do not create duplicate reminders | **VERIFIED** |
| **Inv 15** | Repeated scheduler execution is 100% idempotent (0 duplicate notifications) | **VERIFIED** |
| **Inv 16 & 17** | Failed delivery can be retried safely; successful delivery is not repeated | **VERIFIED** |
| **Inv 18** | Disabled notification channel prevents delivery | **VERIFIED** |
| **Inv 19 & 20** | Cross-researcher notification and rule access returns 403 Forbidden | **VERIFIED** |
| **Inv 21 to 26** | Zero mutation of calendar, canonical evidence, ranking, risk, personalization | **VERIFIED** |
| **Inv 27 & 28** | Zero LLM calls and zero external network calls during scheduling | **VERIFIED** |
| **Inv 29** | Identical inputs produce deterministic scheduling decisions | **VERIFIED** |
| **Inv 30 & 31** | No silent loss of notification history or delivery attempt records | **VERIFIED** |
| **Inv 32** | No duplicate notifications from worker retries | **VERIFIED** |

---

## 9. Deferred Functionality (Strict Phase Boundaries)

The following capabilities are strictly deferred to future phases:
- Automatic paper uploading or portal form submission (Phase 5.x).
- External conference portal credential storage.
- Headless browser automation for external portals.
- Collaborative multi-user team notifications (Phase 4.6).
- Changes to ranking, scoring, or personalization recommendation algorithms.
