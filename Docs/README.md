# TaskForge

**A distributed task processing platform** — submit background jobs (email sending, image resizing, webhook delivery) over a REST API, and let a horizontally scalable worker fleet process them reliably, with real retry/backoff, dead-lettering, idempotency, and worker-failure recovery.

Built as a production-inspired, portfolio-grade project to demonstrate distributed-systems and backend engineering depth, not just CRUD-app plumbing.

## Problem Statement

Doing background work (sending an email, resizing an image, hitting a webhook) synchronously inside an API request makes that request slow and fragile. The common DIY alternative — a hand-rolled queue with no real retry, ack, or dead-letter semantics — quietly loses or duplicates work. TaskForge solves this with a real message broker (RabbitMQ), a durable system of record (PostgreSQL), and a worker pool that handles crashes, retries, and permanent failures explicitly and visibly, instead of silently.

## Features

- Task submission via REST API (JWT for the dashboard, API keys for programmatic clients)
- Three built-in task types: email send, image resize, webhook delivery
- At-least-once delivery with automatic retry + exponential backoff
- Dead-letter queue for tasks that exhaust their retries, with manual replay
- Idempotency keys to prevent duplicate task execution
- Worker registration, heartbeats, and health visibility
- Horizontal worker scaling — add a worker container, no code changes
- Scheduled and recurring tasks
- Sandboxed, resource-limited task execution with SSRF protection on URL-based inputs
- React dashboard: task list/detail, worker list/detail, queue metrics
- Prometheus + Grafana observability stack

See [`docs/FEATURES.md`](docs/FEATURES.md) for the full feature breakdown by priority.

## Architecture Overview

```text
Browser (React) ──HTTPS──▶ FastAPI API ──▶ PostgreSQL (source of truth)
External clients ─────────▶      │
                                  ▼
                             RabbitMQ (main / retry / DLQ)
                                  │
                                  ▼
                          Worker pool (N containers)
                                  │
                      Redis (idempotency, locks, rate limits)
                      Prometheus/Grafana (metrics)
```

Full component responsibilities, task lifecycle, failure-scenario handling, and scaling analysis: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Tech Stack

**Backend:** Python, FastAPI, PostgreSQL, Redis, RabbitMQ, custom async worker (no Celery — see [`docs/TECHSTACK.md`](docs/TECHSTACK.md) for why)
**Frontend:** React, TypeScript, Tailwind CSS, React Query, Recharts
**Infrastructure:** Docker Compose (local), managed PaaS (production), GitHub Actions (CI/CD), Prometheus + Grafana (monitoring)

Full stack rationale, including alternatives considered and rejected: [`docs/TECHSTACK.md`](docs/TECHSTACK.md).

## Local Setup

```bash
git clone <repo-url>
cd taskforge
cp .env.example .env
docker compose up -d postgres redis rabbitmq
docker compose run --rm api alembic upgrade head
docker compose up -d api worker scheduler
cd frontend && npm install && npm run dev
```

API docs (interactive OpenAPI/Swagger): `http://localhost:8000/docs`
Dashboard: `http://localhost:5173`
RabbitMQ management UI: `http://localhost:15672`

Full instructions, including production deployment: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Screenshots

*(placeholder — add dashboard screenshots here: Overview, Task Detail, Worker List)*

## API Documentation

Full endpoint reference, request/response examples, auth, pagination, and rate limiting: [`docs/API.md`](docs/API.md). Interactive docs available at `/docs` on a running instance.

## Testing

```bash
pytest                                       # unit + integration tests
cd frontend && npm run build                 # frontend type check & build
./load-tests/run-tests.sh all                # load tests via bash runner
.\load-tests\run-tests.ps1 -Scenario all     # load tests via PowerShell runner
```

Testing strategy and rationale: [`docs/TECHSTACK.md`](docs/TECHSTACK.md) § Testing.

## Deployment

Deployed via Docker images to a managed PaaS (Render / Fly.io / Railway), with managed Postgres and Redis add-ons, GitHub Actions CI/CD, and health-checked rolling deploys.

Full deployment guide, CI/CD pipeline, and monitoring setup: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Documentation Index

| Document | Contents |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product requirements, goals, non-goals, MVP scope |
| [`docs/FEATURES.md`](docs/FEATURES.md) | Full feature spec with priority/complexity |
| [`docs/UIUX.md`](docs/UIUX.md) | Dashboard information architecture and page specs |
| [`docs/TECHSTACK.md`](docs/TECHSTACK.md) | Technology choices and rationale |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Schema, indexes, Redis structures |
| [`docs/API.md`](docs/API.md) | Full REST API reference |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, task lifecycle, failure handling, scaling |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model, task execution security, checklist |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Local setup, Docker, production deployment, CI/CD |
| [`docs/AI_INSTRUCTIONS.md`](docs/AI_INSTRUCTIONS.md) | Engineering rules for AI agents working on this codebase |

## Future Improvements

- Backpressure-based submission throttling at high queue depth
- Additional built-in task types
- Outbound webhook callbacks on task completion
- Team/organization support
- Cursor-based pagination for high-volume task lists

## A Note on Metrics

Any throughput/latency numbers referenced in this project are either explicitly marked as design targets (e.g. "designed for 50–100 tasks/sec") or backed by an actual, reproducible load test documented in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — no numbers are invented or assumed.
