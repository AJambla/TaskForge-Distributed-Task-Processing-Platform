# ARCHITECTURE.md — System Architecture

## High-Level Architecture

```text
                        ┌───────────────┐
                        │   Browser     │
                        │ (React SPA)   │
                        └───────┬───────┘
                                │ HTTPS (JWT)
                                ▼
                        ┌───────────────┐        ┌────────────────┐
   External clients ───▶│   FastAPI     │───────▶│  PostgreSQL     │
   (HTTPS, API key)      │   API layer   │        │ (source of truth)│
                        └───────┬───────┘        └────────────────┘
                                │                        ▲
                                │ publish (task_id)       │ read/write
                                ▼                        │
                        ┌───────────────┐                │
                        │  RabbitMQ      │                │
                        │ main/retry/DLQ │                │
                        │    exchanges   │                │
                        └───────┬───────┘                │
                                │ consume                 │
                                ▼                        │
                        ┌───────────────┐────────────────┘
                        │  Worker pool   │
                        │ (N containers) │
                        └───────┬───────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
             ┌─────────────┐        ┌──────────────┐
             │    Redis     │        │  Prometheus/  │
             │ (idempotency,│        │   Grafana     │
             │ locks, rate  │        │ (metrics)      │
             │  limiting)   │        └──────────────┘
             └─────────────┘
```

`Scheduler` runs as a standalone async service alongside the API/workers. It uses a periodic 30s polling loop coordinated via Redis distributed locks (`lock:scheduler:scan`) and `croniter` to scan for due recurring/delayed tasks, publishing new task messages into RabbitMQ using the standard `publish_task` pipeline. It also handles periodic cleanup such as marking unresponsive workers offline.

## Component Responsibilities

- **React SPA:** Dashboard UI; talks only to the FastAPI layer, never directly to Postgres/RabbitMQ/Redis.
- **FastAPI API layer:** Auth (JWT + API key), request validation, task creation (writes to Postgres, then publishes to RabbitMQ), read endpoints for tasks/workers/queues, rate limiting.
  - *Why it exists:* single, auditable entry point for all task submission and system state changes; keeps validation and authorization in one place rather than duplicated across workers.
  - *If it fails:* the API being down blocks new task submission and dashboard reads, but does **not** stop already-queued tasks from being processed — workers consume directly from RabbitMQ, independent of API liveness. This decoupling is a deliberate design choice.
  - *Scaling:* stateless, horizontally scalable behind the PaaS's load balancer; session state lives in JWTs, not server memory.
- **PostgreSQL:** Durable system of record for users, API keys, tasks, and attempts (see DATABASE.md).
  - *If it fails:* API writes/reads fail (returns `503`); in-flight RabbitMQ messages are unaffected and will be processed once Postgres recovers, since workers re-check task state against Postgres before acting, and will retry/back off rather than lose the message. No task is lost, but the system pauses.
  - *Scaling:* vertical scaling and read replicas are the documented path if this ever became a bottleneck (see § Scaling); not needed at the 50–100 tasks/sec target.
- **RabbitMQ:** Durable queueing, redelivery-on-crash, and native dead-letter routing (see below).
  - *Why it exists over a simpler Redis-list queue:* manual ack semantics are what make crash-safe redelivery possible without hand-rolled visibility-timeout polling, and DLQ/TTL-based delay routing are native broker features rather than application logic to build and debug from scratch.
  - *If it fails:* new task submission fails at the publish step (API returns `503` for `POST /tasks`, since the API refuses to record a task as "queued" in Postgres if it cannot actually enqueue it — see Task Lifecycle below); already-consumed-but-unacked messages requeue automatically to the next connected consumer once the broker recovers, per AMQP's redelivery-on-disconnect behavior.
  - *Scaling:* clustering/mirrored queues are the documented path for broker HA at higher scale; not required at target scale for this project, and explicitly named as a known limitation (see § Scaling).
- **Worker pool:** Consumes from RabbitMQ, validates task still valid in Postgres, executes the handler with a timeout and resource limits, records the attempt, acks or nacks the message.
  - *If it fails (crash mid-task):* the message remains unacked; RabbitMQ redelivers it to another consumer once the broker detects the connection drop. The task's `attempt_count` and history make this visible rather than silent.
  - *Scaling:* horizontal — add worker container replicas; each worker independently registers and consumes, no coordination needed between workers themselves (see § Scaling for the concrete story).
- **Redis:** Idempotency-check fast path, distributed locks (scheduler), rate-limit counters (see DATABASE.md).
  - *If it fails:* idempotency falls back to the Postgres unique constraint alone (a narrow race window is possible but bounded — see DATABASE.md); scheduler lock loss could cause a brief double-fire of a recurring task, self-correcting and low-severity; rate limiting fails open when Redis is unreachable to avoid blocking legitimate traffic during cache downtime while logging warnings.
