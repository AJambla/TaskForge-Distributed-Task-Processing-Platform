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
  payload?: Record<string, unknown>;
  attempts?: TaskAttempt[];
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
  task_type: "email_send" | "image_resize" | "webhook_delivery";
  payload: Record<string, unknown>;
  idempotency_key?: string;
  priority?: number;
  max_attempts?: number;
  run_at?: string;
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
