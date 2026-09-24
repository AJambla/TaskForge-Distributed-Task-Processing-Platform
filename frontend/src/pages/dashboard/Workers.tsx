import { Link } from "react-router-dom";
import { CheckCircle2, Cpu, Server, Zap } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import StatCard from "../../components/ui/StatCard";
import { PageLoading, EmptyState } from "../../components/ui/Field";
import StatusPill from "../../components/ui/StatusPill";
import { useWorkers } from "../../api/queries";
import { relativeTime } from "../../lib/format";
import type { Worker } from "../../types";

function LoadBar({ current, limit }: { current: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, (current / limit) * 100) : 0;
  return (
    <div className="wk-load">
      <span className="wk-load__track">
        <span
          className="wk-load__fill"
          style={{
            width: `${pct}%`,
            background: pct >= 90 ? "#b91c1c" : "var(--brand)",
          }}
        />
      </span>
      <span className="mono wk-load__text">
        {current}/{limit}
      </span>
    </div>
  );
}

function heartbeatTone(iso: string): "fresh" | "stale" | "dead" {
  const age = (Date.now() - new Date(iso).getTime()) / 1000;
  if (age < 60) return "fresh";
  if (age < 180) return "stale";
  return "dead";
}

function WorkerCard({ worker, delay }: { worker: Worker; delay: number }) {
  const total = worker.tasks_processed + worker.tasks_failed;
  const rate = total > 0 ? ((worker.tasks_processed / total) * 100).toFixed(1) : null;
  const tone = heartbeatTone(worker.last_heartbeat_at);

  return (
    <div className="wk-card rise" style={{ "--d": `${delay}s` } as React.CSSProperties}>
      <div className="wk-card__head">
        <Link to={`/app/workers/${worker.id}`} className="wk-card__name navlink">
          {worker.hostname}
        </Link>
        <StatusPill status={worker.status} />
      </div>
      <LoadBar current={worker.current_task_count} limit={worker.concurrency_limit} />
      <div className="wk-card__grid">
        <div>
          <p className="wk-card__label">Processed</p>
          <p className="wk-card__value mono">{worker.tasks_processed.toLocaleString()}</p>
        </div>
        <div>
          <p className="wk-card__label">Failed</p>
          <p
            className="wk-card__value mono"
            style={{ color: worker.tasks_failed > 0 ? "#b91c1c" : undefined }}
          >
            {worker.tasks_failed.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="wk-card__label">Success</p>
          <p className="wk-card__value mono">{rate ? `${rate}%` : "—"}</p>
        </div>
      </div>
      <p className="wk-card__beat">
        <span className={`wk-dot is-${tone}`} aria-hidden />
        heartbeat {relativeTime(worker.last_heartbeat_at)}
      </p>
    </div>
  );
}

export default function Workers() {
  const { data, isLoading } = useWorkers();

  const online = data?.filter((w) => w.status === "online").length ?? 0;
  const capacity = data?.reduce((s, w) => s + w.concurrency_limit, 0) ?? 0;
  const busy = data?.reduce((s, w) => s + w.current_task_count, 0) ?? 0;
  const processed = data?.reduce((s, w) => s + w.tasks_processed, 0) ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workers"
        subtitle={
          <span className="inline-flex items-center gap-2">
            <span className="chip-dot" style={{ color: "var(--brand)" }} aria-hidden />
            Live worker pool health, refreshed every 5 seconds
          </span>
        }
      />

      {isLoading ? (
        <PageLoading />
      ) : !data?.length ? (
        <Panel delay={0.08}>
          <EmptyState
            icon={<Server size={22} />}
            title="No workers have registered yet"
            hint="Start a worker process and it will appear here within seconds."
          />
        </Panel>
      ) : (
        <>
          <div className="ov-stats">
            <StatCard
              label="Online"
              value={`${online} / ${data.length}`}
              icon={<CheckCircle2 size={14} />}
              accent="#067647"
              delay={0.05}
            />
            <StatCard
              label="Capacity in use"
              value={`${busy} / ${capacity}`}
              icon={<Zap size={14} />}
              sub="concurrent slots occupied"
              delay={0.1}
            />
            <StatCard
              label="Tasks processed"
              value={processed.toLocaleString()}
              icon={<Cpu size={14} />}
              sub="lifetime across pool"
              accent="#6d28d9"
              delay={0.15}
            />
          </div>

          <div className="wk-grid">
            {data.map((w, i) => (
              <WorkerCard key={w.id} worker={w} delay={0.2 + i * 0.05} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
