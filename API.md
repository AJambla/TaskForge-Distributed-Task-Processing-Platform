# TaskForge — REST API Reference

All endpoints are versioned under `/api/v1`. The API is RESTful, communicates via JSON, and provides strict Pydantic validation across all request and response schemas.

---

## 1. Authentication & Security

TaskForge supports dual authentication:
- **JWT (Bearer token)**: For interactive dashboard browser sessions, acquired via `/api/v1/auth/login`.
- **API Key (`tf_live_...`)**: For programmatic and server-to-server task submission.

All authenticated requests must include the HTTP header:
```http
Authorization: Bearer <token_or_api_key>
```

### `POST /api/v1/auth/register`
Create a new user account.
- **Auth**: None
- **Body**:
  ```json
  {
    "email": "developer@example.com",
    "password": "StrongPassword123!"
  }
  ```
- **Response 201**:
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "developer@example.com",
    "role": "user",
    "created_at": "2026-10-13T00:00:00Z"
  }
  ```

### `POST /api/v1/auth/login`
Authenticate and obtain JWT access and refresh tokens.
- **Auth**: None
- **Body**:
  ```json
  {
    "email": "developer@example.com",
    "password": "StrongPassword123!"
  }
  ```
- **Response 200**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "d7a4...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```

### `POST /api/v1/auth/refresh`
Rotate refresh token and issue a fresh access token.
- **Auth**: None
- **Body**:
  ```json
  {
    "refresh_token": "d7a4..."
  }
  ```
- **Response 200**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "e8b5...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```

### `POST /api/v1/auth/logout`
Revoke all active refresh tokens for the authenticated user.
- **Auth**: JWT
- **Response 204**: No Content

---

## 2. API Key Management

### `POST /api/v1/api-keys`
Generate a new programmatic API key.
- **Auth**: JWT
- **Body**:
  ```json
  {
    "name": "Production Ingestion Worker"
  }
  ```
