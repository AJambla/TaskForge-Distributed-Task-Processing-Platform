import { useMemo } from "react";
import { AlertOctagon, Gauge, Layers, Timer, TrendingUp } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import StatCard from "../../components/ui/StatCard";
import { PageLoading, EmptyState } from "../../components/ui/Field";
import { BarRow, Donut, DonutLegend, STATUS_COLORS } from "../../components/ui/Charts";
import { useQueueStats, useQueues } from "../../api/queries";
import { formatSeconds, relativeTime } from "../../lib/format";

const STATUS_ORDER = [
  "queued",
  "running",
  "retrying",
  "succeeded",
  "failed",
  "dead_letter",
  "cancelled",
];

const isForbidden = (error: unknown) =>
  (error as { response?: { status?: number } })?.response?.status === 403;

export default function Metrics() {
  const statsQuery = useQueueStats(true);
  const queuesQuery = useQueues(true);

  const forbidden = isForbidden(statsQuery.error) || isForbidden(queuesQuery.error);
  const stats = statsQuery.data;
  const queues = queuesQuery.data ?? [];

  const segments = useMemo(() => {
    const counts = stats?.status_counts ?? {};
    return STATUS_ORDER.filter((s) => (counts[s] ?? 0) > 0).map((s) => ({
      label: s,
      value: counts[s],
      color: STATUS_COLORS[s] ?? "var(--subtle)",
    }));
  }, [stats]);

  const totalTasks = segments.reduce((s, x) => s + x.value, 0);
  const maxDepth = Math.max(1, ...queues.map((q) => Math.max(q.main_depth, q.retry_depth, q.dlq_depth)));

  if (statsQuery.isLoading || queuesQuery.isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Metrics" subtitle="Live platform snapshot" />
        {forbidden ? (
          <Panel delay={0.05}>
            <EmptyState
              icon={<Gauge size={22} />}
              title="Metrics are restricted to admins."
              hint="Queue statistics require an admin account."
            />
          </Panel>
        ) : (
          <PageLoading />
        )}
      </div>
    );
  }

  if (forbidden) {
    return (
      <div className="space-y-6">
        <PageHeader title="Metrics" subtitle="Live platform snapshot" />
        <Panel delay={0.05}>
          <EmptyState
            icon={<Gauge size={22} />}
            title="Metrics are restricted to admins."
            hint="Queue statistics require an admin account."
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Metrics"
        subtitle={
          <span className="inline-flex items-center gap-2">
            <span className="chip-dot" style={{ color: "var(--brand)" }} aria-hidden />
            Throughput, latency and queue depth · snapshot {stats ? relativeTime(stats.generated_at) : "—"}
          </span>
        }
      />

      <div className="ov-stats">
        <StatCard
          label="Throughput (5m)"
          value={(stats?.throughput.tasks_completed_per_minute_5m ?? 0).toFixed(1)}
          unit="tasks/min"
          icon={<TrendingUp size={14} />}
          accent="#067647"
          delay={0.05}
        />
        <StatCard
          label="Throughput (1h)"
          value={(stats?.throughput.tasks_completed_per_minute_60m ?? 0).toFixed(1)}
          unit="tasks/min"
          icon={<Gauge size={14} />}
          delay={0.1}
        />
        <StatCard
          label="Avg pickup delay"
          value={formatSeconds(stats?.latency.avg_pickup_seconds ?? null)}
          icon={<Timer size={14} />}
          accent="#d97706"
          sub="queue → worker"
          delay={0.15}
        />
        <StatCard
          label="Avg execution"
          value={formatSeconds(stats?.latency.avg_execution_seconds ?? null)}
          icon={<Timer size={14} />}
          accent="#6d28d9"
          sub="worker run time"
          delay={0.2}
        />
      </div>

      <div className="ov-grid-2">
        <Panel
          title="Tasks by status"
          subtitle="All-time counts across the platform"
          delay={0.22}
        >
          {segments.length === 0 ? (
            <p className="ov-empty">No tasks recorded yet.</p>
          ) : (
            <div className="flex flex-wrap items-center gap-6">
              <Donut
                segments={segments}
                centerValue={totalTasks.toLocaleString()}
                centerLabel="tasks"
              />
              <div className="min-w-[200px] flex-1">
                <DonutLegend segments={segments} />
              </div>
            </div>
          )}
        </Panel>

        <Panel
          title="Queue depths"
          subtitle="Messages waiting in RabbitMQ"
          actions={<Layers size={16} style={{ color: "var(--subtle)" }} aria-hidden />}
          delay={0.28}
        >
          {queues.length === 0 ? (
            <p className="ov-empty">No queues reported yet.</p>
          ) : (
            <div className="space-y-5">
              {queues.map((q) => (
                <div key={q.task_type}>
                  <p className="mets-queue__title">{q.task_type.replace(/_/g, " ")}</p>
                  <div className="mt-2 space-y-2">
                    <BarRow label="Main" value={q.main_depth} max={maxDepth} />
                    <BarRow label="Retry" value={q.retry_depth} max={maxDepth} color="#d97706" />
                    <BarRow label="DLQ" value={q.dlq_depth} max={maxDepth} color="#6d28d9" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {totalTasks > 0 && (
        <p className="flex items-center gap-2 text-xs" style={{ color: "var(--subtle)" }}>
          <AlertOctagon size={13} />
          Status counts are lifetime totals; queue depths are live broker readings.
        </p>
      )}
    </div>
  );
}
