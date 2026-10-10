# API.md — API Design

All endpoints are versioned under `/api/v1`. The API is REST over JSON.

## Authentication

Two authentication methods are supported, chosen per-use-case rather than interchangeably:

- **JWT (Bearer token)** — for the dashboard (browser session), obtained via login.
- **API key (Bearer token, `tf_live_...` prefix)** — for programmatic/server-to-server task submission.

Both are passed as `Authorization: Bearer <token>`; the API distinguishes them by token format (JWTs are structurally distinct from the opaque API key format) and validates accordingly.

### `POST /api/v1/auth/register`

- **Auth:** None
- **Body:** `{ "email": "string", "password": "string" }`
- **Response 201:** `{ "id": "uuid", "email": "string" }`
- **Errors:** `400` invalid email/weak password, `409` email already registered.

### `POST /api/v1/auth/login`

- **Auth:** None
- **Body:** `{ "email": "string", "password": "string" }`
- **Response 200:** `{ "access_token": "string", "refresh_token": "string", "expires_in": 900 }`
- **Errors:** `401` invalid credentials.

### `POST /api/v1/auth/refresh`

- **Auth:** Refresh token in body
- **Body:** `{ "refresh_token": "string" }`
- **Response 200:** `{ "access_token": "string", "refresh_token": "string", "token_type": "bearer", "expires_in": 900 }`
- **Behavior:** Issues a new access token and rotates the refresh token (old refresh token is revoked in database).
- **Errors:** `401` invalid/expired refresh token.

### `POST /api/v1/auth/logout`

- **Auth:** JWT
- **Response 204**
- **Behavior:** Invalidates the refresh token server-side (stored/blacklisted).

### API Keys

`POST /api/v1/api-keys` — **Auth:** JWT. Body: `{ "name": "string" }`. Response `201`: `{ "id": "uuid", "name": "string", "key": "tf_live_...", "created_at": "..." }` — full key returned once only.

`GET /api/v1/api-keys` — **Auth:** JWT. Response `200`: list of `{ id, name, key_prefix, created_at, last_used_at, revoked_at }` (no full key ever returned again).

`DELETE /api/v1/api-keys/{key_id}` — **Auth:** JWT, resource ownership enforced. Response `204`. Sets `revoked_at`, does not hard-delete (preserves audit trail).

## Tasks

### `POST /api/v1/tasks`

- **Auth:** API key or JWT
- **Purpose:** Submit a new task.
- **Headers:** `Idempotency-Key` (optional, recommended) — alternative to placing it in the body; query parameter `?Idempotency-Key=...` is also supported for backward compatibility (header takes precedence).
- **Body:**
```json
{
  "task_type": "image_resize",
  "payload": {
    "source_url": "https://example.com/image.jpg",
    "width": 800,
    "height": 600
  },
  "priority": 0,
  "max_attempts": 5,
  "run_at": null,
  "idempotency_key": null
}
```
- **Validation:** `task_type` must be one of the 3 supported types (`email_send`, `image_resize`, `webhook_delivery`); `payload` is validated against a per-type Pydantic schema before the task is persisted or queued.
- **Response 201:**
```json
{
  "id": "9c1f...-uuid",
  "status": "queued",
  "task_type": "image_resize",
  "created_at": "2026-08-29T12:00:00Z"
}
```
- **Errors:** `400` payload fails schema validation, `401` unauthenticated, `409` duplicate idempotency key (returns standard error envelope), `429` rate limit exceeded (with `Retry-After` header) or queue backpressure threshold reached.

### `GET /api/v1/tasks`

