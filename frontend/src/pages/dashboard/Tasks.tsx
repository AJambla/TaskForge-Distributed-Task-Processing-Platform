import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "../../api/client";
import type { Task, TaskCreateRequest, TaskListResponse } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import Modal from "../../components/ui/Modal";
import Field, { Spinner, EmptyState } from "../../components/ui/Field";
import StatusPill from "../../components/ui/StatusPill";
import TaskDrawer from "../../components/TaskDrawer";
import { Button } from "../../components/ui/Button";
import {
  Ban,
  Mail,
  RotateCcw,
  Image as ImageIcon,
  Webhook,
} from "lucide-react";
import { durationBetween, relativeTime, shortId } from "../../lib/format";

const taskTypeLabels: Record<string, string> = {
  email_send: "Email Send",
  image_resize: "Image Resize",
  webhook_delivery: "Webhook Delivery",
};

const TYPE_ICONS: Record<string, React.ReactNode> = {
  email_send: <Mail size={14} />,
  image_resize: <ImageIcon size={14} />,
  webhook_delivery: <Webhook size={14} />,
};

const STATUSES = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "retrying",
  "dead_letter",
  "cancelled",
];

const SORTS: Array<{ value: string; label: string }> = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "-started_at", label: "Latest started" },
  { value: "-completed_at", label: "Latest completed" },
  { value: "status", label: "Status" },
  { value: "priority", label: "Priority" },
];

const emptyForm = (): TaskCreateRequest => ({
  task_type: "email_send",
  payload: { to: "", subject: "", body: "" },
});

