import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  KeyRound,
  Layers,
  LayoutDashboard,
  ListChecks,
  Search,
  Server,
  Settings,
} from "lucide-react";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { Task, TaskListResponse, Worker } from "../types";
import StatusPill from "./ui/StatusPill";
import { shortId } from "../lib/format";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

interface Result {
  key: string;
  group: string;
  label: string;
  hint?: string;
  to: string;
  icon?: React.ReactNode;
  pill?: React.ReactNode;
}

const PAGES: Array<{ label: string; to: string; icon: React.ReactNode; admin?: boolean }> = [
  { label: "Overview", to: "/app/overview", icon: <LayoutDashboard size={15} /> },
  { label: "Tasks", to: "/app/tasks", icon: <ListChecks size={15} /> },
  { label: "Queues", to: "/app/queues", icon: <Layers size={15} /> },
  { label: "Workers", to: "/app/workers", icon: <Server size={15} /> },
  { label: "Metrics", to: "/app/metrics", icon: <BarChart3 size={15} />, admin: true },
  { label: "API Keys", to: "/app/api-keys", icon: <KeyRound size={15} /> },
  { label: "Activity", to: "/app/activity", icon: <Activity size={15} /> },
  { label: "Settings", to: "/app/settings", icon: <Settings size={15} /> },
];

export default function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const q = query.trim().toLowerCase();

  const tasksQuery = useQuery({
    queryKey: ["tasks", "palette"],
    queryFn: async () => {
      const res = await client.get<TaskListResponse>("/tasks", {
        params: { page: 1, page_size: 50, sort: "-created_at" },
      });
      return res.data.data;
    },
    enabled: open,
    staleTime: 30_000,
  });

  const workersQuery = useQuery({
    queryKey: ["workers", "palette"],
    queryFn: async () => {
      const res = await client.get<Worker[]>("/workers");
      return res.data;
    },
    enabled: open && isAdmin,
    staleTime: 30_000,
  });

  const results = useMemo<Result[]>(() => {
    const out: Result[] = [];
    const pages = PAGES.filter((p) => !p.admin || isAdmin);
    pages
      .filter((p) => !q || p.label.toLowerCase().includes(q))
      .forEach((p) =>
        out.push({ key: `page-${p.to}`, group: "Navigate", label: p.label, to: p.to, icon: p.icon })
      );

    if (q) {
      const tasks = (tasksQuery.data ?? []).filter(
        (t: Task) =>
          t.id.toLowerCase().includes(q) ||
          t.task_type.toLowerCase().includes(q) ||
          t.status.replace(/_/g, " ").includes(q)
      );
      tasks.slice(0, 6).forEach((t) =>
        out.push({
          key: `task-${t.id}`,
          group: "Tasks",
          label: shortId(t.id),
          hint: t.task_type.replace(/_/g, " "),
          to: `/app/tasks/${t.id}`,
          pill: <StatusPill status={t.status} />,
        })
      );

      const workers = (workersQuery.data ?? []).filter(
        (w: Worker) =>
          w.hostname.toLowerCase().includes(q) || w.id.toLowerCase().includes(q)
      );
      workers.slice(0, 4).forEach((w) =>
        out.push({
          key: `worker-${w.id}`,
          group: "Workers",
          label: w.hostname,
          hint: w.status,
          to: `/app/workers/${w.id}`,
        })
      );
    }
    return out;
  }, [q, isAdmin, tasksQuery.data, workersQuery.data]);

  useEffect(() => {
    setActive(0);
  }, [q]);

  useEffect(() => {
    if (open) {
      setQuery("");
      const t = setTimeout(() => inputRef.current?.focus(), 20);
      return () => clearTimeout(t);
    }
  }, [open]);

  if (!open) return null;

  const go = (to: string) => {
    onClose();
    navigate(to);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const hit = results[active];
      if (hit) go(hit.to);
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  let lastGroup = "";

  return (
    <div
      className="palette-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKeyDown}>
        <div className="palette__input-row">
          <Search size={16} style={{ color: "var(--subtle)", flexShrink: 0 }} />
          <input
            ref={inputRef}
            className="palette__input"
            placeholder="Search pages, tasks, workers…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search"
          />
          <kbd className="palette__kbd">esc</kbd>
        </div>
        <div className="palette__results">
          {results.length === 0 && (
            <p className="palette__empty">
              {q ? "No matches." : "Type to search pages, task IDs or workers."}
            </p>
          )}
          {results.map((r, i) => {
            const showGroup = r.group !== lastGroup;
            lastGroup = r.group;
            return (
              <div key={r.key}>
                {showGroup && <p className="palette__group">{r.group}</p>}
                <button
                  type="button"
                  className={`palette__item ${i === active ? "is-active" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(r.to)}
                >
                  {r.icon && <span className="palette__icon">{r.icon}</span>}
                  <span className="palette__label">{r.label}</span>
                  {r.hint && <span className="palette__hint">{r.hint}</span>}
                  {r.pill}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
