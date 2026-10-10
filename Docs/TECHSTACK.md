# TECHSTACK.md — Technology Stack

## Frontend

| Layer | Choice | Why |
|---|---|---|
| Framework | React 19 (Vite) | Fast local dev and modern React features consuming the REST API. |
| Language | TypeScript | Catches API-shape mismatches between frontend and backend at compile time. |
| Styling | Tailwind CSS v4 | Rapidly styles dense, consistent dashboard UI without hand-rolling CSS systems. |
| UI components | Hand-crafted Tailwind components + Lucide icons | Avoids heavy component libraries (e.g. Headless UI/MUI); keeps bundle small and maintainable. |
| State management | TanStack Query v5 (`@tanstack/react-query`) | Handles server cache, polling, and refetch on window focus. |
| Data fetching | Axios (`api/client.ts`) | Interceptors handle automatic JWT Bearer injection and seamless 401 token refresh rotation. |
| Charts | Custom lightweight SVG charts (`Charts.tsx`) | Zero-dependency inline SVGs for sparklines and throughput bars; no heavy charting library overhead. |

**Alternative considered:** Next.js — rejected because TaskForge's dashboard has no SEO requirement, no server-rendering need, and no benefit from Next's routing/server-component model; it would add complexity without solving a real problem here.

## Backend

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Strong async ecosystem (FastAPI, aio-pika for RabbitMQ, Pillow for image resizing). |
| API framework | FastAPI | Async-native (publishes to RabbitMQ and queries Postgres asynchronously), built-in Pydantic request/response validation, automatic OpenAPI docs generation at `/docs`. |
| Validation | Pydantic v2 | Single source of truth for request/response schemas and per-task-type payload schemas. |
| Authentication | `python-jose` (JWT) + API-key module | Short-lived JWTs (15m) with revocable rotated refresh tokens for dashboard sessions; SHA-256 hashed API keys for programmatic access with Redis-debounced `last_used_at` updates. |

## Task System

| Layer | Choice | Why |
|---|---|---|
| Message broker | RabbitMQ | Manual acknowledgements for crash safety, native dead-letter exchanges (DLQ), and per-message TTL for retry exponential backoff. |
| Worker framework | Custom async worker (Python + `aio-pika`), not Celery | Building the worker loop directly (consume → validate → execute with timeout → ack/nack → record attempt) demonstrates explicit queueing mechanics rather than hiding them. |
| Scheduling | Custom async loop with `croniter` + Redis distributed locking | Scans due recurring tasks periodically and publishes new task rows to RabbitMQ; coordinates via `lock:scheduler:scan`. |
| Retry system | Custom retry exchange with per-attempt TTL-based delay | Backed by attempt records in Postgres `task_attempts` table. |

## Database

| Layer | Choice | Why |
|---|---|---|
| Primary database | PostgreSQL 16 | Durable source of truth for users, API keys, tasks, and task attempts. |
| Cache / coordination | Redis 7 | Fast idempotency key lookups, distributed locks, rate-limiting counters, and API key debounce buffer. |
| Object storage | Local filesystem / volume (`IMAGE_OUTPUT_DIR`) | Resized image outputs are saved to disk with unique UUID filenames; S3-compatible adapter can be swapped in if needed. |

## Infrastructure

| Layer | Choice | Why |
|---|---|---|
| Containerization | Docker + Docker Compose | Compose defines API, worker, scheduler, Postgres, Redis, RabbitMQ, Prometheus, and Grafana. |
| Cloud | Managed PaaS / Docker host | Runs API + worker + scheduler as separate services with database add-ons. |
| Reverse proxy | Platform-managed or Nginx | Terminates TLS and routes traffic. |
| CI/CD | GitHub Actions (`.github/workflows/ci.yml`) | Automated linting, test suite execution against real services, build, and vulnerability audit (`pip-audit`, `npm audit`). |
| Monitoring | Prometheus + Grafana | Prometheus scrapes API (`/api/v1/metrics`) and worker (`:9001`), visualized in Grafana with pre-provisioned TaskForge and LoadTest dashboards. |

## Testing

| Layer | Choice | Why |
|---|---|---|
| Unit testing | `pytest` | Handlers, rate limiting, SSRF validator, security headers, and schema validation. |
| Integration testing | `pytest` against live service containers | Tests full auth, rate limit, worker lifecycle, DLQ redrive against real Postgres, Redis, and RabbitMQ. |
| API testing | `httpx` + FastAPI's `TestClient` | Exercises API endpoints end-to-end. |
| Load testing | `k6` (`load-tests/k6/taskforge.js`) | Validates throughput, p99 latency, and bottlenecks across baseline, stress, spike, and endurance scenarios. |
| End-to-end testing | Manual + live UI verification (submit task via dashboard, verify status transitions) | Focused integration and contract testing covers core distributed systems mechanics. |

## Explicitly Not Used (and Why)

- **Kafka** — log-based semantics and partition/consumer-group operations add real operational depth but are disproportionate to a 50–100 tasks/sec target and would consume time budget better spent on the queueing/retry/DLQ mechanics themselves.
- **Kubernetes** — orchestration complexity not justified at this scale or time budget; Compose + a managed PaaS demonstrates real deployment competence without it.
- **Celery** — would hide the exact mechanics (queueing, acking, retry, DLQ routing) that are this project's central engineering story.
- **GraphQL** — no requirement for flexible client-driven queries; REST is simpler to secure, rate-limit, and document for this scope.
