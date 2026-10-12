# TaskForge — System Architecture

This document describes the architectural design, component interactions, execution model, failure guarantees, and scope boundaries of **TaskForge**.

---

## 1. High-Level Architecture

```text
                        ┌────────────────────────────────┐
                        │      Client Applications       │
                        │ (Browser SPA, API Clients, k6) │
                        └───────────────┬────────────────┘
                                        │ HTTPS (JWT / API Key)
                                        ▼
                        ┌────────────────────────────────┐        ┌─────────────────────────┐
                        │        FastAPI Gateway         │───────▶│      PostgreSQL 16      │
                        │ • Dual-Auth (JWT + API Key)    │        │ (Authoritative Storage) │
                        │ • Sub-ms Backpressure (<1ms)   │        │ • tasks / task_attempts │
                        │ • W3C Trace Context Injection  │        │ • transactional outbox  │
                        │ • Fixed-Window Rate Limiting   │        │ • worker registrations  │
                        └───────┬────────────────────────┘        └───────────┬─────────────┘
                                │                                             ▲
                                │                                             │ SELECT ... FOR UPDATE
                                ▼                                             │ SKIP LOCKED
                        ┌───────────────┐                         ┌───────────┴─────────────┐
                        │    Redis 7    │                         │ Transactional Outbox    │
                        │ (Fast-Path)   │                         │ Relay Service           │
                        │ • Queue Depth │                         └───────────┬─────────────┘
                        │ • Idempotency │                                     │
                        │ • Heartbeats  │                                     │ AMQP publish
                        └───────────────┘                                     ▼
                                                          ┌─────────────────────────────────┐
                                                          │            RabbitMQ             │
                                                          │ • taskforge.tasks (Topic Exch)  │
                                                          │ • tasks.high (Priority >= 7)    │
                                                          │ • tasks.normal (Priority 3-6)   │
                                                          │ • tasks.low (Priority 0-2)      │
                                                          │ • Retry Buckets (5s to 60s TTL) │
                                                          │ • Dead Letter Queue (DLQ)       │
                                                          └───────────────┬─────────────────┘
                                                                          │
                                            ┌─────────────────────────────┴─────────────────────────────┐
                                            │ AMQP consume (Weighted Fair Queueing: 60% / 30% / 10%)    │
                                            ▼                                                           ▼
                             ┌───────────────────────────────┐                           ┌───────────────────────────────┐
                             │       Worker Instance 1       │                           │       Worker Instance N       │
                             │ • Bounded Concurrency (Sem)   │                           │ • Bounded Concurrency (Sem)   │
                             │ • Double-Buffered Prefetch    │                           │ • Double-Buffered Prefetch    │
                             │ • Execution Timeout Guard     │                           │ • Execution Timeout Guard     │
                             │ • Deterministic Diagnostics   │                           │ • Deterministic Diagnostics   │
                             │ • Metrics Server (:9001)      │                           │ • Metrics Server (:9001)      │
                             └──────────────┬────────────────┘                           └──────────────┬────────────────┘
                                            │                                                           │
                                            └─────────────────────────────┬─────────────────────────────┘
                                                                          │ Heartbeat & State Updates
                                                                          ▼
                                                          ┌─────────────────────────────────┐
                                                          │ Autonomous Recovery Monitor     │
                                                          │ • Scans heartbeats < now - 45s  │
                                                          │ • Marks crashed workers offline │
                                                          │ • Reclaims & re-queues tasks    │
                                                          └─────────────────────────────────┘
```

---

## 2. Core Architectural Principles

### 2.1 The Scope Boundary
TaskForge is built around one governing principle:

> **TaskForge provides the machinery for executing tasks reliably — it does not define what those tasks actually do.**

Business logic resides strictly inside application handlers (e.g., `email_send`, `webhook_delivery`). TaskForge manages the entire operational lifecycle: submission, outbox staging, broker delivery, fair scheduling, execution timeouts, worker health, failure recovery, idempotency, backpressure, and deterministic diagnostics.

TaskForge explicitly excludes:
- DAG and workflow orchestration engines
- Dynamic third-party plugin marketplaces
- Large artifact storage / S3 download services (task results are stored natively in PostgreSQL JSONB)
- Artificial intelligence / LLM agents (all diagnostics are strictly rule-based and deterministic)

### 2.2 Storage & Infrastructure Roles
Every infrastructure component has a single, justified responsibility:
- **PostgreSQL 16**: Durable system of record for tasks, execution attempts, transactional outbox events, worker registrations, and user credentials.
- **RabbitMQ 3.13**: Task delivery backbone providing AMQP manual acknowledgments, unacked-message redelivery upon connection drop, native message TTL, and dead-letter exchanges.
- **Redis 7**: Narrowly targeted fast-path concerns:
  - Sub-millisecond queue depth caching for backpressure admission control
  - Idempotency key lookup fast-path
  - Worker heartbeat live snapshots
  - Fixed-window rate limiting counters
