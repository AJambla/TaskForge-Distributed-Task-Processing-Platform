import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import client from "../api/client";
import type { Task } from "../types";
import StatusPill from "./ui/StatusPill";
import { Spinner } from "./ui/Field";
import { durationBetween, formatSeconds } from "../lib/format";
import { Button } from "./ui/Button";

interface TaskDrawerProps {
  taskId: string | null;
  onClose: () => void;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="drawer__row">
      <span className="drawer__row-label">{label}</span>
      <span className="drawer__row-value">{children}</span>
    </div>
  );
}

export default function TaskDrawer({ taskId, onClose }: TaskDrawerProps) {
  const queryClient = useQueryClient();

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", taskId],
    queryFn: async () => {
      const res = await client.get<Task>(`/tasks/${taskId}`);
      return res.data;
    },
    enabled: Boolean(taskId),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["task", taskId] });
  };

  const cancelMutation = useMutation({
    mutationFn: () => client.post(`/tasks/${taskId}/cancel`),
    onSuccess: invalidate,
  });
  const retryMutation = useMutation({
    mutationFn: () => client.post(`/tasks/${taskId}/retry`),
    onSuccess: invalidate,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (taskId) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [taskId, onClose]);

  if (!taskId) return null;

  const pending = cancelMutation.isPending || retryMutation.isPending;
  const canCancel = task && (task.status === "queued" || task.status === "retrying");
  const canRetry = task && (task.status === "failed" || task.status === "dead_letter");

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Task details">
        <header className="drawer__head">
          <div>
            <p className="drawer__eyebrow">Task</p>
            <h2 className="drawer__title mono">{taskId}</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close drawer">
            <X size={16} />
          </button>
        </header>

        {isLoading && (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        )}

        {task && (
          <>
            <div className="drawer__status">
              <StatusPill status={task.status} />
              {task.recurrence_rule && (
                <span className="chip chip--queued">recurring · {task.recurrence_rule}</span>
              )}
            </div>

            <div className="drawer__rows">
              <Row label="Type">{task.task_type.replace(/_/g, " ")}</Row>
              <Row label="Priority">
                <span className="mono">{task.priority > 0 ? `+${task.priority}` : task.priority}</span>
              </Row>
              <Row label="Attempts">
                <span className="mono">
                  {task.attempt_count} / {task.max_attempts}
                </span>
              </Row>
              <Row label="Idempotency key">
                <span className="mono">{task.idempotency_key ?? "—"}</span>
              </Row>
              <Row label="Scheduled run">
                {task.run_at ? new Date(task.run_at).toLocaleString() : "—"}
              </Row>
            </div>

            <div className="drawer__timeline">
              <div className="timeline-node">
                <span className="timeline-node__dot" />
                <div>
                  <p className="timeline-node__label">Created</p>
                  <p className="timeline-node__time">{new Date(task.created_at).toLocaleString()}</p>
                </div>
              </div>
              <div className="timeline-node">
                <span className={`timeline-node__dot ${task.started_at ? "is-done" : ""}`} />
                <div>
                  <p className="timeline-node__label">Started</p>
                  <p className="timeline-node__time">
                    {task.started_at ? new Date(task.started_at).toLocaleString() : "waiting"}
                    {task.started_at && task.created_at && (
                      <span className="timeline-node__dur mono">
                        +{formatSeconds((new Date(task.started_at).getTime() - new Date(task.created_at).getTime()) / 1000)} pickup
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <div className="timeline-node">
                <span
                  className={`timeline-node__dot ${
                    task.completed_at ? (task.status === "succeeded" ? "is-done" : "is-fail") : ""
                  }`}
                />
                <div>
                  <p className="timeline-node__label">Completed</p>
                  <p className="timeline-node__time">
                    {task.completed_at ? new Date(task.completed_at).toLocaleString() : "—"}
                    {task.started_at && task.completed_at && (
                      <span className="timeline-node__dur mono">
                        {durationBetween(task.started_at, task.completed_at)} run
                      </span>
                    )}
                  </p>
                </div>
              </div>
            </div>

            <div className="drawer__actions">
              <Link to={`/app/tasks/${task.id}`} className="btn btn--quiet btn--sm">
                Full page
              </Link>
              {canRetry && (
                <Button
                  variant="nav"
                  size="sm"
                  disabled={pending}
                  onClick={() => retryMutation.mutate()}
                >
                  Retry task
                </Button>
              )}
              {canCancel && (
                <Button
                  variant="danger"
                  size="sm"
                  disabled={pending}
                  onClick={() => cancelMutation.mutate()}
                >
                  Cancel task
                </Button>
              )}
            </div>
            {(cancelMutation.error || retryMutation.error) && (
              <p className="drawer__error">
                {(
                  (cancelMutation.error ?? retryMutation.error) as {
                    response?: { data?: { error?: { message?: string } } };
                  }
                )?.response?.data?.error?.message ?? "Action failed."}
              </p>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
