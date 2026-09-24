import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  CircleDollarSign,
  Clock,
  FileText,
  KeyRound,
  ListChecks,
  Mail,
  Plus,
  Server,
  Timer,
  TrendingUp,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  bucketTasksByHour,
  useQueueStats,
  useRecentTasks,
  useWorkers,
} from "../../api/queries";
import Panel from "../../components/ui/Panel";
import StatCard from "../../components/ui/StatCard";
import StatusPill from "../../components/ui/StatusPill";
import { AreaLine, Donut, DonutLegend, STATUS_COLORS } from "../../components/ui/Charts";
import { formatNumber, formatSeconds, relativeTime, shortId } from "../../lib/format";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Overview() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";

  const { data: tasks } = useRecentTasks(100);
  const statsQuery = useQueueStats(isAdmin);
  const workersQuery = useWorkers(isAdmin);

  const derived = useMemo(() => {
    const list = tasks ?? [];
    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);
    const today = list.filter((t) => new Date(t.created_at) >= startOfDay).length;
    const finished = list.filter((t) =>
      ["succeeded", "failed", "dead_letter"].includes(t.status)
    );
    const succeeded = list.filter((t) => t.status === "succeeded").length;
    const successRate = finished.length ? (succeeded / finished.length) * 100 : null;
    const queued = list.filter((t) => t.status === "queued" || t.status === "retrying").length;
    const running = list.filter((t) => t.status === "running").length;
    const durations = list
      .filter((t) => t.started_at && t.completed_at)
      .map((t) => (new Date(t.completed_at!).getTime() - new Date(t.started_at!).getTime()) / 1000);
    const avgExec = durations.length
      ? durations.reduce((a, b) => a + b, 0) / durations.length
      : null;
    return { today, successRate, queued, running, avgExec, succeeded };
  }, [tasks]);

  const throughput = useMemo(
    () => bucketTasksByHour(tasks ?? [], 12),
    [tasks]
  );

  const donutSegments = useMemo(() => {
    const counts = isAdmin && statsQuery.data ? statsQuery.data.status_counts : null;
    const source: Record<string, number> = counts ?? {};
    if (counts) {
      return Object.entries(source)
        .filter(([, v]) => v > 0)
        .map(([label, value]) => ({
          label,
          value,
          color: STATUS_COLORS[label] ?? "var(--subtle)",
        }));
    }
    const byStatus: Record<string, number> = {};
    for (const t of tasks ?? []) byStatus[t.status] = (byStatus[t.status] ?? 0) + 1;
    return Object.entries(byStatus).map(([label, value]) => ({
      label,
      value,
      color: STATUS_COLORS[label] ?? "var(--subtle)",
    }));
  }, [isAdmin, statsQuery.data, tasks]);

  const stats = statsQuery.data;
  const onlineWorkers = workersQuery.data?.filter((w) => w.status === "online").length ?? 0;
  const totalWorkers = workersQuery.data?.length ?? 0;
  const systemOk = !isAdmin || onlineWorkers > 0;

  const recent = (tasks ?? []).slice(0, 7);

  return (
    <div className="space-y-6">
      {/* ---------- greeting banner ---------- */}
      <section className="ov-banner rise" style={{ "--d": "0.02s" } as React.CSSProperties}>
        <div className="ov-banner__main">
          <h1 className="ov-banner__title">
            {greeting()}, {user?.email ? user.email.split("@")[0] : "there"}
          </h1>
          <p className="ov-banner__sub">
            {isAdmin
              ? "Your distributed task execution platform is running smoothly."
              : "Here's what's happening across your tasks."}
          </p>
          <div className="ov-banner__actions">
            <Link to="/app/tasks" className="btn btn--light btn--sm">
              <span className="btn__label inline-flex items-center gap-2">
                <Plus size={14} /> Submit Task
              </span>
            </Link>
            <Link to="/app/api-keys" className="btn btn--ghost-dark btn--sm">
              <span className="btn__label inline-flex items-center gap-2">
                <KeyRound size={14} /> Create API Key
              </span>
            </Link>
            <Link to="/app/activity" className="btn btn--ghost-dark btn--sm">
              <span className="btn__label inline-flex items-center gap-2">
                <FileText size={14} /> View Activity
              </span>
            </Link>
          </div>
        </div>
        <div className="ov-banner__status">
          <p className="ov-banner__status-title">
            <span className={`pulse-dot ${systemOk ? "is-ok" : "is-warn"}`} />
            {systemOk ? "System operational" : "No workers online"}
          </p>
          {isAdmin ? (
            <ul className="ov-banner__status-list">
              <li>
                <span className="mono">{onlineWorkers} / {totalWorkers}</span> workers online
              </li>
              <li>
                <span className="mono">{formatNumber(derived.queued)}</span> queued / retrying
              </li>
              {stats && (
                <li>
                  <span className="mono">{stats.throughput.tasks_completed_per_minute_5m.toFixed(1)}</span>{" "}
                  done / min (5m)
                </li>
              )}
            </ul>
          ) : (
            <ul className="ov-banner__status-list">
              <li>
                <span className="mono">{formatNumber(derived.running)}</span> running now
              </li>
              <li>
                <span className="mono">{formatNumber(derived.queued)}</span> queued
              </li>
            </ul>
          )}
        </div>
      </section>

      {/* ---------- stat cards ---------- */}
      <div className="ov-stats">
        <StatCard
          label="Tasks today"
          value={formatNumber(derived.today)}
          icon={<ListChecks size={14} />}
          sub={`of ${formatNumber((tasks ?? []).length)} recent`}
          delay={0.06}
        />
        <StatCard
          label="Success rate"
          value={derived.successRate == null ? "—" : `${derived.successRate.toFixed(1)}%`}
          icon={<CheckCircle2 size={14} />}
          accent="#067647"
          sub={`${formatNumber(derived.succeeded)} succeeded recently`}
          delay={0.12}
        />
        <StatCard
          label="Queued"
          value={formatNumber(derived.queued)}
          icon={<Clock size={14} />}
          accent="#d97706"
          sub={`${formatNumber(derived.running)} running`}
          delay={0.18}
        />
        <StatCard
          label="Avg execution"
          value={
            isAdmin && stats?.latency.avg_execution_seconds != null
              ? formatSeconds(stats.latency.avg_execution_seconds)
              : derived.avgExec != null
                ? formatSeconds(derived.avgExec)
                : "—"
          }
          icon={<Timer size={14} />}
          accent="#6d28d9"
          sub={isAdmin && stats?.latency.avg_pickup_seconds != null
            ? `${formatSeconds(stats.latency.avg_pickup_seconds)} avg pickup`
            : "from recent tasks"}
          delay={0.24}
        />
        {isAdmin && (
          <StatCard
            label="Active workers"
            value={`${onlineWorkers}`}
            unit={`/ ${totalWorkers}`}
            icon={<Server size={14} />}
            accent="#006cd2"
            right={
              <Link to="/app/workers" className="ov-stats__link">
                manage
              </Link>
            }
            delay={0.3}
          />
        )}
      </div>

      {/* ---------- charts row ---------- */}
      <div className="ov-grid-2">
        <Panel
          title="Task throughput"
          subtitle="Tasks created per hour · last 12h"
          actions={
            <TrendingUp size={16} style={{ color: "var(--subtle)" }} aria-hidden />
          }
          delay={0.1}
          bodyClassName="px-5 py-5"
        >
          <AreaLine points={throughput.points} labels={throughput.labels} />
        </Panel>

        <Panel
          title="Status distribution"
          subtitle={isAdmin ? "All tasks (platform-wide)" : "Your recent tasks"}
          delay={0.16}
        >
          {donutSegments.length === 0 ? (
            <p className="ov-empty">No tasks recorded yet.</p>
          ) : (
            <div className="flex flex-wrap items-center gap-6">
              <Donut
                segments={donutSegments}
                centerValue={formatNumber(
                  donutSegments.reduce((s, x) => s + x.value, 0)
                )}
                centerLabel="total"
              />
              <div className="min-w-[180px] flex-1">
                <DonutLegend segments={donutSegments} />
              </div>
            </div>
          )}
        </Panel>
      </div>

      {/* ---------- activity + quick actions ---------- */}
      <div className="ov-grid-2">
        <Panel
          title="Recent tasks"
          subtitle="Latest activity across queues"
          actions={
            <Link to="/app/tasks" className="ov-stats__link">
              View all
            </Link>
          }
          delay={0.2}
          bodyClassName="ov-recent"
        >
          {recent.length === 0 && <p className="ov-empty">Nothing yet — submit your first task.</p>}
          {recent.map((t) => (
            <button
              key={t.id}
              className="ov-recent__row"
              onClick={() => navigate(`/app/tasks/${t.id}`)}
            >
              <span className="mono ov-recent__id">{shortId(t.id)}</span>
              <span className="ov-recent__type">{t.task_type.replace(/_/g, " ")}</span>
              <StatusPill status={t.status} />
              <span className="mono ov-recent__time">{relativeTime(t.created_at)}</span>
              <ArrowRight size={14} className="ov-recent__arrow" />
            </button>
          ))}
        </Panel>

        <div className="space-y-6">
          <Panel title="Quick actions" delay={0.26}>
            <div className="ov-quick">
              <Link to="/app/tasks" className="ov-quick__item">
                <Plus size={16} />
                <span>
                  <strong>Submit task</strong>
                  <em>Queue an email, resize or webhook</em>
                </span>
              </Link>
              <Link to="/app/api-keys" className="ov-quick__item">
                <KeyRound size={16} />
                <span>
                  <strong>Create API key</strong>
                  <em>Authenticate your services</em>
                </span>
              </Link>
              {isAdmin ? (
                <Link to="/app/metrics" className="ov-quick__item">
                  <CircleDollarSign size={16} />
                  <span>
                    <strong>Explore metrics</strong>
                    <em>Throughput, latency and queues</em>
                  </span>
                </Link>
              ) : (
                <Link to="/app/activity" className="ov-quick__item">
                  <Mail size={16} />
                  <span>
                    <strong>Activity log</strong>
                    <em>Trace your task lifecycle</em>
                  </span>
                </Link>
              )}
            </div>
          </Panel>

          {stats && (
            <Panel
              title="Pipeline health"
              subtitle={`Snapshot · updated ${relativeTime(stats.generated_at)}`}
              delay={0.32}
            >
              <div className="ov-health">
                <div>
                  <p className="ov-health__label">Completed / min (5m)</p>
                  <p className="ov-health__value mono">
                    {stats.throughput.tasks_completed_per_minute_5m.toFixed(1)}
                  </p>
                </div>
                <div>
                  <p className="ov-health__label">Avg pickup delay</p>
                  <p className="ov-health__value mono">
                    {formatSeconds(stats.latency.avg_pickup_seconds)}
                  </p>
                </div>
                <div>
                  <p className="ov-health__label">Avg execution</p>
                  <p className="ov-health__value mono">
                    {formatSeconds(stats.latency.avg_execution_seconds)}
                  </p>
                </div>
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
