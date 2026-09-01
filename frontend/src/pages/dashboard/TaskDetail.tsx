import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import client from "../../api/client";
import type { Task, TaskAttempt } from "../../types";
import { ArrowLeft, Clock, Calendar, RefreshCw, XCircle, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { useState } from "react";

const statusColors: Record<string, string> = {
  queued: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  running: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  succeeded: "bg-green-500/10 text-green-400 border-green-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
  retrying: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  dead_letter: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  cancelled: "bg-slate-500/10 text-slate-400 border-slate-500/20",
};

const attemptOutcomes: Record<string, import("react").JSX.Element> = {
  success: <CheckCircle2 size={14} className="text-green-400" />,
  failure: <XCircle size={14} className="text-red-400" />,
  timeout: <AlertCircle size={14} className="text-yellow-400" />,
};

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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={32} className="text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="text-center py-20 text-slate-400">
        <p>Task not found</p>
        <button
          onClick={() => navigate("/tasks")}
          className="mt-4 text-indigo-400 hover:text-indigo-300"
        >
          Back to tasks
        </button>
      </div>
    );
  }

  const attempts = task.attempts || [];

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate("/tasks")}
        className="flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors"
      >
        <ArrowLeft size={16} />
        Back to tasks
      </button>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">
            {task.task_type.replace("_", " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </h1>
          <p className="text-slate-400 mt-1 font-mono text-sm">{task.id}</p>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border ${
            statusColors[task.status] || "bg-slate-500/10 text-slate-400 border-slate-500/20"
          }`}
        >
          {task.status}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
            <Clock size={14} />
            Created
          </div>
          <p className="text-slate-100 font-medium">
            {new Date(task.created_at).toLocaleString()}
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
            <Calendar size={14} />
            Started
          </div>
          <p className="text-slate-100 font-medium">
            {task.started_at ? new Date(task.started_at).toLocaleString() : "—"}
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
            <RefreshCw size={14} />
            Attempts
          </div>
          <p className="text-slate-100 font-medium">
            {task.attempt_count} / {task.max_attempts}
          </p>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Payload</h2>
        <pre className="bg-slate-950 border border-slate-800 rounded-lg p-4 text-sm text-slate-300 font-mono overflow-x-auto">
          {JSON.stringify(task.payload, null, 2)}
        </pre>
      </div>

      {attempts.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-800">
            <h2 className="text-lg font-semibold text-slate-100">Attempt History</h2>
          </div>
          <div className="divide-y divide-slate-800">
            {attempts.map((attempt) => (
              <div key={attempt.id} className="px-6 py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-slate-300">
                      Attempt {attempt.attempt_number}
                    </span>
                    {attempt.outcome && attemptOutcomes[attempt.outcome]}
                    <span className={`text-sm ${attempt.outcome === "success" ? "text-green-400" : attempt.outcome === "failure" ? "text-red-400" : "text-yellow-400"}`}>
                      {attempt.outcome || "pending"}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500">
                    {new Date(attempt.started_at).toLocaleString()}
                  </span>
                </div>
                {attempt.error_message && (
                  <button
                    onClick={() =>
                      setShowError(showError === attempts.indexOf(attempt) ? null : attempts.indexOf(attempt))
                    }
                    className="mt-2 text-xs text-red-400 hover:text-red-300"
                  >
                    {showError === attempts.indexOf(attempt) ? "Hide" : "Show"} error details
                  </button>
                )}
                {showError === attempts.indexOf(attempt) && attempt.error_detail && (
                  <pre className="mt-2 bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-red-300 font-mono overflow-x-auto">
                    {JSON.stringify(attempt.error_detail, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
