import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import client from "../../api/client";
import type { Worker } from "../../types";
import { Loader2, Server, CheckCircle2, CircleOff, AlertTriangle } from "lucide-react";

const statusStyles: Record<string, string> = {
  online: "bg-green-500/10 text-green-400 border-green-500/20",
  offline: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  draining: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
};

const statusIcons: Record<string, import("react").JSX.Element> = {
  online: <CheckCircle2 size={14} />,
  offline: <CircleOff size={14} />,
  draining: <AlertTriangle size={14} />,
};

function relativeTime(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

export default function Workers() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["workers"],
    queryFn: async () => {
      const response = await client.get("/workers");
      return response.data as Worker[];
    },
    refetchInterval: 5000,
  });

  const isForbidden =
    (error as { response?: { status?: number } })?.response?.status === 403;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Workers</h1>
        <p className="text-slate-400 mt-1">
          Live worker pool status, refreshed every 5 seconds
        </p>
      </div>

      {isForbidden ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-10 text-center text-slate-400">
          <Server size={32} className="mx-auto mb-3 text-slate-600" />
          <p>Worker visibility is restricted to admins.</p>
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={32} className="text-indigo-500 animate-spin" />
        </div>
      ) : !data?.length ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl py-16 text-center text-slate-400">
          <p>No workers have registered yet</p>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800 text-left">
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Hostname
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Load
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Processed
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Failed
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Last Heartbeat
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((worker) => (
                  <tr
                    key={worker.id}
                    className="border-b border-slate-800/50 hover:bg-slate-800/30"
                  >
                    <td className="px-6 py-4">
                      <Link
                        to={`/workers/${worker.id}`}
                        className="text-sm font-medium text-indigo-400 hover:text-indigo-300"
                      >
                        {worker.hostname}
                      </Link>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${
                          statusStyles[worker.status] ??
                          "bg-slate-500/10 text-slate-400 border-slate-500/20"
                        }`}
                      >
                        {statusIcons[worker.status]}
                        {worker.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 rounded-full"
                            style={{
                              width: `${Math.min(
                                100,
                                worker.concurrency_limit > 0
                                  ? (worker.current_task_count /
                                      worker.concurrency_limit) *
                                      100
                                  : 0
                              )}%`,
                            }}
                          />
                        </div>
                        <span className="text-xs text-slate-400">
                          {worker.current_task_count}/{worker.concurrency_limit}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">
                      {worker.tasks_processed}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">
                      {worker.tasks_failed}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-400">
                      {relativeTime(worker.last_heartbeat_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
