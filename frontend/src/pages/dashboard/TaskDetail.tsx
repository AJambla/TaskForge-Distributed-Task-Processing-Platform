import { useParams, useNavigate, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "../../api/client";
import type { Task } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { PageLoading } from "../../components/ui/Field";
import StatusPill from "../../components/ui/StatusPill";
import { Button } from "../../components/ui/Button";
import FailureDiagnosticsCard from "../../components/FailureDiagnosticsCard";
import JsonViewer from "../../components/JsonViewer";
import { useTaskEvents } from "../../hooks/useTaskEvents";
import { ChevronLeft, ExternalLink } from "lucide-react";
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

  const isTerminal = task
    ? ["succeeded", "failed", "dead_letter", "cancelled"].includes(task.status)
    : false;
  useTaskEvents(id ?? null, !isTerminal);

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
          <div className="flex flex-wrap items-center gap-3">
            <StatusPill status={task.status} />
            {task.trace_url && (
              <a
                href={task.trace_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition hover:opacity-85"
                style={{
                  background: "rgba(59, 130, 246, 0.12)",
                  color: "#60a5fa",
                  border: "1px solid rgba(59, 130, 246, 0.3)",
                }}
                title="Inspect OpenTelemetry trace in Jaeger"
              >
                <ExternalLink size={12} />
                View in Jaeger
              </a>
            )}
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

      {task.diagnostics && (
        <div className="wipe" style={{ "--d": "0.08s" } as React.CSSProperties}>
          <FailureDiagnosticsCard diagnostics={task.diagnostics} />
        </div>
      )}

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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Panel title="Input Payload" delay={0.2}>
          <JsonViewer
            data={task.payload}
            label="Payload"
            emptyText="No payload provided"
          />
        </Panel>
        <Panel title="Execution Result" delay={0.24}>
          <JsonViewer
            data={task.result}
            label="Result"
            emptyText={task.status === "succeeded" ? "Completed with no return value" : "No execution result recorded"}
            highlightSuccess={task.status === "succeeded" && Boolean(task.result)}
          />
        </Panel>
      </div>

      <div className="ov-grid-2">
        <Panel title="Lifecycle & Execution" delay={0.28}>
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

          {task.attempts && task.attempts.length > 0 ? (
            <div className="mt-6 space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--subtle)" }}>
                Attempt History ({task.attempts.length})
              </h4>
              <div className="overflow-x-auto rounded border" style={{ borderColor: "var(--line)" }}>
                <table className="tbl w-full text-xs">
                  <thead>
                    <tr>
                      <th>Attempt</th>
                      <th>Worker</th>
                      <th>Started</th>
                      <th>Duration</th>
                      <th>Outcome</th>
                      <th>Trace</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {task.attempts.map((attempt) => (
                      <tr key={attempt.id}>
                        <td className="mono font-semibold">#{attempt.attempt_number}</td>
                        <td>
                          {attempt.worker_id ? (
                            <span className="mono text-[11px]" title={attempt.worker_id}>
                              {attempt.worker_id.slice(0, 10)}
                            </span>
                          ) : (
                            <span style={{ color: "var(--subtle)" }}>—</span>
                          )}
                        </td>
                        <td className="mono text-[11px]">
                          {new Date(attempt.started_at).toLocaleTimeString()}
                        </td>
                        <td className="mono text-[11px]">
                          {attempt.finished_at
                            ? durationBetween(attempt.started_at, attempt.finished_at)
                            : "running"}
                        </td>
                        <td>
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium mono ${
                              attempt.outcome === "success" || attempt.outcome === "succeeded"
                                ? "chip chip--succeeded"
                                : attempt.outcome === "timeout"
                                ? "chip chip--retrying"
                                : "chip chip--failed"
                            }`}
                          >
                            {attempt.outcome || "pending"}
                          </span>
                        </td>
                        <td>
                          {attempt.trace_id ? (
                            <a
                              href={`http://localhost:16686/trace/${attempt.trace_id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 mono text-[11px] text-blue-400 hover:underline"
                              title="View trace in Jaeger"
                            >
                              <ExternalLink size={10} />
                              {attempt.trace_id.slice(0, 6)}…
                            </a>
                          ) : (
                            <span style={{ color: "var(--subtle)" }}>—</span>
                          )}
                        </td>
                        <td className="max-w-xs truncate" title={attempt.error_message || ""}>
                          {attempt.error_message ? (
                            <span className="text-rose-400 font-mono text-[11px]">
                              {attempt.error_message}
                            </span>
                          ) : (
                            <span style={{ color: "var(--subtle)" }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="mt-5 text-xs" style={{ color: "var(--subtle)" }}>
              No individual attempt logs recorded yet.
            </p>
          )}
        </Panel>

        <Panel title="Details" delay={0.32}>
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
            <Row label="Trace ID">
              {task.trace_id ? (
                <span className="mono text-xs">{task.trace_id}</span>
              ) : (
                <span style={{ color: "var(--subtle)" }}>—</span>
              )}
            </Row>
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
