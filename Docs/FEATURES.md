# FEATURES.md — Feature Specification

Priority levels: **Must Have** (MVP-blocking), **Should Have** (production-inspired scope, planned Phase 2), **Nice to Have** (do if time allows), **Future** (explicitly out of scope for this build).

Complexity: **S**mall, **M**edium, **L**arge.

## Core

| Feature | Purpose | User | Priority | Complexity | Implemented? |
|---|---|---|---|---|---|
| Task creation (API) | Submit a task for async processing | Developer | Must Have | M | Yes |
| Task creation (dashboard) | Manually submit/test a task via drawer/modal | Developer/Admin | Should Have | S | Yes |
| Task queue (RabbitMQ) | Durable, ordered handoff of tasks to workers | System | Must Have | L | Yes |
| Worker processing | Execute task handlers (email, image, webhook) | System | Must Have | L | Yes |
| Task status tracking | Let users know task lifecycle state | Developer | Must Have | M | Yes |
| Retry mechanism (backoff) | Recover from transient handler failures | System | Must Have | M | Yes |
| Task history / attempts log | Debuggability, audit trail | Developer/Admin | Must Have | M | Yes |
| Dead-letter queue | Surface permanently failed tasks instead of losing them | Admin | Must Have | M | Yes |
| Manual DLQ replay | Recover a task after fixing the underlying issue (single + bulk redrive) | Admin | Should Have | S | Yes |
| Task cancellation | Stop a queued/not-yet-started task | Developer | Should Have | S | Yes |
| Idempotency keys | Prevent duplicate execution from duplicate submissions | Developer | Must Have | M | Yes |
| Scheduled / delayed tasks | Run a task at a future time (`run_at`) | Developer | Should Have | M | Yes |
| Recurring tasks | Run a task on a cron schedule via scheduler service | Developer | Should Have | M | Yes |

## Distributed Systems

| Feature | Purpose | User | Priority | Complexity | Implemented? |
|---|---|---|---|---|---|
| Worker registration | Track which workers exist and their capabilities | System | Must Have | S | Yes |
| Worker heartbeats | Detect worker liveness | System | Must Have | S | Yes |
| Worker health / offline detection | Surface dead workers, trigger task re-delivery | System/Admin | Must Have | M | Yes |
| Load distribution across workers | Even utilization, no single worker overload | System | Must Have | M | Yes |
| Per-worker concurrency limits | Bound resource usage per worker process (QoS prefetch) | System | Must Have | S | Yes |
| Task priority | Let urgent tasks jump the queue | Developer | Nice to Have | M | Partial (stored in DB & UI; priority queue routing deferred) |
| Task timeouts | Prevent a stuck handler from blocking a worker slot forever | System | Must Have | M | Yes |
| Visibility timeout / re-delivery | Redeliver a task if the worker dies mid-execution | System | Must Have | L | Yes |
| Backpressure signaling | Reject/throttle submission when queue depth exceeds threshold | System | Should Have | M | Yes |
| Horizontal worker scaling | Add workers without code changes to absorb more load | System | Must Have | M | Yes |

## Dashboard

| Feature | Purpose | User | Priority | Complexity | Implemented? |
|---|---|---|---|---|---|
| Task dashboard (list + filters) | Browse/search tasks by status, type, time | Developer/Admin | Must Have | M | Yes |
| Task detail view | Inspect payload, attempts, errors, timings | Developer/Admin | Must Have | M | Yes |
| Worker dashboard | See live worker status and load | Admin/User | Must Have | M | Yes |
| Queue metrics view | Queue depth, throughput, latency at a glance | Admin/User | Must Have | M | Yes |
| System health overview | Single-page summary of system state (`Overview.tsx`) | Admin/User | Should Have | S | Yes |
| Grafana dashboards | Deep observability, historical trends (TaskForge + LoadTest dashboards) | Admin | Should Have | M | Yes |

## Developer Experience

| Feature | Purpose | User | Priority | Complexity | Implemented? |
|---|---|---|---|---|---|
| REST API | Primary integration surface (`/api/v1`) | Developer | Must Have | L | Yes |
| API key management | Auth for programmatic access (hashed at rest, rotation/revocation) | Developer | Must Have | M | Yes |
| API versioning (`/api/v1`) | Allow safe future evolution | System | Must Have | S | Yes |
| Rate limiting | Protect system with Redis counters and Retry-After headers | System | Must Have | M | Yes |
| OpenAPI/Swagger docs | Self-serve API discovery at `/docs` | Developer | Should Have | S | Yes |
| SDK | N/A — not planned; REST is the sole surface to keep scope tight | — | Future | — | No |
| CLI | N/A — not planned for this scope | — | Future | — | No |
| Outbound webhooks (task completion callback) | Notify caller's system on task completion | Developer | Nice to Have | M | No |

## Advanced (Production Readiness)

| Feature | Purpose | User | Priority | Complexity | Implemented? |
|---|---|---|---|---|---|
| Sandboxed/resource-limited execution | Contain risk from untrusted task inputs (SSRF guards, memory caps) | System | Should Have | L | Yes |
| Prometheus metrics endpoint | Machine-readable system metrics (`/api/v1/metrics`, worker `:9001`) | System | Should Have | M | Yes |
| Grafana + alerting rules | Operational visibility and proactive Prometheus alerting rules | Admin | Should Have | M | Yes |
| CI/CD pipeline | Automated quality gates (`ci.yml` lint, test, build, scan) | System | Should Have | M | Yes |
| Load testing harness | k6 scenarios (baseline, stress, spike, endurance) | Developer | Should Have | M | Yes |

## Explicitly Excluded (Future / Out of Scope)

- Arbitrary user-defined task types / uploaded code execution.
- AI/LLM task types.
- Kubernetes-based orchestration.
- Multi-tenant organizations/teams.
- SDK and CLI clients.
