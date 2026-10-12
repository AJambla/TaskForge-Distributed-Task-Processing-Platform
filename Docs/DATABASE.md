# DATABASE.md — Database Design

## Database Choice

**PostgreSQL** is the system of record for all durable state: users, API keys, tasks, and task attempts. It was chosen over a NoSQL store because task data is inherently relational (a task belongs to a user, has many attempts, and its state must be updated transactionally and consistently), and because strong consistency matters more here than horizontal write scale at the target load (50–100 tasks/sec is comfortably within a single well-indexed Postgres instance's capability).

**Redis** holds transient/coordination data only: idempotency-key lookups, distributed locks, and rate-limit counters. It is deliberately not used to store anything that must survive a Redis restart without consequence — see "What Redis Does Not Store" below.

**RabbitMQ** holds in-flight queue state (messages currently queued or awaiting redelivery) — not modeled here as it isn't a database, but its relationship to the Postgres `tasks`/`task_attempts` tables is covered under "Queue Metadata."

## Entity-Relationship Overview

```text
User
 │
 ├── APIKey        (many)
 │
 └── Task           (many)
       │
       ├── TaskAttempt  (many)
       │
       └── (references) WorkerRegistration  — via TaskAttempt.worker_id
```

`WorkerRegistration` is not owned by a user — workers are system-level entities, visible to admins.

## Tables

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `email` | TEXT | Unique, not null |
| `password_hash` | TEXT | bcrypt/argon2 hash, not null |
| `role` | TEXT | `'user'` \| `'admin'`, default `'user'` |
| `created_at` | TIMESTAMPTZ | default `now()` |

### `api_keys`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → `users.id`, not null |
| `name` | TEXT | User-provided label, not null |
| `key_hash` | TEXT | SHA-256 hash of the key; raw key is never stored, not null |
| `key_prefix` | TEXT | First few chars of the key, shown in the UI for identification without exposing the full key |
| `created_at` | TIMESTAMPTZ | default `now()` |
| `last_used_at` | TIMESTAMPTZ | nullable, updated on authenticated requests (debounced and buffered in Redis with a 60s window to avoid DB write amplification) |
| `revoked_at` | TIMESTAMPTZ | nullable; a non-null value means the key is inactive |

**Index:** `key_hash` (unique) — required for fast auth lookups on every API request.

### `tasks`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → `users.id`, not null |
| `task_type` | TEXT | `'email_send'` \| `'image_resize'` \| `'webhook_delivery'`, not null |
| `payload` | JSONB | Validated task-type-specific input, not null |
| `status` | TEXT | `'queued'` \| `'running'` \| `'succeeded'` \| `'failed'` \| `'retrying'` \| `'dead_letter'` \| `'cancelled'`, not null |
| `priority` | SMALLINT | default `0`; higher = more urgent (Phase 2 feature) |
| `idempotency_key` | TEXT | nullable; unique per `user_id` when present |
| `max_attempts` | SMALLINT | default from system config, overridable per task |
| `attempt_count` | SMALLINT | default `0`, incremented per attempt |
| `run_at` | TIMESTAMPTZ | for delayed/scheduled tasks; default `now()` |
| `recurrence_rule` | TEXT | nullable, cron-style expression for recurring tasks |
| `created_at` | TIMESTAMPTZ | default `now()` |
| `started_at` | TIMESTAMPTZ | nullable, set on first attempt pickup |
| `completed_at` | TIMESTAMPTZ | nullable, set on terminal state |

**Indexes:**
- `(user_id, status)` — task-list filtering per user.
- `(status, run_at)` — used by the scheduler/worker pickup path.
- Unique `(user_id, idempotency_key)` where `idempotency_key IS NOT NULL` — enforces idempotency at the database level, not just via a Redis check.

**Constraint:** `status` restricted via `CHECK` to the enumerated values above.

### `task_attempts`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `task_id` | UUID | FK → `tasks.id`, not null |
| `attempt_number` | SMALLINT | not null |
| `worker_id` | UUID | FK → `worker_registrations.id`, nullable (null if never picked up) |
| `started_at` | TIMESTAMPTZ | not null |
| `finished_at` | TIMESTAMPTZ | nullable |
| `outcome` | TEXT | `'success'` \| `'failure'` \| `'timeout'`, nullable until finished |
| `error_message` | TEXT | nullable |
| `error_detail` | JSONB | nullable, structured error info (e.g. stack trace, sanitized) |

**Index:** `(task_id, attempt_number)` — attempt-history retrieval for Task Detail view.

### `worker_registrations`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `hostname` | TEXT | Container/host identifier, not null |
| `status` | TEXT | `'online'` \| `'offline'` \| `'draining'`, not null |
| `concurrency_limit` | SMALLINT | not null |
| `current_task_count` | SMALLINT | default `0` |
| `registered_at` | TIMESTAMPTZ | default `now()` |
| `last_heartbeat_at` | TIMESTAMPTZ | not null, updated on each heartbeat |
| `tasks_processed` | INTEGER | default `0`, lifetime counter |
| `tasks_failed` | INTEGER | default `0`, lifetime counter |

**Index:** `last_heartbeat_at` — used by a periodic job to mark workers `offline` after a missed-heartbeat threshold.

## Retention Policy

- `task_attempts` and `tasks`: retained for a configurable window (default 90 days) before archival/deletion, to bound table growth from this being a portfolio/demo system with no real data-retention requirement driving it.
- `worker_registrations`: rows for workers offline longer than 7 days are purged; lifetime counters are not preserved beyond that (acceptable for this project's scope — an audit-grade worker history is not a stated requirement).

## Audit Data

- `task_attempts` itself functions as the audit trail for task execution — every attempt, regardless of outcome, is a permanent record until the retention window purges it.
- Authentication events (login, API key creation/revocation) are logged to application logs (see DEPLOYMENT.md § Monitoring) rather than a dedicated audit table, since this system does not have a compliance requirement driving structured audit-log storage.

## Redis Data Structures

| Purpose | Structure | Key pattern | Notes |
|---|---|---|---|
| Idempotency check | String (SETNX-style) | `idem:{user_id}:{idempotency_key}` | Set with a TTL matching the task's expected max lifetime; existence check happens before a task is queued, backed by the Postgres unique constraint as the authoritative guard against races. |
| Distributed lock (scheduler) | String with TTL, via `SET key value NX PX <ttl>` | `lock:scheduler:scan` | Prevents multiple scheduler instances from double-firing task scans and duplicate scheduling runs. |
| Rate limiting | Sorted set or fixed-window counter | `ratelimit:{api_key_id}:{window}` | Token/fixed-window counter per API key, per time window, per SECURITY.md's rate-limiting policy. |
| Worker heartbeat cache (optional, read-optimization) | Hash | `worker:heartbeat:{worker_id}` | Optional fast-path cache mirroring `worker_registrations.last_heartbeat_at`, to avoid hammering Postgres on every dashboard poll; Postgres remains authoritative. |

### What Redis Does Not Store

Redis is explicitly **not** the source of truth for task state, task history, or worker identity — all of that lives in Postgres. If Redis is flushed or restarted, the system loses only: in-flight idempotency-key caches (worst case, a very narrow race window could allow one duplicate task, mitigated by the Postgres unique constraint), active locks (worst case, a brief double-fire of a recurring task scheduler, which is a low-severity, self-correcting issue at this scale), and rate-limit counters (worst case, a brief rate-limit reset). No task is ever lost due to a Redis failure.

## Queue Metadata (RabbitMQ)

RabbitMQ owns three logical queues per task type:

- **Main queue** (`tasks.{task_type}`) — normal task delivery.
- **Retry queue** (`tasks.{task_type}.retry`) — messages held here with a per-attempt TTL (implementing exponential backoff) before being dead-lettered back into the main queue.
- **Dead-letter queue** (`tasks.{task_type}.dlq`) — terminal home for tasks that exhausted `max_attempts`.

RabbitMQ message bodies carry only the `task_id` (not the full payload) — the worker fetches the authoritative task row (including payload) from Postgres upon pickup. This avoids ever having two divergent copies of task payload data and keeps message bodies small.

## Key Design Decisions

- **Normalization:** `task_attempts` is kept as a separate table from `tasks` (rather than an array/JSONB column on `tasks`) so that attempts can be indexed, queried, and joined against `worker_registrations` independently — required for both the Task Detail attempt timeline and the Worker Detail "recent tasks processed" view.
- **JSONB for `payload`:** Task payloads vary by `task_type`; JSONB avoids a sparse, wide `tasks` table while still allowing indexed queries (via GIN index) if a specific payload field ever needs to be queried directly — not needed at MVP scope but available.
- **Idempotency enforced at two layers:** a fast Redis check (cheap, catches the common case immediately) plus a Postgres unique constraint (authoritative, catches races under concurrent submission) — a single-layer approach was rejected because Redis alone is not durable/transactional enough to be the sole guarantee, and Postgres alone would be slower on the hot path.
- **Message bodies carry only `task_id`:** rejected the alternative of putting the full payload in the RabbitMQ message, because that would create two sources of truth for payload data and complicate schema evolution (changing a payload shape would require draining in-flight messages of the old shape).