- **Auth:** API key or JWT (returns only the caller's own tasks; admins may pass `?all=true`)
- **Query params:** `status`, `task_type`, `created_after`, `created_before`, `page`, `page_size` (default 20, max 100), `sort` (default `-created_at`)
- **Response 200:**
```json
{
  "data": [ { "id": "...", "status": "succeeded", "task_type": "email_send", "created_at": "..." } ],
  "pagination": { "page": 1, "page_size": 20, "total": 143 }
}
```

### `GET /api/v1/tasks/:id`

- **Auth:** API key or JWT, resource ownership enforced (admins exempt)
- **Response 200:** Full task record including `attempts: [...]` (see DATABASE.md `task_attempts` fields).
- **Errors:** `404` not found or not owned by caller.

### `POST /api/v1/tasks/:id/cancel`

- **Auth:** API key or JWT, resource ownership enforced
- **Response 200:** Updated task with `status: "cancelled"`.
- **Errors:** `409` task already running/terminal — cancellation only applies to `queued`/`retrying` tasks; cannot interrupt an in-flight execution.

### `POST /api/v1/tasks/:id/retry`

- **Auth:** API key or JWT, resource ownership enforced (or admin, for DLQ replay)
- **Purpose:** Manually re-queue a `failed` or `dead_letter` task, resetting its attempt path.
- **Response 200:** Updated task with `status: "queued"`.
- **Errors:** `409` task is not in a retryable state (e.g. still `running`).

## Workers

`GET /api/v1/workers` — **Auth:** JWT. Returns worker list per DATABASE.md `worker_registrations` fields. Open to all authenticated users for shared cluster visibility.

`GET /api/v1/workers/{worker_id}` — **Auth:** JWT. Returns worker detail plus recent tasks processed.

## Queues & System

`GET /api/v1/queues` — **Auth:** JWT. Returns per-queue message depths (main, retry, DLQ), throughput rates, and average latency.

`GET /api/v1/queues/dlq` — **Auth:** JWT. Returns dead-letter queue depths, total dead-letter count, and list of up to 50 recent terminal tasks.

`POST /api/v1/queues/dlq/redrive` — **Auth:** JWT. Query params: `task_type` (optional filter), `limit` (default 100, max 500). Re-queues dead-letter tasks into the main processing queue and publishes AMQP messages.

`GET /api/v1/metrics` — **Auth:** None (or IP-restricted, per deployment) — Prometheus scrape endpoint, returns Prometheus text format.

`GET /healthz` — **Auth:** None — liveness/readiness probe verifying database, Redis, and RabbitMQ health.

## Common Error Response Shape

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "payload.width must be a positive integer",
    "field": "payload.width"
  }
}
```

## Standard Status Codes

`200` OK, `201` Created, `204` No Content, `400` Validation error, `401` Unauthenticated, `403` Authenticated but not authorized (e.g. non-admin hitting an admin route), `404` Not found / not owned, `409` Conflict (state conflict, duplicate idempotency key), `429` Rate limited, `500` Unexpected server error.

## Pagination

Offset-based (`page`/`page_size`) for MVP simplicity, given the modest expected data volumes at this project's scale; cursor-based pagination is a documented future improvement if task volume grows large enough for offset pagination's performance characteristics to matter.

## Filtering & Sorting

Supported via query parameters on list endpoints (`GET /tasks`, `GET /workers`); sort direction indicated by a `-` prefix (e.g. `-created_at`). Only indexed columns are sortable/filterable (see DATABASE.md indexes) to avoid full-table scans on large task tables.

## Idempotency

An `Idempotency-Key` on `POST /api/v1/tasks` is scoped per-user. If a request with a previously used key arrives:
- If the original task exists and matches, the API returns `409 Conflict` with error code `DUPLICATE_IDEMPOTENCY_KEY` in the standard error envelope.
- Enforcement is two-layered (Redis fast-path check + Postgres unique constraint on `(user_id, idempotency_key)`) — see DATABASE.md.

## Rate Limiting

Per-API-key fixed-window rate limiting (default: configurable requests/minute, e.g. 60/min for task submission), enforced via the Redis rate-limit counters described in DATABASE.md. Exceeding the limit returns `429` with a `Retry-After` header. Dashboard (JWT) traffic is rate-limited more loosely, scoped per-user rather than per-key.

## Versioning

URL-path versioning (`/api/v1/...`). A breaking change to any endpoint requires a `v2` path rather than an in-place change, preserving backward compatibility for existing integrations — consistent with the "preserve backward compatibility" rule in AI_INSTRUCTIONS.md.

## Webhooks

Not implemented in MVP. Documented here as a Phase 2/future item: an optional `callback_url` field on task submission that the system POSTs to on task completion, secured with an HMAC signature header — deferred because it introduces its own reliability problem (what if the callback fails?) that would need the same retry/DLQ treatment as tasks themselves, and is not required to demonstrate the core distributed-systems story.
