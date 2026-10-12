export interface User {
  id: string;
  email: string;
  role: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface Task {
  id: string;
  user_id: string;
  task_type: string;
  status: string;
  priority: number;
  idempotency_key: string | null;
  max_attempts: number;
  attempt_count: number;
  run_at: string | null;
  recurrence_rule: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface TaskAttempt {
  id: string;
  task_id: string;
  attempt_number: number;
  worker_id: string | null;
  started_at: string;
  finished_at: string | null;
  outcome: string | null;
  error_message: string | null;
  error_detail: Record<string, unknown> | null;
}

export interface TaskCreateRequest {
  task_type: "email_send" | "webhook_delivery" | string;
  payload: Record<string, unknown>;
  idempotency_key?: string;
  priority?: number;
  max_attempts?: number;
  run_at?: string;
  recurrence_rule?: string;
}

export interface TaskListResponse {
  data: Task[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
  };
}

export interface APIKey {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface CreateAPIKeyRequest {
  name: string;
}

export interface CreateAPIKeyResponse extends APIKey {
  key: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  field: string | null;
}

export interface ErrorResponse {
  error: ErrorDetail;
}

export interface Worker {
  id: string;
  hostname: string;
  status: string;
  concurrency_limit: number;
  current_task_count: number;
  last_heartbeat_at: string;
  tasks_processed: number;
  tasks_failed: number;
  registered_at: string;
}

export interface WorkerDetail extends Worker {
  recent_attempts: TaskAttempt[];
}

export interface QueueMetrics {
  task_type: string;
  main_depth: number;
  retry_depth: number;
  dlq_depth: number;
  total_depth: number;
}

export interface QueueStats {
  status_counts: Record<string, number>;
  throughput: {
    tasks_completed_per_minute_5m: number;
    tasks_completed_per_minute_60m: number;
  };
  latency: {
    avg_pickup_seconds: number | null;
    avg_execution_seconds: number | null;
  };
  generated_at: string;
}

export type TaskStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "retrying"
  | "dead_letter"
  | "cancelled";

export type WorkerStatus = "online" | "offline" | "draining";

export interface ReliabilitySnapshot {
  tasks_lost: number;
  duplicate_executions: number;
  tasks_recovered: number;
  retries: number;
  dlq_tasks: number;
  success_rate_percent: number;
}

export interface WindowedRate {
  "5m": number;
  "60m": number;
}

export interface ThroughputSnapshot {
  submissions_per_min: WindowedRate;
  completions_per_min: WindowedRate;
  total_submitted: number;
  history_points: number[];
  history_labels: string[];
}

export interface LastRecoveryEvent {
  worker_id: string | null;
  reason: string | null;
  recovered_tasks: number;
  occurred_at: string | null;
}

export interface WorkersSnapshot {
  active: number;
  healthy: number;
  busy: number;
  idle: number;
  recovering: number;
  unhealthy: number;
  running_tasks: number;
  capacity: number;
  last_recovery: LastRecoveryEvent | null;
}

export interface LatencySnapshot {
  pickup_seconds: {
    avg: number | null;
  };
  execution_seconds: {
    avg: number | null;
    p50: number | null;
    p95: number | null;
    p99: number | null;
  };
}

export interface BackpressureSnapshot {
  status: "NORMAL" | "THROTTLED" | "SATURATED";
  rate_limited_requests: number;
  utilization_percent: number;
}

export interface RecoverySnapshot {
  missed_heartbeats: number;
  recovery_events: number;
  stale_tasks: number;
}

export interface QueueTypeDetail {
  task_type: string;
  main_depth: number;
  retry_depth: number;
  dlq_depth: number;
  total_depth: number;
  status: "Healthy" | "Attention";
}

export interface QueuesSnapshot {
  main: number;
  retry: number;
  dlq: number;
  by_type: QueueTypeDetail[];
}

export interface ExternalLinks {
  grafana: string;
  jaeger: string;
  prometheus: string;
}

export interface MetricsSummaryResponse {
  timestamp: string;
  reliability: ReliabilitySnapshot;
  throughput: ThroughputSnapshot;
  workers: WorkersSnapshot;
  latency: LatencySnapshot;
  backpressure: BackpressureSnapshot;
  recovery: RecoverySnapshot;
  queues: QueuesSnapshot;
  links: ExternalLinks;
}

