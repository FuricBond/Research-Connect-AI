# Demonstration environment

A separate stack for demonstrating ResearchConnect AI, built from this working tree. It has its own Compose
project (`rcdemo`), database volume (`rcdemo_postgres_data`), ports, image tags and generated secrets, so it can
run beside a development stack and never touches its data.

| Service | Address | Container |
|---|---|---|
| Web | http://localhost:3400 | `rcdemo-frontend-1` |
| API | http://localhost:8400 | `rcdemo-backend-1` |
| Mailbox (sends nothing out) | http://localhost:8425/messages?to=ADDRESS | `rcdemo-mailsink-1` |
| PostgreSQL | 127.0.0.1:5446 | `rcdemo-postgres` |

## Start, check, stop

```bash
python demo/demo.py up
```

This builds fresh images from the working tree, starts everything, applies the migrations, and seeds the demo
accounts. Running it again rebuilds from the current tree and keeps the data.

```bash
python demo/demo.py status
```

This shows container health, the schema revision, and exactly what source the images came from: HEAD, whether
there were uncommitted changes, and a fingerprint of them.

```bash
python demo/demo.py logs backend
```

```bash
python demo/demo.py stop
```

`stop` keeps the data. To start again without rebuilding, use the same `docker compose` command that
`demo.py` runs, with `start` at the end:

```bash
docker compose -p rcdemo --env-file demo/.env.demo -f docker-compose.yml -f demo/compose.demo.yml start
```

Nothing here removes a volume. To discard the demonstration's data on purpose, run `docker compose ... down -v`
with the same `-p rcdemo` arguments. Check the project name first: it decides which volume goes.

## Signing in

| Account | Email | Role |
|---|---|---|
| Student | `demo.student@researchconnect.test` | Confirmed email |
| Faculty | `demo.faculty@researchconnect.test` | Verified, confirmed email |
| Administrator | `demo.admin@researchconnect.test` | Confirmed email |

All three use one generated password: `DEMO_PASSWORD` in `demo/.env.demo`, which git ignores. Sign-in allows
10 attempts a minute per address.

## Email

Email goes to a sink inside the stack and nowhere else. A new account confirms its address like this:

1. On **Notifications** or **Settings**, press **Send the confirmation email**.
2. Open `http://localhost:8425/messages?to=ADDRESS` and open the link in the message, in the same browser.

## What the seed contains

Three accounts, twelve calls for papers with deadlines from "already expired" to "months away" and relative to
the day of seeding (two carry the risk engine's warning signs), and three faculty postings. It holds no real
people or data, **and no research papers**. `docker compose ... exec backend python -m scripts.seed_community --password ...`
adds a larger made-up community for peer discovery.

## Known limits

- **Literature search, similar papers and the reading list have nothing to show**, because the seed has no papers
  and the root README's OpenAlex loading steps need network access. Calls for papers, recommendations and
  everything built on them work. It shows the workflows, and is no measure of retrieval quality.
- Browse cards say "Risk not assessed"; a call's detail page shows the assessed level and its evidence.
- Administrators have no personal research pages or APIs, by design.
- The background scheduler is off, so reminders and refreshes do not run on their own.
