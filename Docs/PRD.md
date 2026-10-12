# PRD.md — Product Requirements Document

## Product Name

**TaskForge** — Distributed Task Processing Platform

## Product Overview

TaskForge is a self-hosted, multi-user platform that lets developers offload asynchronous work — email sending, image resizing, and webhook delivery — to a horizontally scalable pool of workers, instead of doing that work inline in their own API request path or building queueing infrastructure themselves.

Developers submit tasks over a REST API (or the dashboard, for manual/testing use), TaskForge durably records and queues the task, a worker picks it up, executes it with resource limits and input validation, and the result (success, failure, retry, or dead-letter) is recorded and visible in real time.

TaskForge is not a general-purpose "run any code" platform. It ships with a small, fixed set of built-in task handlers. This bounded scope is intentional — it keeps the security model tractable and lets the project focus its engineering depth on the distributed-systems core (queueing, retries, idempotency, worker coordination, failure handling) rather than on sandboxing arbitrary user code.

## Problem Statement

Developers building products regularly need to do work that shouldn't block a user-facing request: sending a confirmation email, resizing an uploaded image, notifying a third-party webhook. Doing this work synchronously makes APIs slow and fragile — a slow email provider or an unreachable webhook endpoint becomes the caller's problem. The common alternative — bolt together a message broker, write ad hoc worker scripts, and hand-roll retry logic — is done badly more often than it's done well: retries without backoff, no dead-letter path, no idempotency guarantees, and no visibility into what's queued, running, or stuck.

## Why the Problem Matters

Asynchronous task processing is one of the most common building blocks in real backend systems (payment platforms, SaaS onboarding flows, media pipelines, notification systems all depend on it), and it is also one of the richest areas to demonstrate distributed-systems engineering judgment: delivery semantics, failure handling, idempotency, and horizontal scaling all show up naturally. A well-built task processing platform is both a practically useful piece of infrastructure and a strong, defensible artifact for engineering interviews.

## Target Users

