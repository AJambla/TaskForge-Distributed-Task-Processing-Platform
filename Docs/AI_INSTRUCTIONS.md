# AI_INSTRUCTIONS.md — Project-Level AI Engineering Constitution

This file governs how any AI coding agent (including future Claude sessions) should work on TaskForge. Read this before making any change.

## Project Context

**TaskForge** is a distributed task processing platform: developers submit tasks (email send, image resize, webhook delivery) via a FastAPI REST API; tasks are queued in RabbitMQ; a horizontally scalable worker pool consumes and executes them with retries, backoff, and dead-lettering; PostgreSQL is the durable source of truth; Redis handles idempotency/locks/rate-limiting; React (TypeScript, Tailwind, React Query) is the dashboard. Deployed via Docker Compose locally and a managed PaaS in production. Full detail lives in the other files in `/docs` — this file assumes you've read `ARCHITECTURE.md` and `DATABASE.md` at minimum before touching task-lifecycle code.

**Core technologies:** Python/FastAPI, PostgreSQL, Redis, RabbitMQ, React/TypeScript, Docker, Prometheus/Grafana. See `TECHSTACK.md` for the reasoning behind each choice — do not introduce a replacement or an additional technology in the same category without a documented, discussed reason.

## Coding Rules

The AI must:
- Follow the existing architecture described in `ARCHITECTURE.md`. If a change requires deviating from it, update the document as part of the same change — never let code and docs diverge.
- Avoid unnecessary dependencies. Adding a new library is a deliberate decision, not a default; check `TECHSTACK.md`'s "Explicitly Not Used" section before reaching for something already considered and rejected.
- Avoid unnecessary rewrites. Prefer the smallest change that correctly solves the stated problem.
- Preserve backward compatibility, especially on the API (see API Rules below).
- Write production-quality code: typed (Python type hints, TypeScript strict mode), readable, and consistent with existing patterns in the codebase.
- Handle errors explicitly — no bare `except:` clauses, no silently swallowed promise rejections; every failure path should either recover, retry, or surface clearly (log + appropriate HTTP status / task outcome).
- Validate all external input at the boundary (API request bodies, task payloads) before it reaches business logic — this is a security requirement, not a style preference (see `SECURITY.md`).
- Never expose secrets — not in code, not in logs, not in error messages returned to clients.

## Distributed System Rules