- **Prometheus + Grafana:** Scrapes `/api/v1/metrics` and worker-exposed metrics; visualizes queue depth, throughput, latency, failure rate; alerting rules for operational thresholds.

## Task Lifecycle

```text
Client
  → API: POST /tasks (validated against per-type schema)
  → Postgres: INSERT task row (status = 'queued')
  → RabbitMQ: publish {task_id} to main exchange
       (if publish fails, API returns 503 and does NOT leave the task
        row in 'queued' state without a corresponding message — see below)
  → API responds 201 to client
  ...
  → Worker: consumes message
  → Worker: re-reads task row from Postgres (defends against stale/cancelled state)
  → Worker: status → 'running', started_at set
  → Worker: executes handler with timeout + resource limits
  → Worker: records TaskAttempt (outcome, error if any)
  → Success  → status → 'succeeded', completed_at set, message ACKed
  → Failure  → attempt_count < max_attempts → status → 'retrying',
               message routed to retry queue (TTL = backoff delay),
               then dead-lettered back to main queue after TTL expires
  → Failure  → attempt_count >= max_attempts → status → 'dead_letter',
               message routed to DLQ, visible in dashboard for manual replay
  → Cancel (only while 'queued'/'retrying') → status → 'cancelled'
```

**On the publish-failure edge case:** the API performs the Postgres insert and RabbitMQ publish inside a single logical operation — if the publish fails after the insert, the API marks the task row `failed` immediately (a "never queued" terminal state) rather than leaving a `queued` task with no corresponding message, so the dashboard never shows a task as queued when it isn't actually in the broker.

## Failure Scenarios