- **Primary:** Backend/full-stack developers who need reliable background job processing for a web application, without operating a full message-broker deployment themselves.
- **Secondary (for this project's purposes):** Technical interviewers/recruiters evaluating the author's distributed-systems, backend, and system-design ability through a concrete, runnable system.

## User Personas

**Priya — Backend Developer at a small SaaS company.**
Needs to send onboarding emails and resize user-uploaded avatars without blocking API responses. Wants an API she can call from her existing service, a dashboard to see if something failed, and confidence that a task won't silently vanish or run twice.

**Admin/Operator — the person running TaskForge itself.**
Needs visibility into system health: queue depth, worker status, failure rates, and the ability to intervene (retry, cancel, inspect a stuck task) when something goes wrong.

## Goals

- Provide reliable, observable asynchronous task execution for a small, fixed set of realistic task types.
- Demonstrate correct distributed-systems handling of retries, idempotency, worker failure, and dead-lettering — not just a "happy path" queue.
- Provide a clean, professional developer-tool dashboard for operational visibility.
- Be deployable by a single developer within 1–2 months, on free/low-cost infrastructure, and defensible in a system-design interview.

## Non-Goals

- TaskForge is **not** a general code-execution platform (no arbitrary user-defined handlers/code upload).
- TaskForge does **not** target massive scale (no claims of production-grade throughput beyond what is actually measured).
- TaskForge does **not** include AI/LLM task types.
- TaskForge does **not** implement Kubernetes-based orchestration (Docker Compose + a managed PaaS instead).
- TaskForge does **not** implement multi-region or multi-tenant data isolation beyond basic per-user resource ownership.

## Core Use Cases

1. A developer registers, obtains an API key, and submits a task (e.g. "resize this image") via the REST API.
2. A worker picks up the task, executes the handler with resource limits, and records the result.
3. If the handler fails transiently, the task is retried with exponential backoff up to a configured limit.
4. If retries are exhausted, the task moves to a dead-letter queue and is visible as "failed — needs attention" in the dashboard.
5. A developer or admin logs into the dashboard, views task history, filters by status, inspects a failed task's error and attempt history, and manually retries or cancels it.
6. An admin monitors overall system health: queue depth, active workers, throughput, and failure rate, with Grafana dashboards backed by Prometheus metrics.
7. A developer schedules a recurring task (e.g. "send this webhook every hour").

## User Stories

- As a developer, I want to submit a task via API with an idempotency key, so that retrying my own request doesn't create duplicate work.
- As a developer, I want to see the status and history of a task I submitted, so I know whether it succeeded, is retrying, or failed.
- As a developer, I want failed tasks to land somewhere visible (a dead-letter queue) rather than silently disappearing.
- As an admin, I want to see worker health and queue depth in real time, so I can tell if the system is falling behind.
- As an admin, I want alerts when the failure rate or queue depth crosses a threshold.
- As a developer, I want to schedule a task to run later or on a recurring interval, without writing my own scheduler.

## Functional Requirements

- User registration and login (JWT-based dashboard sessions).
- API key generation, revocation, and use as an alternative auth method for the REST API.
- Task submission via REST API and dashboard, for built-in task types: **email send**, **image resize**, **webhook delivery**.
- Task states: `queued`, `running`, `succeeded`, `failed`, `retrying`, `dead_letter`, `cancelled`.
- Configurable retry policy per task (max attempts, backoff strategy) with a sane system default.
- Idempotency key support on task submission.
- Task scheduling: immediate, delayed (run-at), and recurring (cron-like) tasks.
- Task cancellation (best-effort; cannot interrupt a task already executing, but prevents future retries/starts).
- Worker registration and periodic heartbeats; workers marked unhealthy/offline after missed heartbeats.
- Dashboard views: task list/detail, queue depth, worker list/detail, system metrics.
- Dead-letter queue with manual replay capability.
- Prometheus metrics endpoint; Grafana dashboards for queue depth, throughput, latency, failure rate, worker health.

## Non-Functional Requirements

- **Reliability:** No task submitted successfully should be silently lost; every task reaches a terminal state (`succeeded`, `dead_letter`, or `cancelled`) or is visibly stuck and detectable.
- **Delivery semantics:** At-least-once task execution; correctness depends on task handlers behaving idempotently where feasible, or on idempotency keys at the submission layer.
- **Observability:** Every task's full attempt history (timestamps, worker, error) is queryable after the fact.
- **Security:** All task inputs are validated before reaching a handler; handler execution is resource-limited and isolated from the host and from other tasks.
- **Usability:** Dashboard reflects task and worker state within a few seconds of a change (polling or lightweight real-time updates — no strict real-time guarantee).

## MVP Scope

- Task submission (API + dashboard) for the 3 built-in task types.
- RabbitMQ-backed queueing with acks, retries with backoff, and a dead-letter exchange/queue.
- Worker pool: registration, heartbeats, concurrent task execution with per-worker concurrency limits.
- Postgres persistence for users, API keys, tasks, and task attempts.
- Redis for idempotency-key tracking and short-lived locks.
- JWT auth (dashboard) + API key auth (API), basic RBAC (`user`, `admin`).
- Dashboard: task list/detail, worker list/detail, basic queue/system metrics.
- Local Docker Compose environment; deploy to a managed PaaS.

## Phase 2 Features (Implemented)

- Prometheus + Grafana observability stack with alerting rules (`monitoring/alerting/rules.yml`).
- Scheduled and recurring task support via async scheduler service (`croniter` + Redis distributed locking).
- Sandboxed, resource-limited task execution (SSRF protections, timeouts, memory/dimension limits).
- CI/CD pipeline (`.github/workflows/ci.yml` lint, test against containers, build, dependency audit).
- Load testing harness (`load-tests/k6/taskforge.js`) measuring throughput across 4 load scenarios.

## Future Features (Not Committed)

- Team/organization support with shared task visibility.
- Webhook-based task completion callbacks to the submitting client.
- Additional built-in task types.
- Multi-region worker deployment.

## Success Metrics

Given this is a portfolio project rather than a live product, "success" is measured technically rather than commercially:

- System sustains its target load (50–100 tasks/sec) in a load test, with the actual measured number reported (not assumed).
- Zero task loss demonstrated under induced worker-crash and broker-restart scenarios in testing.
- Dead-letter and retry behavior is demonstrably correct (verified via integration tests that force handler failures).
- All documentation accurately reflects the implemented system (no aspirational claims).

## Performance Requirements

- Target sustained throughput: 50–100 tasks/sec, subject to load-test measurement; actual figure to be reported, not assumed, in all documentation and resume materials.
- Task pickup latency (queued → running) under normal load: target under 1 second at the design load level; to be measured.

## Reliability Requirements

- At-least-once execution guarantee (see ARCHITECTURE.md for full semantics).
- No permanent task loss on a single worker crash — in-flight tasks are re-delivered after a visibility-timeout style mechanism.
- No permanent task loss on a Redis restart — Redis holds idempotency/cache/lock data, not the durable task record (Postgres + RabbitMQ do).

## Scalability Requirements

- Workers scale horizontally by adding container instances; no code change required to add a worker.
- The system should demonstrate a documented scaling path from 1 worker to a handful of workers, with a bottleneck analysis (see ARCHITECTURE.md § Scaling).

## Constraints

- Solo developer, 1–2 months of build time.
- Comfortable stack: Python/FastAPI, React, PostgreSQL, Redis, RabbitMQ, Docker.
- Deployment target: managed PaaS (Render/Fly.io/Railway/ECS — finalized in DEPLOYMENT.md), not Kubernetes.
- Free/low-cost infrastructure preferred for the deployed demo.

## Assumptions

- Task handlers for the 3 built-in types can be implemented without paid third-party dependencies at meaningful scale (e.g. a transactional email provider's free tier, local image processing libraries, arbitrary but validated webhook URLs).
- The deployed demo environment will run at a modest, not production, scale — the throughput target is a design/load-test goal, not a live-traffic commitment.

## Risks

- **Scope creep:** distributed-systems projects tend to expand; task-type count is capped at 3 to protect the core-engine focus.
- **Broker operational complexity:** RabbitMQ adds real operational surface (exchanges, bindings, ack semantics) compared to a Redis-only queue; time-boxed learning is budgeted for this.
- **Security surface:** task handlers process externally supplied input (image bytes, webhook URLs); underestimating this risk (e.g. SSRF via webhook URLs) is treated as a first-class design concern, not an afterthought (see SECURITY.md).
- **Unverified performance claims:** any throughput/latency numbers reported without an actual load test will be flagged as invalid for resume use.

## Acceptance Criteria

- A user can register, obtain an API key, and submit a task of each of the 3 built-in types via the API.
- A submitted task is visible in the dashboard, transitions through correct states, and reaches a terminal state.
- Killing a worker mid-task results in the task being retried by another worker, not lost.
- A handler that always fails results in the task reaching `dead_letter` after the configured max attempts, visible and manually replayable in the dashboard.
- Submitting the same task twice with the same idempotency key results in only one execution.
- Prometheus metrics are scraped and visualized in at least one Grafana dashboard covering queue depth, throughput, and failure rate.
- The system is deployed and reachable at a public URL, running via the documented deployment process.
