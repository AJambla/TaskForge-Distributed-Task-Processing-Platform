import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";
import type { Task, TaskCreateRequest } from "../../types";
import {
  Plus,
  RefreshCw,
  Loader2,
  Filter,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Trash2,
  RotateCw,
  Ban,
} from "lucide-react";

const statusColors: Record<string, string> = {
  queued: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  running: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  succeeded: "bg-green-500/10 text-green-400 border-green-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
  retrying: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  dead_letter: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  cancelled: "bg-slate-500/10 text-slate-400 border-slate-500/20",
};

const statusIcons: Record<string, import("react").JSX.Element> = {
  queued: <Clock size={14} />,
  running: <RefreshCw size={14} className="animate-spin" />,
  succeeded: <CheckCircle2 size={14} />,
  failed: <XCircle size={14} />,
  retrying: <AlertCircle size={14} />,
  dead_letter: <Trash2 size={14} />,
  cancelled: <Ban size={14} />,
};

const taskTypeLabels: Record<string, string> = {
  email_send: "Email Send",
  image_resize: "Image Resize",
  webhook_delivery: "Webhook Delivery",
};

export default function Tasks() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState<TaskCreateRequest>({
    task_type: "email_send",
    payload: { to: "", subject: "", body: "" },
  });

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", page, statusFilter],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: "20",
      });
      if (statusFilter) params.append("status", statusFilter);
      const response = await client.get(`/tasks?${params}`);
      return response.data as { data: Task[]; pagination: { total: number } };
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (taskId: string) => {
      await client.post(`/tasks/${taskId}/cancel`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: async (taskId: string) => {
      await client.post(`/tasks/${taskId}/retry`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const createMutation = useMutation({
    mutationFn: async (data: TaskCreateRequest) => {
      const response = await client.post("/tasks", data);
      return response.data as Task;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setShowModal(false);
      setFormData({ task_type: "email_send", payload: { to: "", subject: "", body: "" } });
    },
  });

  const totalPages = data ? Math.ceil(data.pagination.total / 20) : 1;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(formData);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Tasks</h1>
          <p className="text-slate-400 mt-1">Manage and monitor your task queue</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-2 px-4 rounded-lg transition-colors"
        >
          <Plus size={16} />
          New Task
        </button>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Filter size={14} />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Status</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
            <option value="retrying">Retrying</option>
            <option value="dead_letter">Dead Letter</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={32} className="text-indigo-500 animate-spin" />
          </div>
        ) : !data?.data?.length ? (
          <div className="text-center py-16 text-slate-400">
            <p>No tasks found</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-800 text-left">
                    <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                      Type
                    </th>
                    <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                      Attempts
                    </th>
                    <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {data.data.map((task) => (
                    <tr
                      key={task.id}
                      onClick={() => navigate(`/tasks/${task.id}`)}
                      className="hover:bg-slate-800/50 cursor-pointer transition-colors"
                    >
                      <td className="px-6 py-4">
                        <span className="text-sm font-medium text-slate-200">
                          {taskTypeLabels[task.task_type] || task.task_type}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                            statusColors[task.status] || "bg-slate-500/10 text-slate-400 border-slate-500/20"
                          }`}
                        >
                          {statusIcons[task.status] || <Clock size={14} />}
                          {task.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {task.attempt_count} / {task.max_attempts}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {new Date(task.created_at).toLocaleDateString()}
                      </td>
                      <td
                        onClick={(e) => e.stopPropagation()}
                        className="px-6 py-4 text-right flex items-center justify-end gap-2"
                      >
                        {(task.status === "failed" || task.status === "dead_letter") && (
                          <button
                            onClick={() => retryMutation.mutate(task.id)}
                            className="p-1.5 text-slate-400 hover:text-indigo-400 hover:bg-slate-800 rounded-lg transition-colors"
                            title="Retry"
                          >
                            <RotateCw size={14} />
                          </button>
                        )}
                        {(task.status === "queued" || task.status === "retrying") && (
                          <button
                            onClick={() => cancelMutation.mutate(task.id)}
                            className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-800 rounded-lg transition-colors"
                            title="Cancel"
                          >
                            <Ban size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800">
                <p className="text-sm text-slate-400">
                  Page {page} of {totalPages}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-slate-100">Submit New Task</h2>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <XCircle size={20} />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Task Type
                </label>
                <select
                  value={formData.task_type}
                  onChange={(e) => {
                    const type = e.target.value as TaskCreateRequest["task_type"];
                    setFormData({
                      ...formData,
                      task_type: type,
                      payload:
                        type === "email_send"
                          ? { to: "", subject: "", body: "" }
                          : type === "image_resize"
                          ? { url: "", width: 800, height: 600 }
                          : { url: "", headers: {}, body: {} },
                    });
                  }}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="email_send">Email Send</option>
                  <option value="image_resize">Image Resize</option>
                  <option value="webhook_delivery">Webhook Delivery</option>
                </select>
              </div>

              {formData.task_type === "email_send" && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">
                      To
                    </label>
                    <input
                      type="email"
                      value={(formData.payload.to as string) || ""}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: { ...formData.payload, to: e.target.value },
                        })
                      }
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="recipient@example.com"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">
                      Subject
                    </label>
                    <input
                      type="text"
                      value={(formData.payload.subject as string) || ""}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: { ...formData.payload, subject: e.target.value },
                        })
                      }
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="Email subject"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">
                      Body
                    </label>
                    <textarea
                      value={(formData.payload.body as string) || ""}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: { ...formData.payload, body: e.target.value },
                        })
                      }
                      rows={4}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                      placeholder="Email body content"
                      required
                    />
                  </div>
                </>
              )}

              {formData.task_type === "image_resize" && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">
                      Image URL
                    </label>
                    <input
                      type="url"
                      value={(formData.payload.url as string) || ""}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: { ...formData.payload, url: e.target.value },
                        })
                      }
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="https://example.com/image.jpg"
                      required
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1.5">
                        Width
                      </label>
                      <input
                        type="number"
                        value={(formData.payload.width as number) || 800}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            payload: { ...formData.payload, width: Number(e.target.value) },
                          })
                        }
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        min={1}
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1.5">
                        Height
                      </label>
                      <input
                        type="number"
                        value={(formData.payload.height as number) || 600}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            payload: { ...formData.payload, height: Number(e.target.value) },
                          })
                        }
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        min={1}
                        required
                      />
                    </div>
                  </div>
                </>
              )}

              {formData.task_type === "webhook_delivery" && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">
                      Webhook URL
                    </label>
                    <input
                      type="url"
                      value={(formData.payload.url as string) || ""}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: { ...formData.payload, url: e.target.value },
                        })
                      }
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="https://example.com/webhook"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">
                      Body (JSON)
                    </label>
                    <textarea
                      value={JSON.stringify(formData.payload.body || {}, null, 2)}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: {
                            ...formData.payload,
                            body: (() => {
                              try {
                                return JSON.parse(e.target.value);
                              } catch {
                                return {};
                              }
                            })(),
                          },
                        })
                      }
                      rows={4}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                    />
                  </div>
                </>
              )}

              <div className="flex items-center justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-medium py-2 px-4 rounded-lg transition-colors"
                >
                  {createMutation.isPending ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    <>
                      <Plus size={16} />
                      Submit Task
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
