import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, Check, Clock, X } from "lucide-react";
import client from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import StatusPill from "../../components/ui/StatusPill";
import { EmptyState } from "../../components/ui/Field";
import { relativeTime, shortId } from "../../lib/format";
import type { Task, TaskListResponse } from "../../types";

interface Event {
  key: string;
  task: Task;
  kind: "created" | "started" | "completed";
  at: string;
}

const KIND_META: Record<
  Event["kind"],
  { label: string; icon: React.ReactNode; color: string }
> = {
  created: { label: "queued", icon: <Clock size={13} />, color: "var(--brand)" },
  started: { label: "started", icon: <ArrowUp size={13} />, color: "#d97706" },
  completed: { label: "finished", icon: <Check size={13} />, color: "#067647" },
};

const STATUS_FILTERS = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "retrying",
  "dead_letter",
  "cancelled",
];

export default function Activity() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";
  const [allUsers, setAllUsers] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", "activity", allUsers],
    queryFn: async () => {
      const res = await client.get<TaskListResponse>("/tasks", {
        params: {
          page: 1,
          page_size: 100,
          sort: "-created_at",
          ...(allUsers && isAdmin ? { all_tasks: true } : {}),
        },
      });
      return res.data.data;
    },
    refetchInterval: 15_000,
  });

  const events = useMemo<Event[]>(() => {
    const out: Event[] = [];
    for (const t of data ?? []) {
      out.push({ key: `${t.id}-c`, task: t, kind: "created", at: t.created_at });
      if (t.started_at) out.push({ key: `${t.id}-s`, task: t, kind: "started", at: t.started_at });
      if (t.completed_at)
        out.push({
          key: `${t.id}-f`,
          task: t,
          kind: "completed",
          at: t.completed_at,
        });
    }
    const filtered = statusFilter
      ? out.filter((e) => e.task.status === statusFilter)
      : out;
    return filtered.sort((a, b) => (a.at < b.at ? 1 : -1));
  }, [data, statusFilter]);

  const groups = useMemo(() => {
    const map = new Map<string, Event[]>();
    for (const e of events) {
      const d = new Date(e.at);
      const label = d.toDateString() === new Date().toDateString()
        ? "Today"
        : d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
      const arr = map.get(label) ?? [];
      arr.push(e);
      map.set(label, arr);
    }
    return [...map.entries()];
  }, [events]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Activity"
        subtitle="Task lifecycle events derived from queue activity"
        actions={
          isAdmin && (
            <label className="ov-toggle">
              <input
                type="checkbox"
                checked={allUsers}
                onChange={(e) => setAllUsers(e.target.checked)}
              />
              All users
            </label>
          )
        }
      />

      <div className="act-filters">
        <button
          className={`chip ${!statusFilter ? "is-active" : ""}`}
          onClick={() => setStatusFilter(null)}
        >
          all
        </button>
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            className={`chip chip--${s} ${statusFilter === s ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === s ? null : s)}
          >
            {s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {isLoading && <Panel delay={0.05}><EmptyState title="Loading activity…" /></Panel>}

      {!isLoading && groups.length === 0 && (
        <Panel delay={0.05}>
          <EmptyState
            title="No activity yet"
            hint="Submit a task and its lifecycle will appear here."
          />
        </Panel>
      )}

      {groups.map(([label, list], gi) => (
        <section key={label} className="act-group">
          <h2 className="act-group__label">{label}</h2>
          <Panel delay={0.05 + gi * 0.06} bodyClassName="act-list">
            {list.map((e) => {
              const meta =
                e.kind === "completed" &&
                ["failed", "dead_letter", "cancelled"].includes(e.task.status)
                  ? { ...KIND_META.completed, icon: <X size={13} />, color: "#b91c1c" }
                  : KIND_META[e.kind];
              return (
                <button
                  key={e.key}
                  className="act-row"
                  onClick={() => navigate(`/app/tasks/${e.task.id}`)}
                >
                  <span className="act-row__icon" style={{ color: meta.color }}>
                    {meta.icon}
                  </span>
                  <span className="act-row__text">
                    Task <span className="mono act-row__id">{shortId(e.task.id)}</span>{" "}
                    {e.kind === "created" && "queued"}
                    {e.kind === "started" && "picked up by a worker"}
                    {e.kind === "completed" && (
                      <>
                        finished <StatusPill status={e.task.status} />
                      </>
                    )}
                    <em>{e.task.task_type.replace(/_/g, " ")}</em>
                  </span>
                  <span className="mono act-row__time">{relativeTime(e.at)}</span>
                </button>
              );
            })}
          </Panel>
        </section>
      ))}
    </div>
  );
}
