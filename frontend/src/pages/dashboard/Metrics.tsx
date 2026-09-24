import { useQuery } from "@tanstack/react-query";
import client from "../../api/client";
import type { QueueMetrics } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { PageLoading } from "../../components/ui/Field";
import { Gauge, Timer, Layers, Archive } from "lucide-react";

interface Stats {
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

const STATUS_ORDER = [
  "queued",
  "running",
  "retrying",
  "succeeded",
  "failed",
  "dead_letter",
  "cancelled",
];

const STATUS_COLOR: Record<string, string> = {
  queued: "var(--brand)",
  running: "#b45309",
  retrying: "#c2410c",
  succeeded: "#067647",
  failed: "#b91c1c",
  dead_letter: "#6d28d9",
  cancelled: "var(--subtle)",
};

function formatSeconds(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return value >= 60 ? `${(value / 60).toFixed(1)}m` : `${value.toFixed(2)}s`;
}

export default function Metrics() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["queue-stats"],
    queryFn: async () => {
      const response = await client.get("/queues/stats");
      return response.data as Stats;
    },
    refetchInterval: 5000,
  });

  const { data: queues, isLoading: queuesLoading } = useQuery({
    queryKey: ["queue-depths"],
    queryFn: async () => {
      const response = await client.get("/queues");
      return (response.data as { queues: QueueMetrics[] }).queues;
    },
    refetchInterval: 5000,
  });

  const isLoading = statsLoading || queuesLoading;

  if (isLoading) return <PageLoading />;

  const topCards = [
    {
      icon: <Gauge size={14} />,
      label: "Throughput (5m)",
      value: stats?.throughput.tasks_completed_per_minute_5m ?? 0,
      unit: "tasks/min",
    },
    {
      icon: <Gauge size={14} />,
      label: "Throughput (1h)",
      value: stats?.throughput.tasks_completed_per_minute_60m ?? 0,
      unit: "tasks/min",
    },
    {
      icon: <Timer size={14} />,
      label: "Avg Pickup",
      value: formatSeconds(stats?.latency.avg_pickup_seconds ?? null),
      unit: "",
    },
    {
      icon: <Timer size={14} />,
      label: "Avg Execution",
      value: formatSeconds(stats?.latency.avg_execution_seconds ?? null),
      unit: "",
    },
  ];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Queue Metrics"
        subtitle={
          <span className="inline-flex items-center gap-2">
            <span className="chip-dot" style={{ color: "var(--brand)" }} aria-hidden />
            System throughput, latency and queue depth, refreshed every 5 seconds
          </span>
        }
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {topCards.map((c, i) => (
          <div
            key={c.label}
            className="stat rise"
            style={{ "--d": `${0.1 + i * 0.06}s` } as React.CSSProperties}
          >
            <p className="stat__label">
              {c.icon} {c.label}
            </p>
            <p className="stat__value">
              {c.value}
              {c.unit && <span className="stat__unit">{c.unit}</span>}
            </p>
          </div>
        ))}
      </div>

      <Panel
        title={
          <span className="inline-flex items-center gap-2">
            <Layers size={14} style={{ color: "var(--subtle)" }} /> Tasks by Status
          </span>
        }
        delay={0.2}
      >
        <div className="grid grid-cols-2 gap-x-4 gap-y-6 md:grid-cols-4 lg:grid-cols-7">
          {STATUS_ORDER.map((status) => (
            <div key={status} style={{ borderLeft: `2px solid ${STATUS_COLOR[status]}`, paddingLeft: 12 }}>
              <p className="section-label" style={{ color: STATUS_COLOR[status], textTransform: "none", letterSpacing: 0 }}>
                {status.replace(/_/g, " ")}
              </p>
              <p className="stat__value" style={{ marginTop: 4 }}>
                {stats?.status_counts[status] ?? 0}
              </p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title={
          <span className="inline-flex items-center gap-2">
            <Archive size={14} style={{ color: "var(--subtle)" }} /> Queue Depths by Task Type
          </span>
        }
        delay={0.26}
        bodyClassName="overflow-x-auto"
      >
        {!queues?.length ? (
          <p className="py-10 text-center text-sm" style={{ color: "var(--subtle)" }}>
            No queues reported yet
          </p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Task Type</th>
                <th>Main</th>
                <th>Retry</th>
                <th>Dead Letter</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {queues.map((row) => (
                <tr key={row.task_type}>
                  <td className="font-medium" style={{ color: "var(--text)" }}>
                    {row.task_type}
                  </td>
                  <td className="mono text-sm">{row.main_depth}</td>
                  <td className="mono text-sm">{row.retry_depth}</td>
                  <td className="mono text-sm" style={{ color: "#6d28d9" }}>
                    {row.dlq_depth}
                  </td>
                  <td className="mono text-sm font-semibold" style={{ color: "var(--text)" }}>
                    {row.total_depth}
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
