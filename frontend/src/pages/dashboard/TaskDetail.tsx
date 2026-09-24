import { useParams, useNavigate, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "../../api/client";
import type { Task } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { PageLoading } from "../../components/ui/Field";
import StatusPill from "../../components/ui/StatusPill";
import { Button } from "../../components/ui/Button";
import { ChevronLeft } from "lucide-react";
import { durationBetween, formatSeconds, relativeTime } from "../../lib/format";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="drawer__row">
      <span className="drawer__row-label">{label}</span>
      <span className="drawer__row-value">{children}</span>
    </div>
  );
}

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", id],
    queryFn: async () => {
      const response = await client.get<Task>(`/tasks/${id}`);
      return response.data;
    },
    enabled: !!id,
    refetchInterval: 10_000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["task", id] });
  };
  const cancelMutation = useMutation({
    mutationFn: () => client.post(`/tasks/${id}/cancel`),
    onSuccess: invalidate,
  });
  const retryMutation = useMutation({
    mutationFn: () => client.post(`/tasks/${id}/retry`),
    onSuccess: invalidate,
  });

  if (isLoading) return <PageLoading />;

  if (!task) {
    return (
      <Panel delay={0.05}>
        <p style={{ color: "var(--subtle)" }}>Task not found.</p>
        <button
          onClick={() => navigate("/app/tasks")}
          className="navlink mt-4"
          style={{ color: "var(--brand)" }}
        >
          ← Back to tasks
        </button>
      </Panel>
    );
  }

  const title = task.task_type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());
  const canCancel = task.status === "queued" || task.status === "retrying";
  const canRetry = task.status === "failed" || task.status === "dead_letter";
  const failedTerminal = ["failed", "dead_letter", "cancelled"].includes(task.status);

  return (
    <div className="space-y-6">
      <div className="wipe" style={{ "--d": "0.02s" } as React.CSSProperties}>
        <Link
          to="/app/tasks"
          className="inline-flex items-center gap-1.5 text-sm"
          style={{ color: "var(--subtle)" }}
        >
          <ChevronLeft size={14} /> Back to tasks
        </Link>
      </div>

      <PageHeader
        title={title}
        subtitle={
          <span className="mono text-xs" style={{ color: "var(--subtle)" }}>
            {task.id}
          </span>
        }
        actions={
          <div className="flex items-center gap-3">
            <StatusPill status={task.status} />
            {canRetry && (
              <Button
                variant="nav"
                size="sm"
                disabled={retryMutation.isPending}
                onClick={() => retryMutation.mutate()}
              >
                Retry
              </Button>
            )}
            {canCancel && (
              <Button
                variant="danger"
                size="sm"
                disabled={cancelMutation.isPending}
                onClick={() => cancelMutation.mutate()}
              >
                Cancel
              </Button>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          {
            label: "Created",
            value: relativeTime(task.created_at),
            sub: new Date(task.created_at).toLocaleString(),
          },
          {
            label: "Duration",
            value: task.started_at
              ? durationBetween(task.started_at, task.completed_at)
              : "—",
            sub: task.started_at && !task.completed_at ? "still running" : task.started_at
              ? "execution time"
              : "not started yet",
          },
          {
            label: "Pickup delay",
            value:
              task.started_at && task.created_at
                ? formatSeconds(
                    (new Date(task.started_at).getTime() - new Date(task.created_at).getTime()) /
                      1000
                  )
                : "—",
            sub: "created → started",
          },
        ].map((s, i) => (
          <div
            key={s.label}
            className="stat rise"
            style={{ "--d": `${0.1 + i * 0.06}s` } as React.CSSProperties}
          >
            <div className="stat__label">{s.label}</div>
            <p className="stat__value" style={{ fontSize: 22 }}>
              {s.value}
            </p>
            <p className="stat__sub">{s.sub}</p>
          </div>
        ))}
      </div>

      <div className="ov-grid-2">
        <Panel title="Lifecycle" delay={0.16}>
          <div className="drawer__timeline">
            <div className="timeline-node">
              <span className="timeline-node__dot is-done" />
              <div>
                <p className="timeline-node__label">Created · queued</p>
                <p className="timeline-node__time">{new Date(task.created_at).toLocaleString()}</p>
              </div>
            </div>
            <div className="timeline-node">
              <span className={`timeline-node__dot ${task.started_at ? "is-done" : ""}`} />
              <div>
                <p className="timeline-node__label">Picked up by worker</p>
                <p className="timeline-node__time">
                  {task.started_at ? new Date(task.started_at).toLocaleString() : "waiting"}
                </p>
              </div>
            </div>
            <div className="timeline-node">
              <span
                className={`timeline-node__dot ${
                  task.completed_at ? (failedTerminal ? "is-fail" : "is-done") : ""
                }`}
              />
              <div>
                <p className="timeline-node__label">
                  {failedTerminal ? "Finished (unsuccessful)" : "Completed"}
                </p>
                <p className="timeline-node__time">
                  {task.completed_at ? new Date(task.completed_at).toLocaleString() : "—"}
                </p>
              </div>
            </div>
          </div>
          <p className="mt-5 text-xs" style={{ color: "var(--subtle)" }}>
            Per-attempt history is tracked on the worker that executed the task.
          </p>
        </Panel>

        <Panel title="Details" delay={0.22}>
          <div className="drawer__rows">
            <Row label="Status">
              <StatusPill status={task.status} />
            </Row>
            <Row label="Attempts">
              <span className="mono">
                {task.attempt_count} / {task.max_attempts}
              </span>
            </Row>
            <Row label="Priority">
              <span className="mono">{task.priority > 0 ? `+${task.priority}` : task.priority}</span>
            </Row>
            <Row label="Idempotency key">
              <span className="mono">{task.idempotency_key ?? "—"}</span>
            </Row>
            <Row label="Scheduled run">
              {task.run_at ? new Date(task.run_at).toLocaleString() : "—"}
            </Row>
            <Row label="Recurrence">{task.recurrence_rule ?? "—"}</Row>
            <Row label="Owner">
              <span className="mono">{task.user_id.slice(0, 8)}…</span>
            </Row>
          </div>
          {(cancelMutation.error || retryMutation.error) && (
            <p className="drawer__error mt-4">
              {(
                (cancelMutation.error ?? retryMutation.error) as {
                  response?: { data?: { error?: { message?: string } } };
                }
              )?.response?.data?.error?.message ?? "Action failed."}
            </p>
          )}
        </Panel>
      </div>
    </div>
  );
}
