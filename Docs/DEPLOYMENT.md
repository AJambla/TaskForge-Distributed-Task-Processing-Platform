# DEPLOYMENT.md — Deployment Guide

## Local Development

```text
git clone <repo-url>
cd taskforge
cp .env.example .env          # fill in local secrets (DB password, JWT secret, etc.)
docker compose up -d postgres redis rabbitmq
docker compose run --rm api alembic upgrade head    # run DB migrations
docker compose up -d api worker scheduler
cd frontend && npm install && npm run dev            # dashboard on localhost:5173
```

Services and default local ports:

| Service | Port | Notes |
|---|---|---|
| API (FastAPI) | 8000 | `GET /docs` for interactive OpenAPI UI |
| Frontend (Vite dev server) | 5173 | Proxies API calls to `localhost:8000` |
| PostgreSQL | 5432 (mapped to 5433 in compose override) | |
| Redis | 6379 (mapped to 6380 in compose override) | |
| RabbitMQ | 5672 (AMQP), 15672 (management UI) | |
| Prometheus | 9090 | Scrapes API, workers, and RabbitMQ |
| Grafana | 3000 | Operational & load test dashboards (auth via `GRAFANA_ADMIN_PASSWORD`) |

## Docker

**Containers defined in `docker-compose.yml`:**

- **`api`** — FastAPI app, built from `Dockerfile.api`; depends on `postgres`, `redis`, `rabbitmq`.
- **`worker`** — Worker process, built from `Dockerfile.worker` (shares Python dependencies, runs async consumer loop with prefetch QoS and graceful SIGTERM drain); scaled via `docker compose up --scale worker=N`.
- **`scheduler`** — Standalone async scheduler service publishing due recurring/delayed tasks, coordinated via Redis distributed locks (`lock:scheduler:scan`).
- **`frontend`** — React 19 SPA built with Vite.
- **`postgres`** — Official `postgres:16` image, with named volume for data persistence.
- **`redis`** — Official `redis:7-alpine` image.
- **`rabbitmq`** — `rabbitmq:3-management-alpine` image, with named volume, DLQ, and durable queue declarations.
- **`prometheus`** / **`grafana`** — Monitoring containers with provisioned Prometheus datasource and TaskForge operational dashboards.

**Networking:** All services share a single Compose network; only `api` and `frontend` publish ports to the host in local dev. Environment variables (DB connection string, RabbitMQ URL, Redis URL, JWT signing secret) are injected via the `.env` file, referenced in `docker-compose.yml`.

## Production

```text
Internet
   │
   ▼
PaaS-managed HTTPS/Load Balancer
   │
   ▼
API service (N instances, autoscaled by the platform)
   │
   ├── Managed PostgreSQL (add-on)
   ├── Managed Redis (add-on)
   ├── RabbitMQ (single instance, PaaS-hosted container or a managed CloudAMQP-style add-on)
   └── Worker service (M instances, scaled independently of the API)
   └── Scheduler service (1 instance)

Frontend: deployed as a static build (e.g. to the PaaS's static hosting or a
CDN), calling the API service's public HTTPS endpoint.
```

**Chosen platform:** A managed multi-service PaaS (Render, Fly.io, or Railway — final choice made at implementation time based on free/low-cost tier fit for running 5 services + Postgres + Redis continuously). All three support the same fundamental pattern: one deployable service per container (`api`, `worker`, `scheduler`), managed database add-ons, and environment-variable-based secret injection — so the choice does not affect the architecture, only deployment mechanics.

