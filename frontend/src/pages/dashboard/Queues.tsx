import { useMemo } from "react";
import { AlertOctagon, Layers, RefreshCcw, Timer } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import StatCard from "../../components/ui/StatCard";
import { BarRow } from "../../components/ui/Charts";
import { useAuth } from "../../context/AuthContext";
import { useQueueStats, useQueues } from "../../api/queries";
import { formatNumber, formatSeconds, relativeTime } from "../../lib/format";
import { EmptyState } from "../../components/ui/Field";

const isForbidden = (error: unknown) =>
  (error as { response?: { status?: number } })?.response?.status === 403;

export default function Queues() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const queuesQuery = useQueues(isAdmin);
  const statsQuery = useQueueStats(isAdmin);

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

  if (!isAdmin || isForbidden(queuesQuery.error) || isForbidden(statsQuery.error)) {
    return (
      <div>
        <PageHeader title="Queues" subtitle="Live RabbitMQ depths per task type" />
        <Panel delay={0.08}>
          <EmptyState
            icon={<Layers size={22} />}
            title="Queue visibility is restricted to admins."
            hint="Your own task statuses are on the Tasks and Overview pages."
          />
        </Panel>
      </div>
    );
  }

  const stats = statsQuery.data;
  const queues = queuesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Queues"
        subtitle="Live RabbitMQ depths across main, retry and dead-letter queues"
        actions={
          queuesQuery.data && (
            <span className="mono text-xs" style={{ color: "var(--subtle)" }}>
              refreshing every 5s
            </span>
          )
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
    </div>
  );
}
