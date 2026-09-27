# Phase 6.4 — Production Configuration

Phase 6.4 audits and hardens the production configuration. The Phase 6 specification
defines the scope:

- **Audit** secrets, environment variables, CORS, JWT configuration, database credentials,
  debug mode, logging, the frontend API URL, scheduler settings and seed-data settings.
- **No secrets** in source, Dockerfiles, committed `.env` files or frontend bundles.
- **Development defaults must not silently become production authentication bypasses.**

The Phase 6 reconnaissance also assigned two follow-ups here: the development template's
contradicting developer-identity default (D3), and a production configuration reference,
which is this document.

---

## 1. Audit findings and changes

Each finding was reproduced against the code before it was changed.

| Area | Found | Now |
|---|---|---|
| Development defaults vs production | `APP_ENV` was compared to the exact string `production`. `Production`, `prod` or `" production"` skipped every production check, so `AUTH_DEV_IDENTITY_ENABLED=true` (spoofable `X-User-ID` identity) and an ephemeral key were accepted. | `APP_ENV` is trimmed, lowercased and limited to `development`, `test` or `production`. Any other value is a startup error. |
| JWT algorithm | Any string. `none` or `RS256` started, then every login failed. | `HS256`, `HS384` or `HS512` only. |
| Token lifetime | Unbounded. `0` expired every token; 10 years was accepted. | 1 minute to 7 days (there is no revocation). |
| Password hashing | bcrypt cost 4 (the test value) was accepted in production. | 4-31 everywhere; at least 10 in production. |
| Signing secret | Any 32 characters, such as 32×`a`, were accepted in production. | At least 32 characters and at least 10 distinct characters in production. |
| CORS | `["*"]` was accepted in production, and any site's preflight was answered with its own origin plus `credentials: true`. A trailing slash silently broke the frontend. | Exact origins only: lowercase `scheme://host[:port]`, no wildcard, credentials, path, query or trailing slash. Enforced in every environment. |
| Database credentials | With `DATABASE_URL` unset, production silently used the built-in development URL and its well-known password. | Production refuses the development password, whether it comes from the built-in default or an explicit URL. |
| Logging | An unknown level crashed at startup with a bare `ValueError`; an unknown format silently fell back to text. | Both are validated (case-insensitive). `DEBUG` in production logs a startup warning. |
| Debug surface | `/docs`, `/redoc` and `/openapi.json` were served in production; responses carried `server: uvicorn` and `X-Powered-By: Next.js`. | Docs are off in production unless `API_DOCS_ENABLED=true`; both headers are removed. |
| Frontend API URL | Never validated. | Must be an absolute http(s) URL without credentials, query or fragment, or `next build` fails. A trailing slash is removed. |
| Scheduler settings | Validated in 6.3. But Compose v5 sent SIGKILL about 3 s into a stop, before the scheduler's 5 s shutdown wait. | The backend's `stop_grace_period: 15s`. |
| Seed data | The seeder created an ADMIN with the README's public password in production-mode containers, and it logged whatever password it was given. | In production `--password` is required and the public password is refused. Any supplied password must pass the registration policy, and a chosen password is never logged. The seeder never updates an account it did not create: if a demo email belongs to any other account, such as one registered through the API, it stops before writing anything (audit finding P2-1). |
| Development template (D3) | `backend/.env.example` enabled developer identity although the settings default and the README say it is opt-in. | The template leaves it off. |
| Secrets in the repository | None found in source, templates, Dockerfiles or bundles (see 5). | Locked in by tests. |

## 2. Where each check runs

- **Settings construction:** field types, ranges, closed value sets and the CORS format are
  checked when `Settings` is built. That covers every entry point: the API, the scheduler,
  the seeder, `wait_for_db` and Alembic. An invalid value stops the process before it does
  anything.
- **Application startup:** the production-only rules run in
  `validate_security_settings()`, when the API starts. They report every problem in one
  error, never including the secret itself:

  ```
  Refusing to start with APP_ENV=production: AUTH_SECRET_KEY must be at least 32
  characters; AUTH_DEV_IDENTITY_ENABLED must be false; AUTH_BCRYPT_ROUNDS must be at least
  10; DATABASE_URL must be set explicitly; the built-in development credentials are not
  accepted.
  ```
- **Frontend build:** the frontend URL rules run in `next.config.ts` during `next build`.

## 3. Configuration reference

**Backend settings** (environment variables; `backend/.env` when run on the host):