- **Prometheus & Grafana**: Telemetry collection and visualization across API request rates, worker saturation, execution durations, and recovery events.

---

## 3. The 5 Architectural Pillars

### Pillar 1: Reliable (At-Least-Once Delivery & Transactional Outbox)
When a task is submitted via `POST /api/v1/tasks`:
1. The API validates the payload against strict Pydantic schemas.
2. The task record and corresponding `task_outbox` event are committed atomically inside a single database transaction.
3. The outbox relay service processes pending events using:
   ```sql
   SELECT id, payload FROM task_outbox
   WHERE status = 'pending'
   ORDER BY created_at
   FOR UPDATE SKIP LOCKED
   LIMIT :batch_size;
   ```
4. This guarantees that concurrent relay workers never process duplicate events and no task is lost even if the broker is momentarily unavailable during submission.

### Pillar 2: Recoverable (Autonomous Crash Detection & Task Reclamation)
Worker node failure or process termination (`kill -9`) is handled autonomously:
1. Every worker emits periodic heartbeats (`worker.heartbeat` in Redis and `last_heartbeat_at` in PostgreSQL).
2. The background recovery loop (`recover_stale_tasks`) scans for workers marked `online` whose last heartbeat exceeds the stale threshold (45 seconds).
3. The dead worker is marked `offline`.
4. In-flight tasks assigned to that worker are reclaimed:
   - If `attempt_count < max_attempts`: The attempt is closed with `outcome='failure'` and `error_message='Worker heartbeat lost (crash detected)'`. The task is transitioned back to `queued` and a new outbox re-publish event is scheduled.
   - If `attempt_count >= max_attempts`: The task transitions to `dead_letter`.
5. This mechanism guarantees the core system invariant: **Zero Task Loss**.

### Pillar 3: Controlled (Low-Latency Backpressure & Priority Fairness)
1. **Sub-Millisecond Admission Control**:
   - A background sampler continuously updates Redis key `queue:total_depth` with a 2-second TTL.
   - Upon task submission, the API checks this cached count in `<1ms`.
   - If total depth exceeds `backpressure_critical_depth`, the API sheds load immediately, returning `429 Too Many Requests` with a `Retry-After: 5` header, protecting downstream database and broker memory.
2. **Anti-Starvation Weighted Fair Queueing (WFQ)**:
   - Tasks are partitioned across `tasks.high` (priority 7–10), `tasks.normal` (priority 3–6), and `tasks.low` (priority 0–2).
   - The worker consumer polls queues in a 60% / 30% / 10% weighted schedule.
   - Under sustained high-priority traffic bursts, low-priority tasks are guaranteed 10% of worker capacity, preventing starvation.
3. **Bounded Concurrency & Prefetch QoS**:
   - Worker task concurrency is bounded by an `asyncio.BoundedSemaphore`.
   - AMQP channel prefetch count is set to `worker_concurrency * 2`, ensuring double-buffered pipeline flow without memory bloat.

### Pillar 4: Observable (Distributed Tracing & Golden Metrics)
- **W3C Distributed Tracing**: Every task carries a W3C `traceparent`. Traces inject at the API gateway and propagate through the outbox, RabbitMQ headers, worker executor, and database attempts, enabling distributed trace analysis.
- **Prometheus Metrics**:
  - `http_requests_total` & `http_request_duration_seconds_bucket` (FastAPI Gateway)
  - `tasks_processed_total` & `task_duration_seconds` (Worker Fleet)
  - `worker_active_tasks`, `worker_concurrency_limit`, `worker_utilization_ratio`
  - `tasks_recovered_total` & `worker_failures_total`
  - `backpressure_shed_total`

### Pillar 5: Developer-Friendly (Deterministic Failure Diagnostics)
Failed tasks are analyzed by a deterministic rule engine (`synthesize_diagnostics`) that produces structured diagnostic reports:
- **Classification**:
  - `TRANSIENT_ERROR`: Upstream network glitch, temporary 5xx, or DB lock contention.
  - `RATE_LIMITED`: Upstream HTTP 429 response.
  - `TIMEOUT`: Execution exceeded configured `timeout_seconds`.
  - `WORKER_CRASH`: Worker heartbeat lost or process killed mid-execution.
  - `FATAL_ERROR`: Unhandled exception or deterministic schema failure.
- **Actionable Metadata**:
  - Recommended recovery action.
  - Next retry scheduled timestamp (`next_retry_at`).
  - Worker ID responsible for recovery.
  - Complete chronological execution history across all attempts.