- **DNS:** A custom domain (optional) pointed at the PaaS-provided endpoint via CNAME; PaaS handles the rest.
- **TLS:** Automatically provisioned and renewed by the PaaS (e.g. via Let's Encrypt) — no manual certificate management.
- **Environment variables / secrets:** Set via the PaaS's dashboard/CLI secret store, not committed to the repo; `.env.example` documents required keys without values.
- **Database migrations:** Run via Alembic (`alembic upgrade head`) as a one-off release-time command/job before the new API version starts serving traffic — never applied by application code on startup, to avoid race conditions between multiple API replicas starting simultaneously.
- **Autoscaling:** API service scales on request volume/CPU (platform-native autoscaling); worker service scales manually or on a queue-depth-based rule if the platform supports custom scaling triggers — documented as a manual scaling step for MVP, with the queue-depth-based version marked as a Phase 2 stretch goal.
- **Health checks:** `GET /healthz` on the API service, checked by the platform to determine instance health and readiness before routing traffic to it.
- **Rolling deployments:** New API instances started and health-checked before old instances are terminated (platform-native rolling deploy); workers use a "let in-flight tasks finish, then stop consuming" drain pattern on shutdown (SIGTERM handled to stop consuming new messages, finish current task, then exit) rather than a hard kill, to avoid unnecessarily triggering redelivery-based retries during a routine deploy.
- **Backups:** Managed Postgres add-on's automatic daily backups, retained per the platform's default window; documented manual `pg_dump` procedure as a supplementary/portable backup option.
- **Disaster recovery:** Restore procedure = provision a fresh Postgres instance from the latest backup, point the API's `DATABASE_URL` at it, redeploy. RabbitMQ and Redis hold no data that isn't reconstructible or non-critical (see ARCHITECTURE.md failure-scenario table), so DR focuses on Postgres.

## CI/CD

```text
Git Push
 ↓
Lint          — ruff (Python), eslint (frontend)
 ↓
Unit Tests    — pytest (backend logic), vitest (frontend components)
 ↓
Integration Tests — pytest against real Postgres/RabbitMQ/Redis via Docker
                     Compose in the CI runner (testcontainers or a CI
                     services block)
 ↓
Build         — build API, worker, and frontend Docker images
 ↓
Docker Image  — tag with commit SHA, push to a container registry
 ↓
Security Scan — dependency audit (pip-audit / npm audit) and a container
                 image scan (e.g. Trivy) — pipeline fails on high/critical
                 findings
 ↓
Deploy        — trigger the PaaS deploy (via its CLI/API) on main-branch
                 merges only; PRs run through Lint/Test/Build/Scan but do
                 not deploy
```

Implemented via **GitHub Actions**, one workflow file per stage-group (`ci.yml` for lint/test/build/scan on every PR and push, `deploy.yml` triggered on merge to `main`).

## Monitoring

- **Logs:** Structured JSON logs from API and workers (request ID, task ID where applicable, level, message), shipped to the PaaS's native log aggregation (sufficient at this scale — a dedicated log platform like Loki is a documented future step, not required now).
- **Metrics:** `prometheus-fastapi-instrumentator` on the API (request latency/count/status), a custom metrics exporter on workers (tasks processed, task duration histogram, failures by type), and a RabbitMQ Prometheus plugin/exporter for queue depth and consumer counts — all scraped by a Prometheus instance and visualized in Grafana.
- **Health checks:** `GET /healthz` (API) and a worker-side liveness signal via the heartbeat mechanism already described in ARCHITECTURE.md/DATABASE.md — the dashboard's Worker view is effectively a human-facing health check for the worker fleet.
- **Alerts:** Prometheus alerting rules (`monitoring/alerting/rules.yml`) for: queue depth exceeding threshold, high failure rates, and zero online workers.
- **Queue metrics:** Exposed both via the RabbitMQ management UI (operator-facing, ad hoc) and via the Prometheus exporter (for dashboards/alerting) — the two are complementary, not redundant, since the management UI is useful for direct debugging in a way a dashboard panel isn't.
- **Worker metrics:** Tasks processed, failure rate, and current load per worker, both in the TaskForge dashboard (application-level view, tied to `worker_registrations`) and in Grafana (infrastructure-level view, tied to Prometheus counters) — kept consistent by deriving both from the same underlying attempt records where possible.

## Load Testing Plan

A bundled `k6` harness (`load-tests/k6/taskforge.js`) drives task submissions against the stack across four distinct load scenarios:
- **Baseline**: 10 VUs for 5 minutes
- **Stress**: 50 VUs for 10 minutes
- **Spike**: 10→200 VUs burst for 9 minutes
- **Endurance**: 30 VUs sustained for 30 minutes

Run via PowerShell (`.\load-tests\run-tests.ps1`) or Bash (`./load-tests/run-tests.sh`). Grafana dashboards (`Load Test`) and Prometheus indicate bottlenecks (e.g. Postgres `task_attempts` write saturation vs RabbitMQ queue growth). Results are measured and verifiable.