- **Response 201**:
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "name": "Production Ingestion Worker",
    "key": "tf_live_a1b2c3d4e5f6...",
    "created_at": "2026-10-13T00:00:00Z"
  }
  ```
  *(Note: The raw key is returned only once at creation and is never stored in plaintext).*

### `GET /api/v1/api-keys`
List active API keys for the current user.
- **Auth**: JWT
- **Response 200**: Array of key metadata objects (prefix, creation time, last used time).

### `DELETE /api/v1/api-keys/{id}`
Revoke an API key.
- **Auth**: JWT
- **Response 204**: No Content

---

## 3. Task Management

### `POST /api/v1/tasks`
Submit a new asynchronous task for execution.
- **Auth**: API Key or JWT
- **Headers**:
  - `Idempotency-Key` *(optional)*: Unique UUID to prevent duplicate submissions.
  - `traceparent` *(optional)*: W3C distributed tracing context header.
- **Body**:
  ```json
  {
    "task_type": "email_send",
    "priority": 8,
    "payload": {
      "recipient": "user@example.com",
      "subject": "System Alert",
      "body": "Your invoice is ready."
    },
    "timeout_seconds": 30,
    "max_retries": 3
  }
  ```
- **Response 201 Created**:
  ```json
  {
    "id": "a50c822e-bb91-4475-b653-53818e6cbe57",
    "task_type": "email_send",
    "status": "queued",
    "priority": 8,
    "payload": { ... },
    "attempt_count": 0,
    "max_attempts": 4,
    "timeout_seconds": 30,
    "created_at": "2026-10-13T00:00:00Z",
    "run_at": "2026-10-13T00:00:00Z"
  }
  ```
- **Response 429 Too Many Requests** *(Backpressure Shedding)*:
  ```json
  {
    "error": {
      "code": "QUEUE_FULL",
      "message": "Task queue saturated, system in backpressure shedding mode",
      "field": null
    }
  }
  ```
  *Headers: `Retry-After: 5`*

### `GET /api/v1/tasks`
List and filter submitted tasks with cursor/offset pagination.
- **Auth**: API Key or JWT
- **Query Parameters**:
  - `status`: Filter by status (`queued`, `running`, `succeeded`, `retrying`, `failed`, `dead_letter`, `cancelled`).
  - `task_type`: Filter by registered handler type.
  - `priority_min` / `priority_max`: Filter by priority range (0–10).
  - `limit`: Number of tasks per page (default: 20, max: 100).
  - `offset`: Offset count.
- **Response 200**:
  ```json
  {
    "items": [ ... ],
    "total": 1420,
    "limit": 20,
    "offset": 0
  }
  ```

### `GET /api/v1/tasks/{id}`
Retrieve complete task status, including the **execution attempt timeline** and **synthesized deterministic failure diagnostics**.
- **Auth**: API Key or JWT
- **Response 200**:
  ```json
  {
    "id": "a50c822e-bb91-4475-b653-53818e6cbe57",
    "task_type": "webhook_delivery",
    "status": "retrying",
    "priority": 5,
    "attempt_count": 1,
    "max_attempts": 4,
    "attempts": [
      {
        "id": "b11c822e-bb91-4475-b653-53818e6cbe88",
        "attempt_number": 1,
        "worker_id": "7665fd58-3759-4ca5-985e-6b94ea9c1221",
        "outcome": "failure",
        "started_at": "2026-10-13T00:01:00Z",
        "finished_at": "2026-10-13T00:01:02Z",
        "duration_seconds": 2.01,
        "error_message": "Upstream service returned HTTP 429 Too Many Requests"
      }
    ],
    "diagnostics": {
      "failed_attempt": 1,
      "classification": "RATE_LIMITED",
      "cause_description": "Task execution encountered rate limiting: Upstream service returned HTTP 429 Too Many Requests",
      "recovery_action": "Task will automatically retry after exponential backoff delay.",
      "will_retry": true,
      "next_retry_at": "2026-10-13T00:01:07Z",
      "recovery_worker_id": "7665fd58-3759-4ca5-985e-6b94ea9c1221",
      "recovery_duration_seconds": 2.01
    }
  }
  ```

### `POST /api/v1/tasks/{id}/cancel`
Cancel an active or pending task.
- **Auth**: API Key or JWT
- **Behavior**:
  - `queued` or `retrying` tasks transition immediately to `cancelled`.
  - `running` tasks have their cooperative cancellation flag set in Redis (`task:cancelled:{id}`), prompting the worker to abort gracefully.
  - Returns `409 Conflict` if the task is already terminal (`succeeded`, `failed`, `cancelled`).
- **Response 200**: Updated task response object.

### `POST /api/v1/tasks/{id}/retry`
Manually re-queue a `failed` or `dead_letter` task.
- **Auth**: API Key or JWT
- **Response 200**: Updated task transitioned to `queued`.

### `GET /api/v1/tasks/{id}/result`
Retrieve the task output result JSON without fetching the full attempt chronicle.
- **Auth**: API Key or JWT
- **Response 200**:
  ```json
  {
    "task_id": "a50c822e-bb91-4475-b653-53818e6cbe57",
    "status": "succeeded",
    "result": {
      "status_code": 200,
      "response_time_ms": 142.5
    }
  }
  ```

---

## 4. Worker & Fleet Telemetry

### `GET /api/v1/workers`
List all registered worker processes with real-time health and capacity telemetry.
- **Auth**: API Key or JWT
- **Response 200**:
  ```json
  [
    {
      "id": "7665fd58-3759-4ca5-985e-6b94ea9c1221",
      "hostname": "worker-pool-84f9b",
      "status": "online",
      "concurrency_limit": 8,
      "active_tasks": 3,
      "utilization_rate": 0.375,
      "last_heartbeat_at": "2026-10-13T00:04:12Z"
    }
  ]
  ```

### `GET /api/v1/workers/{id}`
Retrieve detailed diagnostic state for a specific worker instance.
- **Auth**: API Key or JWT
- **Response 200**: Worker details including queue subscriptions and active task allocations.

---

## 5. Queue Statistics & Control

### `GET /api/v1/queues/stats`
Retrieve real-time message depths across all broker priority queues and retry buckets.
- **Auth**: API Key or JWT
- **Response 200**:
  ```json
  {
    "tasks.high": 12,
    "tasks.normal": 45,
    "tasks.low": 8,
    "tasks.email_send.retry.5s": 2,
    "tasks.email_send.retry.10s": 0,
    "tasks.dead_letter": 0,
    "total_depth": 67
  }
  ```

### `POST /api/v1/queues/purge`
Purge all unconsumed messages from a queue (Admin only).
- **Auth**: JWT (Admin role required)
- **Body**: `{ "queue_name": "tasks.low" }`
- **Response 200**: `{ "purged_count": 8 }`

---

## 6. System & Observability

### `GET /healthz`
Health check for Kubernetes/PaaS liveness and readiness probes.
- **Auth**: None
- **Response 200**:
  ```json
  {
    "status": "ok",
    "components": {
      "database": { "status": "ok", "detail": "ok" },
      "redis": { "status": "ok", "detail": "ok" },
      "rabbitmq": { "status": "ok", "detail": "ok" }
    }
  }
  ```
  *(Returns `503 Service Unavailable` if any primary infrastructure dependency fails).*

### `GET /api/v1/metrics`
Prometheus exposition endpoint exporting API throughput, request durations, and backpressure admission statistics.
- **Auth**: None
- **Response 200**: Standard Prometheus plain text format.

### `GET /api/v1/handlers`
List available registered application handlers.
- **Auth**: None
- **Response 200**:
  ```json
  {
    "handlers": ["email_send", "webhook_delivery"]
  }
  ```

---

## 7. Standard Error Response Envelope

All API errors return a uniform, machine-readable JSON structure:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Task a50c822e-bb91-4475-b653-53818e6cbe57 not found",
    "field": "task_id"
  }
}
```

Common error codes:
- `UNAUTHENTICATED` (401)
- `FORBIDDEN` (403)
- `RESOURCE_NOT_FOUND` (404)
- `VALIDATION_ERROR` (422)
- `QUEUE_FULL` (429 - Backpressure shedding)
- `CONFLICT` (409)
- `INTERNAL_ERROR` (500)