| Scenario | Behavior |
|---|---|
| API crashes | New submissions/reads fail (503s); already-queued tasks continue processing normally since workers don't depend on the API. |
| Worker crashes mid-task | Message stays unacked, RabbitMQ redelivers to another worker after connection-drop detection; task shows an extra attempt in its history rather than silently disappearing. |
| Database goes down | API responses degrade to errors for read/write; workers pause (can't validate task state) rather than proceeding blind, and retry connecting; RabbitMQ buffers messages durably in the meantime — no message is dropped due to Postgres being unavailable. |
| Redis goes down | Idempotency/locking/rate-limiting degrade to their documented fallback behaviors (above); no task data is lost, since Redis never holds authoritative task state. |
| Worker disappears during execution | Same as "worker crashes" — the AMQP consumer connection drop is what triggers redelivery, not any custom heartbeat logic on the message itself (worker heartbeats in `worker_registrations` are for dashboard visibility, a separate mechanism from message redelivery). |
| Task times out | Worker enforces a per-task-type execution timeout; on timeout, the attempt is recorded as `outcome = 'timeout'`, the message is nacked (not acked), and it proceeds through the same retry/DLQ path as any other failure. |
| Task repeatedly fails | After `max_attempts`, task reaches `dead_letter` — visible, not deleted, and manually replayable. |
| Duplicate task arrives | Blocked by the two-layer idempotency check (Redis fast-path + Postgres unique constraint) — see DATABASE.md. |
| Queue becomes overloaded | Queue depth is monitored (Prometheus); Phase 2 backpressure signaling would reject new submissions above a depth threshold rather than let the queue grow unbounded — documented as a Phase 2 feature, not yet enforced in MVP. |

## Distributed Systems Concepts — What's Actually Implemented

| Concept | Status | Explanation |
|---|---|---|
| At-least-once delivery | **Implemented** | RabbitMQ manual acks + redelivery-on-disconnect guarantee a message is not lost on worker crash; the same message can be delivered more than once (e.g. if a worker crashes after processing but before acking), which is why idempotent handler design and the idempotency-key layer both matter. |
| Idempotency (submission-level) | **Implemented** | Redis + Postgres unique constraint on `(user_id, idempotency_key)`. |
| Idempotency (handler-level) | **Partially implemented** | `webhook_delivery` and `email_send` are designed to be safe-ish to re-run (the risk of a duplicate email/webhook on a rare redelivery is accepted and documented, not eliminated); true handler-level exactly-once is explicitly **not** claimed. |
| Retry with backoff | **Implemented** | Per-attempt TTL on the retry queue implements exponential backoff (e.g. attempt N delay = base × 2^N, capped). |
| Dead-letter queue | **Implemented** | Native RabbitMQ DLQ per task type, after `max_attempts`. Inspectable via `GET /api/v1/queues/dlq` and replayable in bulk via `POST /api/v1/queues/dlq/redrive` or individually via `POST /api/v1/tasks/{id}/retry`. |
| Worker heartbeat | **Implemented** | Periodic heartbeat updates `worker_registrations.last_heartbeat_at`; a background scheduler job marks workers `offline` after a missed-heartbeat threshold. This is for **dashboard visibility**, not the mechanism that triggers message redelivery (that's AMQP connection-drop detection). |
| Worker leasing / visibility timeout | **Implemented, via AMQP semantics** | RabbitMQ's unacked-message redelivery-on-disconnect *is* TaskForge's visibility-timeout mechanism — no separate custom lease system was built, since the broker already provides this correctly. |
| Concurrency (per worker) | **Implemented** | Each worker enforces a configured max concurrent task count (AMQP QoS prefetch tied to this limit). |
| Backpressure | **Implemented** | API checks total RabbitMQ queue depth during task creation (`check_backpressure`); if depth exceeds configured threshold (default 10,000), new submissions are rejected with `429 Too Many Requests`. |
| Horizontal scaling | **Implemented** | Workers are stateless consumers; adding a replica requires no code or config change beyond starting another container. |
| Fault tolerance (broker) | **Partially implemented** | Single RabbitMQ instance in MVP — durable queues survive a broker *restart* (with disk-backed message persistence enabled), but not a broker *host failure* without clustering, which is explicitly out of scope at this project's scale (see § Scaling, "Known Limitation"). |
| Ordering guarantees | **Not guaranteed, by design** | FIFO within a single queue/consumer is roughly preserved but not contractually guaranteed once retries and multiple workers are involved; task types were chosen (email, image resize, webhook delivery) specifically because none require strict cross-task ordering. |

## Scaling

```text
1 worker    → baseline throughput; single point of processing capacity;
              easy to reason about and debug.

5 workers   → near-linear throughput increase for CPU-bound handlers
              (image resize); I/O-bound handlers (email, webhook) scale
              even further since they spend most time waiting, not
              computing — concurrency per worker matters more than
              worker count for these.

50 workers  → RabbitMQ itself, and Postgres connection count, become the
              likely bottlenecks before worker count does — this is
              the point at which connection pooling (PgBouncer) and
              broker tuning (prefetch, queue count) would need explicit
              attention rather than "just add more workers."

500 workers → out of scope for this project's target load and would
              require RabbitMQ clustering/mirrored queues, Postgres
              read replicas, and almost certainly a queue-per-shard
              or partitioned approach — named here to show awareness
              of the next step, not implemented or claimed.
```

**Known bottleneck at target scale (50–100 tasks/sec):** the most likely limiting factor is Postgres write throughput from `task_attempts` inserts under concurrent worker load, not RabbitMQ (which comfortably handles far higher throughput than this target) or the workers themselves. This is exactly what the load-testing plan (see DEPLOYMENT.md) is designed to confirm or disprove with real numbers rather than assumption.

## Architecture Trade-offs

**Broker: RabbitMQ vs. Redis-list queue vs. Kafka**
- *Redis-list queue* — simpler to operate, but requires hand-building ack/redelivery/DLQ logic that RabbitMQ provides natively; rejected because it would move engineering effort away from the parts of the system most worth demonstrating (correct retry/DLQ semantics) and into reinventing broker primitives.
- *Kafka* — stronger resume signal for log-based/high-throughput systems, but partition/consumer-group management and its different delivery model (offset-based, not per-message ack) are a mismatch for this project's task-queue semantics and time budget.
- **Selected: RabbitMQ** — matches task-queue semantics naturally (per-message ack, native DLQ, TTL-based delay) at a complexity level appropriate for a 1–2 month solo build.

**Worker framework: custom vs. Celery**
- *Celery* — faster to build with, widely used in production Python systems.
- **Selected: custom async worker** — the queueing/retry/ack mechanics are the point of this project; using Celery would hide exactly what needs to be designed and explained.

**Task variety: fixed 3 types vs. arbitrary user-defined handlers**
- *Arbitrary handlers* — more "impressive" on paper, but turns this into a code-execution sandboxing project (a different, much larger problem) and dilutes focus away from distributed-systems depth.
- **Selected: fixed 3 built-in types** — keeps the security model tractable (validate against known schemas) while still requiring real isolation for untrusted *inputs* (image bytes, webhook URLs) — see SECURITY.md.

**Deployment: PaaS vs. Kubernetes**
- *Kubernetes* — strong resume keyword, but the operational learning curve would consume time better spent on the task engine itself, and is not required to demonstrate the stated primary goals (distributed systems + backend).
- **Selected: Docker Compose (local) + managed PaaS (prod)** — demonstrates real multi-service deployment and container orchestration concepts without the full K8s operational surface.

**Idempotency: Redis-only vs. Postgres-only vs. both**
- *Redis-only* — fast, but not durable/transactional enough to be a hard guarantee under race conditions.
- *Postgres-only* — durable and race-safe, but adds a database round-trip to every submission's hot path.
- **Selected: both, layered** — Redis for the common-case fast rejection, Postgres unique constraint as the authoritative backstop.