| Variable | Default | Allowed | Production rule |
|---|---|---|---|
| `APP_ENV` | `development` (`production` in Compose) | `development`, `test`, `production` (case-insensitive) | `production` enables the rules below |
| `AUTH_SECRET_KEY` | empty (ephemeral key outside production) | any | Required: at least 32 characters and at least 10 distinct |
| `AUTH_ALGORITHM` | `HS256` | `HS256`, `HS384`, `HS512` | — |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | 1-10080 | — |
| `AUTH_BCRYPT_ROUNDS` | `12` | 4-31 | at least 10 |
| `AUTH_LOGIN_RATE_LIMIT_PER_MINUTE` | `10` | at least 1 | — |
| `AUTH_DEV_IDENTITY_ENABLED` | `false` | bool | must be `false` (Compose pins it) |
| `DATABASE_URL` | the local development URL | SQLAlchemy URL | Must not use the development password |
| `CORS_ORIGINS` | `["http://localhost:3000","http://127.0.0.1:3000"]` | JSON list of exact origins | — |
| `TRUST_PROXY_HEADERS` | `false` | bool | `true` only behind a proxy that overwrites the forwarding headers |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `DEBUG` logs a startup warning |
| `LOG_FORMAT` | `text` | `text`, `json` | — |
| `API_DOCS_ENABLED` | unset: on outside production, off in production | bool | — |
| `DISCOVERY_RATE_LIMIT_PER_MINUTE` | `60` | at least 1 | — |
| `SCHEDULER_*` | off | see [Phase 6.3](phase6-3-scheduler.md) | enable in one process only |

**Compose and frontend:**

| Variable | Where | Rule |
|---|---|---|
| `POSTGRES_PASSWORD` | root `.env` | Required by Compose; URL-safe characters |
| `NEXT_PUBLIC_API_URL` | frontend build argument | Public by definition: an absolute http(s) URL, no credentials, query or fragment |

## 4. Deployment checklist

1. `cp .env.example .env`, then set `POSTGRES_PASSWORD` and `AUTH_SECRET_KEY`, generated with
   `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
2. Keep `APP_ENV=production`.
3. For access from other machines:
   - set `CORS_ORIGINS` to the exact frontend origin(s) and `NEXT_PUBLIC_API_URL` to the address
     browsers use for the API, then rebuild the frontend;
   - terminate TLS at a reverse proxy, and set `TRUST_PROXY_HEADERS=true` only if that proxy
     overwrites the forwarding headers.
4. `docker compose up --build -d --wait`. If the backend exits, its log line lists every
   setting to fix.
5. Demo data is optional: `docker compose exec backend python -m scripts.seed_demo_data
   --password '<your password>'`. The public demo password is refused in production.
6. Leave `API_DOCS_ENABLED` and `SCHEDULER_OPPORTUNITY_REFRESH_ENABLED` off unless you need them.
   Enable `SCHEDULER_ENABLED` in one backend process only.

## 5. Secrets policy

- **Runtime secrets.** `POSTGRES_PASSWORD` and `AUTH_SECRET_KEY` exist only in the git-ignored
  root `.env` and in the environment of the containers that need them. The frontend receives
  none; migrate receives only the database URL.
- **Templates.** Both `.env.example` files ship empty secrets and a `CHANGE_ME` database
  password. The settings class has no default secret.
- **Dockerfiles.** No `ENV` or `ARG` carries a secret; every value arrives at runtime.
- **The frontend bundle.** It contains exactly one environment value, `NEXT_PUBLIC_API_URL`,
  and the build refuses one with embedded credentials.
- **Logs.** Startup errors name the setting, never its value. The seeder never logs a chosen
  password, and `wait_for_db` masks the database password.

## 6. Tests

- **`backend/tests/test_production_config.py`** (76 tests):
  - settings validation in every environment;
  - every production startup rule, and all problems reported together;
  - the capitalized-`APP_ENV` bypass;
  - the real application refusing insecure configuration at import;
  - docs hidden in production;
  - the seeder refusing the public password and never logging a chosen one;
  - committed templates, Compose and Dockerfiles carrying no secret or bypass;
  - the stop grace outlasting the scheduler's shutdown wait.
- **`frontend/tests/next-config.test.ts`** (15 tests): API-URL validation and normalization, no
  `X-Powered-By`, and only the API URL in the bundle environment.
- **`backend/tests/test_seed_demo_account_takeover.py`** (13 tests, audit finding P2-1): an
  account registered under a demo email keeps its role, password and verification when the
  seeder runs; its existing token gains nothing; legitimate reruns, `--dry-run` and `--reset`
  keep their behaviour.

## 7. Limitations

- The secret check is a floor, not an entropy measurement. It rejects placeholders and
  repetition, not every weak value; use a generated secret.
- `CORS_ORIGINS`, `TRUST_PROXY_HEADERS` and `NEXT_PUBLIC_API_URL` describe the deployment's
  topology. The backend cannot tell whether they are right for the network in front of it.
- Individual tokens cannot be revoked. Deactivating an account blocks all of its tokens at once,
  because the user row is re-read on every request, and rotating `AUTH_SECRET_KEY` signs
  everybody out. The 7-day cap limits how long a leaked token stays usable.
- `test` behaves like `development`; it exists so test runs can name themselves.