Before touching anything in the task/worker/queue path, the AI must understand:
- **Task lifecycle** (`ARCHITECTURE.md` § Task Lifecycle) — the full state machine and what triggers each transition.
- **Worker lifecycle** — registration, heartbeat, offline detection, and how this is *separate* from AMQP-level redelivery (don't conflate the two mechanisms).
- **Queue semantics** — manual acks, retry-queue TTL-based backoff, DLQ routing; these are RabbitMQ features being used deliberately, not incidental.
- **Retry behavior and idempotency** — the two-layer (Redis + Postgres) idempotency design and why both layers exist (see `DATABASE.md`).
- **Failure handling** — the full failure-scenario table in `ARCHITECTURE.md`; any code change touching worker/API/broker interaction should be checked against that table for regressions.
- **Concurrency, timeouts, backpressure** — per-worker concurrency limits and per-task-type timeouts are safety mechanisms, not arbitrary config; don't remove or bypass them without updating the relevant doc and explaining the trade-off.

**Never modify distributed-system behavior (retry logic, ack timing, idempotency checks, timeout values) without first explaining the impact** — what changes for a client, for a worker crash scenario, for the guarantees table in `ARCHITECTURE.md`. If the change alters a guarantee (e.g. moving from at-least-once toward something else), that table must be updated in the same change.

## API Rules

- Version APIs — a breaking change gets a new `/api/v2` path, per `API.md` § Versioning; never break `/api/v1` in place.
- Validate every request with a Pydantic schema; never accept unvalidated JSON into business logic.
- Keep response shapes consistent with `API.md` — same field naming conventions, same pagination envelope, same error shape (`{"error": {"code", "message", "field"}}`) across all endpoints.
- Enforce authentication and authorization on every endpoint except the explicitly public ones (`/auth/register`, `/auth/login`, `/healthz`, `/api/v1/metrics`) — when adding a new endpoint, default to requiring auth and explicitly justify any exception.
- Respect and extend rate limiting rather than bypassing it for new endpoints.

## Database Rules

- Use Alembic migrations for every schema change — never modify the production schema by hand, and never let application code auto-create/alter tables at runtime.
- Add indexes intentionally, tied to an actual query pattern (see `DATABASE.md` for the reasoning behind each existing index) — don't index speculatively, and don't skip an index that a new frequent query pattern clearly needs.
- Avoid N+1 queries, especially in list endpoints (`GET /tasks`, `GET /workers`) and the attempt-history join for Task Detail.
- Preserve data integrity — foreign keys, `CHECK` constraints, and the idempotency unique constraint are load-bearing, not incidental; don't relax them to work around a bug without understanding why the constraint existed.
- Use transactions where multiple writes must succeed or fail together (e.g. task insert + attempt update in the same logical operation).

## Security Rules

The AI must never:
- Hardcode secrets (API keys, DB passwords, JWT signing keys) in code or config committed to the repo.
- Log passwords, raw API keys, or JWT tokens — log identifiers (user ID, key ID/prefix) instead.
- Disable authentication or authorization "temporarily" for convenience/debugging in code that could be merged.
- Trust user input — every task payload field, every query parameter, every header value is untrusted until validated.
- Execute arbitrary user-supplied code — this project's scope explicitly excludes that; if a request seems to require it, flag the scope conflict rather than building it.
- Weaken or bypass the SSRF protections on `image_resize`/`webhook_delivery` handlers (private-IP blocking, redirect validation) without a security-reviewed reason documented in `SECURITY.md`.

## Testing Rules

Every meaningful feature change should include, as applicable:
- **Unit tests** for new logic (handler functions, retry/backoff calculation, schema validation).
- **Integration tests** for anything touching the task lifecycle — run against real Postgres/RabbitMQ/Redis (via the project's test-container setup), not mocks, since the whole point of this system is the interaction between these components.
- **API tests** for new/changed endpoints, covering both success and the relevant error paths (auth failure, validation failure, not-found, conflict).
- **Failure tests** for anything in the distributed-systems path — e.g. "worker crashes mid-task → task is redelivered, not lost" should be an actual test, not just a design claim in `ARCHITECTURE.md`.
- **Concurrency tests** where relevant (e.g. two simultaneous submissions with the same idempotency key should result in exactly one task).

## Documentation Rules

When changing:
- **Architecture** → update `ARCHITECTURE.md`.
- **APIs** → update `API.md`.
- **Database** → update `DATABASE.md`.
- **Infrastructure/deployment** → update `DEPLOYMENT.md`.
- **Security posture** → update `SECURITY.md`.

Docs and code must never silently diverge. If a change is large enough to touch multiple docs, update all of them in the same change, not as a follow-up.

## Git Rules

- Small, focused commits — one logical change per commit.
- Conventional commit messages (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Feature branches per change, merged via pull-request-style review (even if self-reviewed on a solo project) rather than direct commits to `main` for anything non-trivial.

## AI Workflow

Before modifying code, follow this sequence:

```text
1. Understand the requirement — what is actually being asked, and why.
2. Inspect existing architecture — read the relevant docs (ARCHITECTURE.md,
   DATABASE.md, API.md, SECURITY.md as applicable) before writing code.
3. Identify affected components — API, worker, scheduler, frontend,
   database schema, docs.
4. Identify risks — especially for anything touching the task lifecycle,
   retry/idempotency logic, or security-sensitive input handling.
5. Propose the implementation — briefly state the approach, especially if
   it involves a trade-off or a deviation from documented architecture.
6. Implement.
7. Test — per the Testing Rules above.
8. Review — check against this file's rules before considering the change done.
9. Update documentation — per the Documentation Rules above.
```

The AI should never blindly modify files, especially in the task lifecycle, retry/idempotency, or security-validation code paths — these are the parts of the system where a "small, obviously correct" change can silently break a distributed-systems guarantee. When in doubt, state the trade-off and ask rather than guessing.
