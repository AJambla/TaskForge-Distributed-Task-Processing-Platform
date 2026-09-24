import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import client from "../../api/client";
import type { WorkerDetail } from "../../types";
import { Loader2, ArrowLeft } from "lucide-react";

const outcomeStyles: Record<string, string> = {
  success: "text-green-400",
  failure: "text-red-400",
  timeout: "text-orange-400",
};

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
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-10 text-center text-slate-400">
        <p>Worker visibility is restricted to admins.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={32} className="text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-10 text-center text-slate-400">
        <p>Worker not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/workers"
          className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-slate-100 mb-3"
        >
          <ArrowLeft size={14} />
          Back to workers
        </Link>
        <h1 className="text-2xl font-semibold text-slate-100">
          {data.hostname}
        </h1>
        <p className="text-slate-400 mt-1 text-sm">
          {data.status} · registered {new Date(data.registered_at).toLocaleString()}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Status", value: data.status },
          {
            label: "Load",
            value: `${data.current_task_count}/${data.concurrency_limit}`,
          },
          { label: "Tasks Processed", value: String(data.tasks_processed) },
          { label: "Tasks Failed", value: String(data.tasks_failed) },
        ].map((stat) => (
          <div
            key={stat.label}
            className="bg-slate-900 border border-slate-800 rounded-xl p-4"
          >
            <p className="text-xs text-slate-400 uppercase tracking-wider">
              {stat.label}
            </p>
            <p className="text-xl font-semibold text-slate-100 mt-1">
              {stat.value}
            </p>
          </div>
        ))}
      </div>

      <div>
        <h2 className="text-lg font-semibold text-slate-100 mb-3">
          Recent Attempts
        </h2>
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          {!data.recent_attempts.length ? (
            <p className="text-slate-400 text-center py-10">
              No attempts recorded for this worker
            </p>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800 text-left">
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                    Task
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                    Attempt
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                    Outcome
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                    Started
                  </th>
                  <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase">
                    Error
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.recent_attempts.map((attempt) => (
                  <tr
                    key={attempt.id}
                    className="border-b border-slate-800/50 hover:bg-slate-800/30"
                  >
                    <td className="px-6 py-3 text-sm">
                      <Link
                        to={`/tasks/${attempt.task_id}`}
                        className="text-indigo-400 hover:text-indigo-300"
                      >
                        {attempt.task_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-6 py-3 text-sm text-slate-300">
                      #{attempt.attempt_number}
                    </td>
                    <td
                      className={`px-6 py-3 text-sm font-medium ${
                        outcomeStyles[attempt.outcome ?? ""] ?? "text-slate-400"
                      }`}
                    >
                      {attempt.outcome ?? "running"}
                    </td>
                    <td className="px-6 py-3 text-sm text-slate-400">
                      {new Date(attempt.started_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-3 text-sm text-red-400/80 max-w-xs truncate">
                      {attempt.error_message ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
