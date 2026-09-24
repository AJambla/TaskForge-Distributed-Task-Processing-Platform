import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import client from "../../api/client";
import type { Task, TaskAttempt } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { PageLoading } from "../../components/ui/Field";
import StatusPill, { OutcomeText } from "../../components/ui/StatusPill";
import { Clock, Calendar, RotateCcw, ChevronLeft } from "lucide-react";

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [showError, setShowError] = useState<number | null>(null);

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", id],
    queryFn: async () => {
      const response = await client.get(`/tasks/${id}`);
      return response.data as Task & { attempts?: TaskAttempt[] };
    },
    enabled: !!id,
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

  const attempts = task.attempts || [];
  const title = task.task_type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());

  return (
    <div className="space-y-8">
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
        actions={<StatusPill status={task.status} />}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          { icon: <Clock size={14} />, label: "Created", value: new Date(task.created_at).toLocaleString() },
          {
            icon: <Calendar size={14} />,
            label: "Started",
            value: task.started_at ? new Date(task.started_at).toLocaleString() : "—",
          },
          {
            icon: <RotateCcw size={14} />,
            label: "Attempts",
            value: `${task.attempt_count} / ${task.max_attempts}`,
          },
        ].map((s, i) => (
          <div key={s.label} className="stat rise" style={{ "--d": `${0.1 + i * 0.06}s` } as React.CSSProperties}>
            <div className="stat__label">
              {s.icon} {s.label}
            </div>
            <p className="stat__value" style={{ fontSize: 18 }}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      <Panel title="Payload" delay={0.18}>
        <pre
          className="mono overflow-x-auto p-4 text-xs"
          style={{ background: "var(--app-bg)", border: "1px solid var(--line)", color: "var(--muted)" }}
        >
          {JSON.stringify(task.payload, null, 2)}
        </pre>
      </Panel>

      {attempts.length > 0 && (
        <Panel title="Attempt History" subtitle={`${attempts.length} recorded attempts`} delay={0.24} bodyClassName="">
          <div className="divide-y" style={{ borderColor: "var(--line-soft)" }}>
            {attempts.map((attempt, idx) => (
              <div key={attempt.id} className="px-6 py-4" style={{ borderTop: idx ? "1px solid var(--line-soft)" : undefined }}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium" style={{ color: "var(--text)" }}>
                      Attempt {attempt.attempt_number}
                    </span>
                    <OutcomeText outcome={attempt.outcome ?? "running"} />
                  </div>
                  <span className="text-xs" style={{ color: "var(--subtle)" }}>
                    {new Date(attempt.started_at).toLocaleString()}
                  </span>
                </div>
                {attempt.error_message && (
                  <>
                    <p className="mt-2 text-sm" style={{ color: "#b91c1c" }}>
                      {attempt.error_message}
                    </p>
                    <button
                      onClick={() => setShowError(showError === idx ? null : idx)}
                      className="navlink mt-2 !text-xs"
                      style={{ color: "var(--brand)" }}
                    >
                      {showError === idx ? "Hide" : "Show"} error details
                    </button>
                    {showError === idx && attempt.error_detail && (
                      <pre
                        className="mono mt-2 overflow-x-auto p-3 text-xs"
                        style={{
                          background: "rgba(185,28,28,0.05)",
                          border: "1px solid rgba(185,28,28,0.2)",
                          color: "#b91c1c",
                        }}
                      >
                        {JSON.stringify(attempt.error_detail, null, 2)}
                      </pre>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
