import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import client from "../../api/client";
import type { WorkerDetail } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { PageLoading, EmptyState } from "../../components/ui/Field";
import { Server, ChevronLeft } from "lucide-react";

export default function WorkerDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ["worker", id],
    queryFn: async () => {
      const response = await client.get(`/workers/${id}`);
      return response.data as WorkerDetail;
    },
    refetchInterval: 5000,
    enabled: Boolean(id),
  });

  const isForbidden =
    (error as { response?: { status?: number } })?.response?.status === 403;

  if (isForbidden) {
    return (
      <Panel delay={0.05}>
        <EmptyState icon={<Server size={22} />} title="Worker visibility is restricted to admins." />
      </Panel>
    );
  }

  if (isLoading) return <PageLoading />;

  if (!data) {
    return (
      <Panel delay={0.05}>
        <EmptyState icon={<Server size={22} />} title="Worker not found." />
      </Panel>
    );
  }

  const stats = [
    { label: "Status", value: data.status },
    { label: "Load", value: `${data.current_task_count}/${data.concurrency_limit}` },
    { label: "Tasks Processed", value: String(data.tasks_processed) },
    { label: "Tasks Failed", value: String(data.tasks_failed) },
  ];

  return (
    <div className="space-y-8">
      <div className="wipe" style={{ "--d": "0.02s" } as React.CSSProperties}>
        <Link
          to="/app/workers"
          className="inline-flex items-center gap-1.5 text-sm"
          style={{ color: "var(--subtle)" }}
        >
          <ChevronLeft size={14} /> Back to workers
        </Link>
      </div>

      <PageHeader
        title={data.hostname}
        subtitle={`${data.status} · registered ${new Date(data.registered_at).toLocaleString()}`}
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {stats.map((s, i) => (
          <div key={s.label} className="stat rise" style={{ "--d": `${0.1 + i * 0.06}s` } as React.CSSProperties}>
            <p className="stat__label">{s.label}</p>
            <p className="stat__value">{s.value}</p>
          </div>
        ))}
      </div>

      <Panel title="Recent Attempts" delay={0.2} bodyClassName="overflow-x-auto">
        {!data.recent_attempts.length ? (
          <EmptyState title="No attempts recorded for this worker" />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Task</th>
                <th>Attempt</th>
                <th>Outcome</th>
                <th>Started</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_attempts.map((attempt) => (
                <tr key={attempt.id}>
                  <td>
                    <Link to={`/app/tasks/${attempt.task_id}`} className="navlink mono !text-xs">
                      {attempt.task_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="mono text-xs">#{attempt.attempt_number}</td>
                  <td>
                    <span
                      className="font-medium"
                      style={{
                        color:
                          attempt.outcome === "success"
                            ? "#067647"
                            : attempt.outcome === "failure"
                              ? "#b91c1c"
                              : attempt.outcome === "timeout"
                                ? "#c2410c"
                                : "var(--subtle)",
                      }}
                    >
                      {attempt.outcome ?? "running"}
                    </span>
                  </td>
                  <td style={{ color: "var(--subtle)" }}>
                    {new Date(attempt.started_at).toLocaleString()}
                  </td>
                  <td
                    className="block max-w-xs truncate"
                    style={{ color: attempt.error_message ? "#b91c1c" : "var(--subtle)" }}
                    title={attempt.error_message ?? undefined}
                  >
                    {attempt.error_message ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
