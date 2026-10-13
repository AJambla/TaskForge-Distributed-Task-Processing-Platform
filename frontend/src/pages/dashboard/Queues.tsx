import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertOctagon, Layers, RefreshCcw, Timer, RotateCw } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import StatCard from "../../components/ui/StatCard";
import { BarRow } from "../../components/ui/Charts";
import { Button } from "../../components/ui/Button";
import client from "../../api/client";
import { useQueueStats, useQueues, useDLQInspection } from "../../api/queries";
import { formatNumber, formatSeconds, relativeTime, shortId } from "../../lib/format";
import { EmptyState } from "../../components/ui/Field";

export default function Queues() {
  const queryClient = useQueryClient();
  const queuesQuery = useQueues();
  const statsQuery = useQueueStats();
  const { data: dlqData, isLoading: dlqLoading } = useDLQInspection();
  const [redriveMessage, setRedriveMessage] = useState<string | null>(null);

  const redriveMutation = useMutation({
    mutationFn: async () => {
      const res = await client.post<{ redriven_count: number }>("/queues/dlq/redrive");
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["queues"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setRedriveMessage(`Redrove ${data.redriven_count} tasks`);
      setTimeout(() => setRedriveMessage(null), 4000);
    },
    onError: (err: any) => {
      setRedriveMessage(err?.response?.data?.detail || "Redrive failed");
      setTimeout(() => setRedriveMessage(null), 4000);
    },
  });

  const retryTaskMutation = useMutation({
    mutationFn: async (taskId: string) => {
      await client.post(`/tasks/${taskId}/retry`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queues"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const totals = useMemo(() => {
    const queues = queuesQuery.data ?? [];
    return {
      main: queues.reduce((s, q) => s + q.main_depth, 0),
      retry: queues.reduce((s, q) => s + q.retry_depth, 0),
      dlq: queues.reduce((s, q) => s + q.dlq_depth, 0),
      total: queues.reduce((s, q) => s + q.total_depth, 0),
      max: Math.max(1, ...queues.map((q) => Math.max(q.main_depth, q.retry_depth, q.dlq_depth))),
    };
  }, [queuesQuery.data]);

  const stats = statsQuery.data;
  const queues = queuesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Queues"
        subtitle="Live RabbitMQ depths across main, retry and dead-letter queues"
        actions={
          <div className="flex items-center gap-3">
            {redriveMessage && (
              <span className="mono text-xs" style={{ color: "var(--accent)" }}>
                {redriveMessage}
              </span>
            )}
            <Button
              variant="quiet"
              size="sm"
              disabled={redriveMutation.isPending || totals.dlq === 0}
              onClick={() => redriveMutation.mutate()}
            >
              <RotateCw
                size={13}
                className={redriveMutation.isPending ? "animate-spin" : ""}
                style={{ display: "inline", marginRight: "6px" }}
              />
              {redriveMutation.isPending ? "Redriving..." : "Redrive DLQ"}
            </Button>
            {queuesQuery.data && (
              <span className="mono text-xs" style={{ color: "var(--subtle)" }}>
                refreshing every 5s
              </span>
            )}
          </div>
        }
      />

      <div className="ov-stats">
        <StatCard
          label="Total backlog"
          value={formatNumber(totals.total)}
          icon={<Layers size={14} />}
          sub={`${formatNumber(totals.main)} main · ${formatNumber(totals.retry)} retry`}
          delay={0.05}
        />
        <StatCard
          label="Dead-letter"
          value={formatNumber(totals.dlq)}
          icon={<AlertOctagon size={14} />}
          accent="#6d28d9"
          sub="failed after all attempts"
          delay={0.1}
        />
        <StatCard
          label="Completed / min"
          value={stats ? stats.throughput.tasks_completed_per_minute_5m.toFixed(1) : "—"}
          icon={<RefreshCcw size={14} />}
          accent="#067647"
          sub={stats ? `${stats.throughput.tasks_completed_per_minute_60m.toFixed(1)} avg over 60m` : undefined}
          delay={0.15}
        />
        <StatCard
          label="Avg pickup delay"
          value={stats ? formatSeconds(stats.latency.avg_pickup_seconds) : "—"}
          icon={<Timer size={14} />}
          accent="#d97706"
          sub={stats ? `snapshot ${relativeTime(stats.generated_at)}` : undefined}
          delay={0.2}
        />
      </div>

      {queues.length === 0 ? (
        <Panel delay={0.2}>
          <EmptyState
            icon={<Layers size={22} />}
            title="No queue data"
            hint="Queues appear once task types are registered with the broker."
          />
        </Panel>
      ) : (
        <div className="ov-grid-2">
          {queues.map((q, i) => (
            <Panel
              key={q.task_type}
              title={q.task_type.replace(/_/g, " ")}
              subtitle={`${formatNumber(q.total_depth)} messages waiting`}
              delay={0.22 + i * 0.06}
            >
              <div className="space-y-2.5">
                <BarRow label="Main" value={q.main_depth} max={totals.max} />
                <BarRow
                  label="Retry"
                  value={q.retry_depth}
                  max={totals.max}
                  color="#d97706"
                />
                <BarRow
                  label="DLQ"
                  value={q.dlq_depth}
                  max={totals.max}
                  color="#6d28d9"
                />
              </div>
            </Panel>
          ))}
        </div>
      )}

      <Panel
        title={
          <div className="flex items-center justify-between w-full">
            <span className="inline-flex items-center gap-2">
              <AlertOctagon size={14} style={{ color: "#a855f7" }} /> Dead-Letter Queue Inspection
            </span>
            <span className="mono text-xs" style={{ color: "var(--subtle)" }}>
              {dlqData?.recent_dead_tasks.length ?? 0} recent failures
            </span>
          </div>
        }
        delay={0.3}
        bodyClassName="p-0"
      >
        {dlqLoading ? (
          <div className="p-6 text-center text-xs" style={{ color: "var(--subtle)" }}>
            Loading dead-letter tasks…
          </div>
        ) : !dlqData || dlqData.recent_dead_tasks.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No dead-letter tasks"
              hint="Tasks routed to the DLQ after exhausting retries will appear here for inspection."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="tbl w-full text-xs">
              <thead>
                <tr>
                  <th>Task ID</th>
                  <th>Task Type</th>
                  <th>Failed Attempts</th>
                  <th>Completed At</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {dlqData.recent_dead_tasks.map((task) => (
                  <tr key={task.id}>
                    <td>
                      <Link
                        to={`/app/tasks/${task.id}`}
                        className="mono font-semibold text-blue-400 hover:underline"
                        title="View task detail and diagnostics"
                      >
                        {shortId(task.id)}
                      </Link>
                    </td>
                    <td>
                      <span className="font-medium" style={{ color: "var(--text)" }}>
                        {task.task_type.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="mono">
                      <span className="chip chip--failed font-mono text-[11px]">
                        {task.attempt_count} attempts
                      </span>
                    </td>
                    <td className="mono" title={task.completed_at ? new Date(task.completed_at).toLocaleString() : ""}>
                      {task.completed_at ? relativeTime(task.completed_at) : "—"}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        onClick={() => retryTaskMutation.mutate(task.id)}
                        disabled={retryTaskMutation.isPending}
                        className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-1 rounded hover:bg-white/10 transition cursor-pointer"
                        style={{ color: "var(--brand)" }}
                        title="Retry this individual task"
                      >
                        <RotateCw size={12} className={retryTaskMutation.isPending ? "animate-spin" : ""} />
                        Retry
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
