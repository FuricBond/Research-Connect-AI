# Phase 5.16 — Email Delivery & Live Notifications

Before this phase every notification was in-app only: the email channel went to an in-memory
mock that marked messages "delivered" without sending anything, and the browser only saw new
notifications when the notifications page was opened or reloaded. Phase 5.16 adds real email
over SMTP, a live unread count, and a status header that reports what is actually switched on.

**Email is off by default.** With `EMAIL_PROVIDER=mock` (the default in the settings class,
both `.env.example` files and `docker-compose.yml`) nothing is sent and nothing changes.

Code: `backend/app/services/smtp_email_provider.py`, `backend/app/services/email_dispatch_service.py`,
the `email_dispatch` job in `backend/app/scheduler/jobs.py`, migration
`0031_phase5_16_email_delivery`, and `frontend/hooks/useUnreadNotificationCount.ts`.
Tests: `backend/tests/test_email_delivery.py`, `backend/tests/test_notification_api.py`,
`backend/tests/test_scheduler.py`, `frontend/tests/notification-live-updates.test.tsx`.

---

## 1. How a notification reaches someone

1. A feature creates its in-app notification exactly as before. None of the places that create
   notifications changed.
2. Every minute, the `email_dispatch` scheduler job looks at in-app notifications from the last
   6 hours whose email has not been decided, oldest first, at most 25 a pass.
3. For each it decides once, and records the outcome in `notifications.email_status`:

| Outcome | When |
|---|---|
| `SKIPPED` | not an emailed type, already read in the app, Email Alerts off, inactive account or no address, recipient not allowed, or older than 6 hours |
| `SENT` | the mail server accepted it (`email_sent_at` records when) |
| `RETRY` | the server was unreachable, timed out, refused the login or answered 4xx; tried again next pass |
| `FAILED` | the recipient was refused or the server answered 5xx, or 5 attempts were used |

4. Every send attempt is recorded in `notification_delivery_attempts` with channel `EMAIL`. The
   in-app `delivery_status` and `delivered_at` are never changed by email.
5. The browser asks for the unread count every 30 seconds while the tab is visible, at once when
   the tab comes back, and right after notifications are marked read.

Typical latency: on screen within 30 seconds, by email within about a minute. Deadline reminders
themselves are still created by `reminder_dispatch` every 5 minutes.

### Emailed types

| Emailed | In-app only |
|---|---|
| `DEADLINE_UPCOMING`, `DEADLINE_TODAY`, `DEADLINE_EXTENDED`, `DEADLINE_MOVED_EARLIER`, `DEADLINE_CONFLICT` | `INVITATION_ACCEPTED` |
| `CALENDAR_EVENT_UPCOMING`, `SUBMISSION_STATUS_CHANGE` | `TASK_COMPLETED` |
| `SYSTEM` (application received or changed, refresh-failure alerts) | `DOCUMENT_UPDATED` |
| `WORKSPACE_INVITATION`, `MEMBER_ROLE_CHANGED`, `MEMBER_REMOVED`, `TASK_ASSIGNED` | `COLLABORATION_ACTIVITY` |
| `POSTING_MATCH` | |

With the default reminder rules (14, 7 and 3 days, and 24 hours before) a saved deadline can
produce up to four reminder emails. Each recipient controls all email with the Email Alerts
switch in notification settings.

Each email has a plain-text and an HTML part, links to the page the notification is about
(`/postings/{id}`, `/calendar`, `/workspace` or `/notifications`) under `APP_PUBLIC_URL`, and
links to the notification settings. Stored text is HTML-escaped.

## 2. Safety

- **Recipient allowlist.** `EMAIL_RECIPIENT_ALLOWLIST` lists the addresses and `@domains` that
  may receive email, or `*` for everyone. **Empty means nobody.** The Docker stack runs with
  `APP_ENV=production` on development data, so this, not the environment, is what keeps seeded
  accounts from being mailed. The SMTP provider itself enforces it, so it also covers the older
  Phase 4.5 path where a reminder rule names the `EMAIL` channel.
- **No backlog.** The migration marks every existing notification `SKIPPED`, and anything older
  than 6 hours is skipped, so switching email on never mails old notifications.
- **Bounded work.** At most 25 emails a pass. An unreachable server stops the pass, so an outage
  costs one attempt per pass, not one per notification.
- **At-least-once.** Each email is committed on its own; a crash repeats at most the one email in
  flight.
- **No secrets or addresses in logs.** `SMTP_PASSWORD` is a `SecretStr`. Error messages name the
  SMTP status code or the exception class, never the server's reply text. Logs carry notification
  ids only.
- **Production check.** `APP_ENV=production` refuses `SMTP_SECURITY=none` together with an
  `SMTP_USERNAME`, because the login would cross the network unencrypted.
- **Tests never send.** `tests/conftest.py` forces the mock for every test, even when a local
  `.env` chooses smtp, and every SMTP test replaces `smtplib` with an in-memory fake.

## 3. Configuration

Every key is a backend setting. Both `.env.example` files list all of them except the two tuning
keys (`SMTP_TIMEOUT_SECONDS`, and `SCHEDULER_EMAIL_INTERVAL_SECONDS` in the root template), and
`docker-compose.yml` passes the same ones to the backend container. `smtp` also needs
`SCHEDULER_ENABLED=true`, because the scheduler sends the emails; startup logs a warning when it
is off or when the allowlist is empty.

| Key | Default | Meaning |
|---|---|---|
| `EMAIL_PROVIDER` | `mock` | `mock` or `smtp` |
| `SMTP_HOST` | | required with smtp |
| `SMTP_PORT` | `587` | |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | | no login when the username is empty |
| `SMTP_SECURITY` | `starttls` | `starttls` (587), `ssl` (465) or `none` (a local relay) |
| `SMTP_TIMEOUT_SECONDS` | `10` | per connection |
| `EMAIL_FROM_ADDRESS` | | required with smtp |
| `EMAIL_FROM_NAME` | `ResearchConnect AI` | |
| `EMAIL_RECIPIENT_ALLOWLIST` | empty (nobody) | addresses, `@domains`, or `*` |
| `APP_PUBLIC_URL` | `http://localhost:3000` | base of the links in emails |
| `SCHEDULER_EMAIL_INTERVAL_SECONDS` | `60` | minimum 60 |

**Trying it safely:** a Mailtrap sandbox inbox accepts every email and delivers none. **Gmail:**
`smtp.gmail.com`, port 587, `starttls`, your address as username and sender, and an app password
(Google Account → Security → 2-Step Verification → App passwords). Gmail allows about 500 emails
a day.

## 4. API and interface

- `GET /api/v1/notifications/delivery-status` (signed in): `in_app_enabled`, `email_enabled`
  (the caller's switch), `email_delivery_available` (SMTP on, scheduler on, and the caller's
  address allowed), `reminders_scheduled`, `reminder_interval_seconds`. Booleans and intervals
  only: never a host, address or credential.
- Each notification now includes `email_status` and `email_sent_at`.
- The navbar's Notifications tab shows the unread count. The notifications page refreshes itself,
  reports the channels that actually reach the user and whether reminders are scheduled, marks
  emailed notifications, and shows "Evaluate Now" to administrators only (the only role the API
  accepts it from). Notification settings say when this server does not email.

## 5. Not included

Push notifications stay mock. There is no daily digest and no one-click unsubscribe link: the
email links to settings, which need sign-in. Sending to real users from a public domain also
needs SPF and DKIM records and a `List-Unsubscribe` header, which belong to the deployment.
