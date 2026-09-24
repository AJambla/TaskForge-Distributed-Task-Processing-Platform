import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";
import type { Task, TaskCreateRequest } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import Modal from "../../components/ui/Modal";
import Field, { Spinner, EmptyState } from "../../components/ui/Field";
import StatusPill from "../../components/ui/StatusPill";
import { Button } from "../../components/ui/Button";
import { Ban, Mail, RotateCcw, Image as ImageIcon, Webhook, Plus } from "lucide-react";

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

  const onTypeChange = (type: TaskCreateRequest["task_type"]) => {
    setFormData({
      task_type: type,
      payload:
        type === "email_send"
          ? { to: "", subject: "", body: "" }
          : type === "image_resize"
            ? { url: "", width: 800, height: 600 }
            : { url: "", headers: {}, body: {} },
    });
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Tasks"
        subtitle="Manage and monitor your task queue"
        actions={
          <Button variant="nav" size="sm" withIcon onClick={() => setShowModal(true)}>
            New Task
          </Button>
        }
      />

      <div className="flex items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="field__input !h-10 !w-auto min-w-[180px]"
          aria-label="Filter by status"
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
        <span className="text-sm" style={{ color: "var(--subtle)" }}>
          {data ? `${data.pagination.total} total` : "…"}
        </span>
      </div>

      <Panel bodyClassName="overflow-x-auto" delay={0.08}>
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner size={26} />
          </div>
        ) : !data?.data?.length ? (
          <EmptyState
            icon={<Ban size={22} />}
            title="No tasks found"
            hint="Submit a task or adjust the status filter."
          />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Created</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.data.map((task) => (
                <tr
                  key={task.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/app/tasks/${task.id}`)}
                >
                  <td className="font-medium" style={{ color: "var(--text)" }}>
                    {taskTypeLabels[task.task_type] || task.task_type}
                  </td>
                  <td>
                    <StatusPill status={task.status} />
                  </td>
                  <td className="mono text-xs">
                    {task.attempt_count} / {task.max_attempts}
                  </td>
                  <td style={{ color: "var(--subtle)" }}>
                    {new Date(task.created_at).toLocaleString()}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1">
                      {(task.status === "failed" || task.status === "dead_letter") && (
                        <button
                          onClick={() => retryMutation.mutate(task.id)}
                          className="icon-btn"
                          title="Retry"
                          aria-label="Retry task"
                        >
                          <RotateCcw size={14} />
                        </button>
                      )}
                      {(task.status === "queued" || task.status === "retrying") && (
                        <button
                          onClick={() => cancelMutation.mutate(task.id)}
                          className="icon-btn icon-btn--danger"
                          title="Cancel"
                          aria-label="Cancel task"
                        >
                          <Ban size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {totalPages > 1 && (
          <div
            className="flex items-center justify-between px-6 py-4"
            style={{ borderTop: "1px solid var(--line)" }}
          >
            <p className="text-sm" style={{ color: "var(--subtle)" }}>
              Page {page} of {totalPages}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="quiet"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                ← Previous
              </Button>
              <Button
                variant="quiet"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                Next →
              </Button>
            </div>
          </div>
        )}
      </Panel>

      {showModal && (
        <Modal
          title="Submit New Task"
          subtitle="Queue a job for your worker pool"
          onClose={() => setShowModal(false)}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="Task Type">
              <select
                value={formData.task_type}
                onChange={(e) => onTypeChange(e.target.value as TaskCreateRequest["task_type"])}
                className="field__input"
              >
                <option value="email_send">Email Send</option>
                <option value="image_resize">Image Resize</option>
                <option value="webhook_delivery">Webhook Delivery</option>
              </select>
            </Field>

            {formData.task_type === "email_send" && (
              <>
                <Field label="To">
                  <input
                    type="email"
                    value={(formData.payload.to as string) || ""}
                    onChange={(e) =>
                      setFormData({ ...formData, payload: { ...formData.payload, to: e.target.value } })
                    }
                    className="field__input"
                    placeholder="recipient@example.com"
                    required
                  />
                </Field>
                <Field label="Subject">
                  <input
                    type="text"
                    value={(formData.payload.subject as string) || ""}
                    onChange={(e) =>
                      setFormData({ ...formData, payload: { ...formData.payload, subject: e.target.value } })
                    }
                    className="field__input"
                    placeholder="Email subject"
                    required
                  />
                </Field>
                <Field label="Body">
                  <textarea
                    value={(formData.payload.body as string) || ""}
                    onChange={(e) =>
                      setFormData({ ...formData, payload: { ...formData.payload, body: e.target.value } })
                    }
                    rows={4}
                    className="field__input"
                    placeholder="Email body content"
                    required
                  />
                </Field>
              </>
            )}

            {formData.task_type === "image_resize" && (
              <>
                <Field label="Image URL">
                  <input
                    type="url"
                    value={(formData.payload.url as string) || ""}
                    onChange={(e) =>
                      setFormData({ ...formData, payload: { ...formData.payload, url: e.target.value } })
                    }
                    className="field__input"
                    placeholder="https://example.com/image.jpg"
                    required
                  />
                </Field>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Width">
                    <input
                      type="number"
                      value={(formData.payload.width as number) || 800}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: { ...formData.payload, width: Number(e.target.value) },
                        })
                      }
                      className="field__input"
                      min={1}
                      required
                    />
                  </Field>
                  <Field label="Height">
                    <input
                      type="number"
                      value={(formData.payload.height as number) || 600}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          payload: { ...formData.payload, height: Number(e.target.value) },
                        })
                      }
                      className="field__input"
                      min={1}
                      required
                    />
                  </Field>
                </div>
              </>
            )}

            {formData.task_type === "webhook_delivery" && (
              <>
                <Field label="Webhook URL">
                  <input
                    type="url"
                    value={(formData.payload.url as string) || ""}
                    onChange={(e) =>
                      setFormData({ ...formData, payload: { ...formData.payload, url: e.target.value } })
                    }
                    className="field__input"
                    placeholder="https://example.com/webhook"
                    required
                  />
                </Field>
                <Field label="Body (JSON)">
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
                    className="field__input mono text-xs"
                  />
                </Field>
              </>
            )}

            <div className="flex items-center justify-end gap-3 pt-4">
              <Button variant="quiet" type="button" onClick={() => setShowModal(false)}>
                Cancel
              </Button>
              <Button variant="nav" size="sm" type="submit" disabled={createMutation.isPending} withIcon>
                {createMutation.isPending ? (
                  <>
                    <Spinner size={14} /> Submitting…
                  </>
                ) : (
                  <>Submit Task</>
                )}
              </Button>
            </div>
          </form>
        </Modal>
      )}

      <div className="flex items-center gap-6 pb-2" style={{ color: "var(--subtle)" }}>
        <span className="inline-flex items-center gap-1.5 text-xs">
          <Mail size={13} /> email_send
        </span>
        <span className="inline-flex items-center gap-1.5 text-xs">
          <ImageIcon size={13} /> image_resize
        </span>
        <span className="inline-flex items-center gap-1.5 text-xs">
          <Webhook size={13} /> webhook_delivery
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-xs">
          <Plus size={13} /> {totalPages > 1 ? `${totalPages} pages` : "single page"}
        </span>
      </div>
    </div>
  );
}