export default function Tasks() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sort, setSort] = useState("-created_at");
  const [drawerTaskId, setDrawerTaskId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState<TaskCreateRequest>(emptyForm);

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", page, statusFilter, typeFilter, sort],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: "20",
        sort,
      });
      if (statusFilter) params.append("status", statusFilter);
      if (typeFilter) params.append("task_type", typeFilter);
      const response = await client.get<TaskListResponse>(`/tasks?${params}`);
      return response.data;
    },
    refetchInterval: 10_000,
  });

  const cancelMutation = useMutation({
    mutationFn: async (taskId: string) => {
      await client.post(`/tasks/${taskId}/cancel`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });

  const retryMutation = useMutation({
    mutationFn: async (taskId: string) => {
      await client.post(`/tasks/${taskId}/retry`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });

  const createMutation = useMutation({
    mutationFn: async (payload: TaskCreateRequest) => {
      const response = await client.post("/tasks", payload);
      return response.data as Task;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setShowModal(false);
      setFormData(emptyForm());
      setPage(1);
    },
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.pagination.total / 20)) : 1;

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
            ? { source_url: "", width: 800, height: 600 }
            : { url: "", headers: {}, body: {} },
    });
  };

  const setPayloadField = (key: string, value: unknown) =>
    setFormData((f) => ({ ...f, payload: { ...f.payload, [key]: value } }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tasks"
        subtitle="Manage and monitor your task queue"
        actions={
          <Button variant="nav" size="sm" withIcon onClick={() => setShowModal(true)}>
            New Task
          </Button>
        }
      />

      <div className="tsk-filters">
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="field__input !h-10 tsk-filters__select"
          aria-label="Filter by status"
        >
          <option value="">All status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(1);
          }}
          className="field__input !h-10 tsk-filters__select"
          aria-label="Filter by type"
        >
          <option value="">All types</option>
          {Object.keys(taskTypeLabels).map((t) => (
            <option key={t} value={t}>
              {taskTypeLabels[t]}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setPage(1);
          }}
          className="field__input !h-10 tsk-filters__select"
          aria-label="Sort tasks"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <span className="tsk-filters__count mono">
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
            hint="Submit a task or adjust the filters."
          />
        ) : (
          <table className="tbl tbl--clickable">
            <thead>
              <tr>
                <th>Task</th>
                <th>Type</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Priority</th>
                <th>Duration</th>
                <th>Created</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.data.map((task) => (
                <tr key={task.id} onClick={() => setDrawerTaskId(task.id)}>
                  <td>
                    <span className="mono tsk-id">{shortId(task.id)}</span>
                  </td>
                  <td>
                    <span className="tsk-type">
                      {TYPE_ICONS[task.task_type] ?? null}
                      {taskTypeLabels[task.task_type] || task.task_type}
                    </span>
                  </td>
                  <td>
                    <StatusPill status={task.status} />
                  </td>
                  <td className="mono text-xs">
                    {task.attempt_count} / {task.max_attempts}
                  </td>
                  <td className="mono text-xs">
                    {task.priority > 0 ? `+${task.priority}` : task.priority}
                  </td>
                  <td className="mono text-xs">
                    {task.started_at ? (
                      task.completed_at ? (
                        durationBetween(task.started_at, task.completed_at)
                      ) : (
                        <span className="tsk-running">{durationBetween(task.started_at, null)}</span>
                      )
                    ) : (
                      "—"
                    )}
                  </td>
                  <td title={new Date(task.created_at).toLocaleString()}>
                    {relativeTime(task.created_at)}
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
                    onChange={(e) => setPayloadField("to", e.target.value)}
                    className="field__input"
                    placeholder="recipient@example.com"
                    required
                  />
                </Field>
                <Field label="Subject">
                  <input
                    type="text"
                    value={(formData.payload.subject as string) || ""}
                    onChange={(e) => setPayloadField("subject", e.target.value)}
                    className="field__input"
                    placeholder="Email subject"
                    required
                  />
                </Field>
                <Field label="Body">
                  <textarea
                    value={(formData.payload.body as string) || ""}
                    onChange={(e) => setPayloadField("body", e.target.value)}
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
                    value={(formData.payload.source_url as string) || ""}
                    onChange={(e) => setPayloadField("source_url", e.target.value)}
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
                      onChange={(e) => setPayloadField("width", Number(e.target.value))}
                      className="field__input"
                      min={1}
                      required
                    />
                  </Field>
                  <Field label="Height">
                    <input
                      type="number"
                      value={(formData.payload.height as number) || 600}
                      onChange={(e) => setPayloadField("height", Number(e.target.value))}
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
                    onChange={(e) => setPayloadField("url", e.target.value)}
                    className="field__input"
                    placeholder="https://example.com/webhook"
                    required
                  />
                </Field>
                <Field label="Body (JSON)">
                  <textarea
                    defaultValue={JSON.stringify(formData.payload.body || {}, null, 2)}
                    onChange={(e) => {
                      try {
                        setPayloadField("body", JSON.parse(e.target.value));
                      } catch {
                        /* keep last valid body until JSON parses */
                      }
                    }}
                    rows={4}
                    className="field__input mono text-xs"
                  />
                </Field>
              </>
            )}

            <div className="grid grid-cols-2 gap-4">
              <Field label="Priority" hint="-100 … 100, higher runs first">
                <input
                  type="number"
                  value={formData.priority ?? 0}
                  onChange={(e) =>
                    setFormData((f) => ({ ...f, priority: Number(e.target.value) }))
                  }
                  className="field__input"
                  min={-100}
                  max={100}
                />
              </Field>
              <Field label="Max attempts">
                <input
                  type="number"
                  value={formData.max_attempts ?? 5}
                  onChange={(e) =>
                    setFormData((f) => ({ ...f, max_attempts: Number(e.target.value) }))
                  }
                  className="field__input"
                  min={1}
                  max={20}
                />
              </Field>
            </div>

            {createMutation.error && (
              <p className="text-xs" style={{ color: "#b91c1c" }}>
                {(
                  createMutation.error as { response?: { data?: { error?: { message?: string } } } }
                )?.response?.data?.error?.message ?? "Failed to submit task."}
              </p>
            )}

            <div className="flex items-center justify-end gap-3 pt-4">
              <Button variant="quiet" type="button" onClick={() => setShowModal(false)}>
                Cancel
              </Button>
              <Button
                variant="nav"
                size="sm"
                type="submit"
                disabled={createMutation.isPending}
                withIcon
              >
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

      <TaskDrawer taskId={drawerTaskId} onClose={() => setDrawerTaskId(null)} />
    </div>
  );
}
