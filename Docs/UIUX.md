# UIUX.md — UI/UX Design

## Information Architecture

```text
Dashboard (authenticated app shell)
├── Overview          — system-wide KPIs and recent activity
├── Tasks
│   ├── Task List      — filterable/sortable table of all tasks
│   └── Task Detail     — single task deep-dive
├── Workers
│   ├── Worker List     — all registered workers and status
│   └── Worker Detail    — single worker deep-dive
├── Queues              — queue depth, DLQ, per-queue metrics
├── Metrics             — links out to Grafana (or embedded panels)
└── Settings
    ├── API Keys        — create/revoke API keys
    └── Account          — profile, password
```

No "Logs" as a standalone top-level page — logs are scoped to a task or worker and surfaced in their detail views, to avoid an unfocused firehose page.

## Page Specifications

### Overview

**Purpose:** Answer "is the system healthy right now?" in one glance.

**Layout:** Top row of KPI cards, followed by a recent-activity table and a small throughput sparkline.

**Components:**
- KPI cards: Queue depth, Active workers, Tasks/sec (rolling), Success rate (last hour), Failed/DLQ count.
- Recent tasks table (last ~20 tasks, all users if admin, own tasks if regular user).
- Throughput mini-chart (last hour).

**Data displayed:** Aggregated counts pulled from the API; refreshed via polling (e.g. every 5s) rather than a hard real-time requirement.

**User actions:** Click a KPI card to jump to the filtered Tasks or Queues view; click a recent task to open its detail.

**Loading state:** Skeleton cards and skeleton table rows.

**Empty state:** "No tasks yet — submit your first task via the API" with a link to API docs, shown only for a brand-new account with zero tasks ever.

**Error state:** Inline banner: "Couldn't load system status — retrying…" with automatic retry; cards fall back to last-known values where available.

**Success state:** N/A (informational page).

**Responsive behavior:** KPI cards collapse from a 5-column to a 2-column to a 1-column grid on narrower viewports; table becomes horizontally scrollable.

---

### Task List

**Purpose:** Find and triage tasks.

**Layout:** Filter bar above a dense data table.

**Components:** Table with columns — Task ID, Type, Status (colored badge), Priority, Created At, Duration, Retry Count, Worker. Filters for status, task type, and time range; search by task ID or idempotency key.

**Data displayed:** Paginated task list from `GET /api/v1/tasks`.

**User actions:** Click a row to open Task Detail; bulk-select for cancel (queued tasks only); "Retry" quick-action on failed/dead-letter rows.

**Loading state:** Skeleton table rows.

**Empty state:** "No tasks match these filters" with a "Clear filters" action.

**Error state:** Inline error banner above the table; table area shows a retry button.

**Success state:** Toast confirmation on cancel/retry actions ("Task retried").

**Responsive behavior:** Lower-priority columns (Worker, Priority) hide below a breakpoint; row remains tappable to view full detail.

---

### Task Detail

**Purpose:** Full inspection of a single task for debugging.

**Layout:** Header with ID/status/actions, followed by two sections: metadata panel and attempt-history timeline.

**Data displayed:**
- Task ID, Status, Queue/type, Priority, Created time, Started time, Completed time, Duration, Retry count, Assigned worker.
- Payload (formatted JSON, redacted for known-sensitive fields).
- Attempt-by-attempt history: each attempt's worker, start/end time, outcome, and error message/stack if failed.

**User actions:** Cancel (if queued), Retry now (if failed/dead-letter), Copy task ID, Copy payload.

**Loading state:** Skeleton metadata panel and skeleton timeline.

**Empty state:** N/A (always has at least the submission record).

**Error state:** "Task not found" (404) or "Couldn't load task" with retry, distinguished clearly.

**Success state:** Toast confirmation on cancel/retry.

**Responsive behavior:** Two-column metadata/timeline layout collapses to a single stacked column on mobile.

---

### Worker List

**Purpose:** See the health and load of the worker fleet.

**Layout:** Table similar to Task List.

**Components:** Table with columns — Worker ID, Status (online/offline/draining, colored badge), Host/container, Current task count / concurrency limit, Last heartbeat, Tasks processed (lifetime), Failure rate.

**Data displayed:** From `GET /api/v1/workers`.

**User actions:** Click a row for Worker Detail.

**Loading/Empty/Error states:** Same pattern as Task List.

**Responsive behavior:** Same pattern as Task List.

---

### Worker Detail

**Purpose:** Debug a specific worker.

**Data displayed:**
- Worker ID, Status, Host/container identifier, Current task(s) being processed, Concurrency limit, Last heartbeat timestamp, Tasks processed, Success/failure counts, Failure rate.
- Recent task history processed by this worker.

**User actions:** None destructive from the UI in MVP (no remote worker shutdown) — informational only.

**Loading/Empty/Error states:** Same pattern as Task Detail.

---

### Queues

**Purpose:** Operational view of queue health, separate from individual tasks.

**Components:** Per-queue cards (main queue, retry queue, dead-letter queue) showing depth, oldest message age, and consumption rate. DLQ card includes a "View dead-lettered tasks" link into a pre-filtered Task List.

**States:** Same loading/empty/error patterns as Overview.

---

### Settings — API Keys

**Purpose:** Manage programmatic access credentials.

**Components:** Table of existing keys (name, created date, last used, masked value) with Create and Revoke actions. Full key value is shown exactly once, at creation time, with a copy button and an explicit "you won't see this again" warning.

**User actions:** Create key (name it), Revoke key (confirmation modal).

**Error state:** Inline validation on key naming; revoke failures shown as a toast.

---

## Design System

- **Typography:** A clean system/sans stack (e.g. Inter or system-ui) for UI text; a monospace font (e.g. JetBrains Mono) for task IDs, payload JSON, and logs.
- **Spacing:** 4px base unit, consistent 8/12/16/24px rhythm for padding and gaps — standard dense-dashboard spacing, not overly airy.
- **Status indicators:** Consistent color-coded badges across the whole app — e.g. gray (queued), blue (running), green (succeeded), amber (retrying), red (failed), dark red/purple (dead_letter), slate (cancelled). Same palette used in charts.
- **Tables:** Dense, sortable, sticky header row, zebra-free (rely on row hover + borders for readability at this density).
- **Cards:** Used for KPIs and queue summaries; minimal shadow, clear numeric hierarchy (large number, small label).
- **Charts:** Line charts for throughput/latency over time, bar for per-status counts — rendered with a lightweight charting library (see TECHSTACK.md).
- **Modals:** Used only for destructive/irreversible confirmations (revoke API key, cancel task) — not for primary navigation flows.
- **Forms:** Minimal — task submission is primarily an API action; the few in-dashboard forms (API key creation, login) use inline validation and clear error text under each field.
- **Notifications:** Toast notifications (bottom-right, auto-dismiss) for action confirmations; persistent banners for system-level errors (e.g. "can't reach API").

**Overall aesthetic:** Clean, dense, professional developer-tool look — closer to Stripe's or Vercel's dashboards than a consumer app. Dark-mode-friendly color choices from the start, even if only light mode ships in v1.
