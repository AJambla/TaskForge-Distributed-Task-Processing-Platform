import { useQuery } from "@tanstack/react-query";
import client from "../../api/client";
import type { QueueMetrics } from "../../types";
import { Loader2, Gauge, Layers, Timer, Archive } from "lucide-react";

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

const statusColors: Record<string, string> = {
  queued: "text-blue-400",
  running: "text-yellow-400",
  retrying: "text-orange-400",
  succeeded: "text-green-400",
  failed: "text-red-400",
  dead_letter: "text-purple-400",
  cancelled: "text-slate-400",
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={32} className="text-indigo-500 animate-spin" />
      </div>
    );
  }

  const totalByType = (row: QueueMetrics) => row.total_depth;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Queue Metrics</h1>
        <p className="text-slate-400 mt-1">
          System throughput, latency and queue depth, refreshed every 5 seconds
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wider">
            <Gauge size={14} /> Throughput (5m)
          </div>
          <p className="text-2xl font-semibold text-slate-100 mt-2">
            {stats?.throughput.tasks_completed_per_minute_5m ?? 0}
            <span className="text-sm text-slate-400 ml-1">tasks/min</span>
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wider">
            <Gauge size={14} /> Throughput (1h)
          </div>
          <p className="text-2xl font-semibold text-slate-100 mt-2">
            {stats?.throughput.tasks_completed_per_minute_60m ?? 0}
            <span className="text-sm text-slate-400 ml-1">tasks/min</span>
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wider">
            <Timer size={14} /> Avg Pickup
          </div>
          <p className="text-2xl font-semibold text-slate-100 mt-2">
            {formatSeconds(stats?.latency.avg_pickup_seconds ?? null)}
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wider">
            <Timer size={14} /> Avg Execution
          </div>
          <p className="text-2xl font-semibold text-slate-100 mt-2">
            {formatSeconds(stats?.latency.avg_execution_seconds ?? null)}
          </p>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wider mb-3">
          <Layers size={14} /> Tasks by Status
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {STATUS_ORDER.map((status) => (
            <div key={status}>
              <p
                className={`text-xs font-medium ${statusColors[status] ?? "text-slate-400"}`}
              >
                {status}
              </p>
              <p className="text-xl font-semibold text-slate-100">
                {stats?.status_counts[status] ?? 0}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wider">
          <Archive size={14} /> Queue Depths by Task Type
        </div>
        {!queues?.length ? (
          <p className="text-slate-400 text-center py-10">
            No queues reported yet
          </p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800 text-left">
                <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                  Task Type
                </th>
                <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                  Main
                </th>
                <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                  Retry
                </th>
                <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                  Dead Letter
                </th>
                <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {queues.map((row) => (
                <tr
                  key={row.task_type}
                  className="border-b border-slate-800/50 hover:bg-slate-800/30"
                >
                  <td className="px-6 py-3 text-sm font-medium text-slate-200">
                    {row.task_type}
                  </td>
                  <td className="px-6 py-3 text-sm text-slate-300">
                    {row.main_depth}
                  </td>
                  <td className="px-6 py-3 text-sm text-slate-300">
                    {row.retry_depth}
                  </td>
                  <td className="px-6 py-3 text-sm text-purple-400">
                    {row.dlq_depth}
                  </td>
                  <td className="px-6 py-3 text-sm text-slate-100 font-medium">
                    {totalByType(row)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
