import {
  AlertOctagon,
  CheckCircle2,
  ExternalLink,
  Gauge,
  Layers,
  RefreshCw,
  ShieldCheck,
  Timer,
  TrendingUp,
} from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import StatCard from "../../components/ui/StatCard";
import { PageLoading, EmptyState } from "../../components/ui/Field";
import { AreaLine, BarRow } from "../../components/ui/Charts";
import { useMetricsSummary } from "../../api/queries";
import { relativeTime } from "../../lib/format";

const isForbidden = (error: unknown) =>
  (error as { response?: { status?: number } })?.response?.status === 403;

export default function Metrics() {
  const { data: summary, isLoading, error } = useMetricsSummary(true);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Metrics" subtitle="Live platform telemetry snapshot" />
        <PageLoading />
      </div>
    );
  }

  if (error || !summary) {
    const forbidden = isForbidden(error);
    return (
      <div className="space-y-6">
        <PageHeader title="Metrics" subtitle="Live platform telemetry snapshot" />
        <Panel delay={0.05}>
          <EmptyState
            icon={<Gauge size={22} />}
            title={forbidden ? "Metrics are restricted." : "Unable to load operational metrics."}
            hint={forbidden ? "Operational telemetry requires an authenticated account." : "Please ensure the TaskForge backend service is reachable."}
          />
        </Panel>
      </div>
    );
  }

  const {
    reliability,
    throughput,
    workers,
    latency,
    backpressure,
    queues,
    links,
  } = summary;

  // Determine top-level health status
  const isSaturated = backpressure.status === "SATURATED";
  const isThrottled = backpressure.status === "THROTTLED";
  const hasUnhealthyWorkers = workers.unhealthy > 0;

  let healthStatusLabel = "HEALTHY";
  let healthDotColor = "#067647";
  let healthBadgeClass = "bg-[#067647]/10 text-[#067647] border border-[#067647]/30";

  if (isSaturated || workers.healthy === 0) {
    healthStatusLabel = "DEGRADED";
    healthDotColor = "#b91c1c";
    healthBadgeClass = "bg-[#b91c1c]/10 text-[#b91c1c] border border-[#b91c1c]/30";
  } else if (isThrottled || hasUnhealthyWorkers) {
    healthStatusLabel = "ATTENTION";
    healthDotColor = "#d97706";
    healthBadgeClass = "bg-[#d97706]/10 text-[#d97706] border border-[#d97706]/30";
  }

  const bpBadgeClass =
    backpressure.status === "SATURATED"
      ? "bg-[#b91c1c]/10 text-[#b91c1c] border border-[#b91c1c]/30"
      : backpressure.status === "THROTTLED"
      ? "bg-[#d97706]/10 text-[#d97706] border border-[#d97706]/30"
      : "bg-[#067647]/10 text-[#067647] border border-[#067647]/30";

  return (
    <div className="space-y-6">
      {/* 1. Header with Platform Health and Config-driven Observability Links */}
      <PageHeader
        title="Operational Metrics"
        subtitle={
          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider rounded-sm ${healthBadgeClass}`}
            >
              <span
                className="w-2 h-2 rounded-full animate-pulse"
                style={{ background: healthDotColor }}
                aria-hidden
              />
              TASKFORGE · {healthStatusLabel}
            </span>
            <span className="text-xs text-[var(--subtle)]">
              {workers.active} Workers · {workers.running_tasks} Running · {queues.main} Queued · {reliability.success_rate_percent}% Success
            </span>
            <span className="text-xs text-[var(--subtle)]">
              · snapshot {relativeTime(summary.timestamp)}
            </span>
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            {links?.grafana && (
              <a
                href={links.grafana}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-[var(--text)] bg-[var(--app-bg)] hover:bg-[var(--line-soft)] border border-[var(--line)] transition-colors rounded-sm"
                title="Open Grafana Dashboards"
              >
                <span>Grafana</span>
                <ExternalLink size={12} />
              </a>
            )}
            {links?.jaeger && (
              <a
                href={links.jaeger}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-[var(--text)] bg-[var(--app-bg)] hover:bg-[var(--line-soft)] border border-[var(--line)] transition-colors rounded-sm"
                title="Open Jaeger Distributed Tracing"
              >
                <span>Jaeger</span>
                <ExternalLink size={12} />
              </a>
            )}
            {links?.prometheus && (
              <a
                href={links.prometheus}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-[var(--text)] bg-[var(--app-bg)] hover:bg-[var(--line-soft)] border border-[var(--line)] transition-colors rounded-sm"
                title="Open Prometheus Time-Series Metrics"
              >
                <span>Prometheus</span>
                <ExternalLink size={12} />
              </a>
            )}
          </div>
        }
      />

      {/* 2. Visual Centerpiece: Reliability Invariant Ledger */}
      <Panel
        title={
          <span className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-[#067647]" />
            <span>Reliability Invariant Ledger</span>
          </span>
        }
        subtitle="TaskForge zero-data-loss architecture and fault recovery guarantees"
        delay={0.05}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="p-4 border border-[#067647]/30 bg-[#067647]/5 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold tracking-wider uppercase text-[#067647]">
                Tasks Lost
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] font-bold text-[#067647] bg-[#067647]/15 px-2 py-0.5 rounded-sm">
                <CheckCircle2 size={12} /> GUARANTEED INVARIANT
              </span>
            </div>
            <div className="text-4xl font-extrabold text-[#067647] my-2 font-mono">
              {reliability.tasks_lost}
            </div>
            <p className="text-xs text-[var(--subtle)]">
              Zero tasks dropped across worker crashes, broker partitions, or node restarts via Transactional Outbox.
            </p>
          </div>

          <div className="p-4 border border-[#067647]/30 bg-[#067647]/5 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold tracking-wider uppercase text-[#067647]">
                Duplicate Executions
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] font-bold text-[#067647] bg-[#067647]/15 px-2 py-0.5 rounded-sm">
                <CheckCircle2 size={12} /> GUARANTEED INVARIANT
              </span>
            </div>
            <div className="text-4xl font-extrabold text-[#067647] my-2 font-mono">
              {reliability.duplicate_executions}
            </div>
            <p className="text-xs text-[var(--subtle)]">
              Atomic distributed locking and idempotency ledger guarantee strict exactly-once execution semantics.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Tasks Recovered"
            value={reliability.tasks_recovered}
            icon={<RefreshCw size={14} />}
            accent="#006cd2"
            sub="reclaimed from dead workers"
          />
          <StatCard
            label="Automated Retries"
            value={reliability.retries}
            icon={<TrendingUp size={14} />}
            accent="#d97706"
            sub="exponential jitter backoff"
          />
          <StatCard
            label="Dead-Letter Queue"
            value={reliability.dlq_tasks}
            icon={<AlertOctagon size={14} />}
            accent="#6d28d9"
            sub="quarantined tasks"
          />
          <StatCard
            label="Success Rate"
            value={`${reliability.success_rate_percent}%`}
            icon={<CheckCircle2 size={14} />}
            accent="#067647"
            sub="completed tasks"
          />
        </div>
      </Panel>

      {/* 3. Throughput & Workload Dynamics */}
      <Panel
        title={
          <span className="flex items-center gap-2">
            <TrendingUp size={18} className="text-[var(--brand)]" />
            <span>Throughput & Workload Dynamics</span>
          </span>
        }
        subtitle="Real-time submission and completion processing velocity"
        delay={0.1}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <StatCard
            label="Submissions"
            value={`${throughput.submissions_per_min["5m"]} / min`}
            sub={`1h avg: ${throughput.submissions_per_min["60m"]} / min`}
            icon={<TrendingUp size={14} />}
            accent="#006cd2"
          />
          <StatCard
            label="Completions"
            value={`${throughput.completions_per_min["5m"]} / min`}
            sub={`1h avg: ${throughput.completions_per_min["60m"]} / min`}
            icon={<CheckCircle2 size={14} />}
            accent="#067647"
          />
          <StatCard
            label="Total Submitted"
            value={throughput.total_submitted.toLocaleString()}
            sub="lifetime platform workload"
            icon={<Layers size={14} />}
          />
        </div>

        {throughput.history_points && throughput.history_points.length > 1 && (
          <div className="mt-4 pt-4 border-t border-[var(--line)]">
            <div className="flex items-center justify-between text-xs text-[var(--subtle)] mb-2">
              <span className="font-semibold uppercase tracking-wider">
                Workload Activity Trend (Recent Intervals)
              </span>
              <span>Tasks submitted / interval</span>
            </div>
            <AreaLine
              points={throughput.history_points}
              labels={throughput.history_labels}
              height={140}
              color="var(--brand)"
            />
          </div>
        )}
      </Panel>

      {/* 4. Execution Latency & SLA Percentiles */}
      <Panel
        title={
          <span className="flex items-center gap-2">
            <Timer size={18} className="text-[#d97706]" />
            <span>Execution Latency & SLA Distribution</span>
          </span>
        }
        subtitle="Task processing duration percentiles and broker pickup wait times"
        delay={0.15}
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Queue Pickup Delay"
            value={
              latency.pickup_seconds.avg != null
                ? `${(latency.pickup_seconds.avg * 1000).toFixed(0)} ms`
                : "—"
            }
            icon={<Timer size={14} />}
            accent="#d97706"
            sub="queue → worker claim"
          />
          <StatCard
            label="P50 Latency"
            value={
              latency.execution_seconds.p50 != null
                ? `${latency.execution_seconds.p50}s`
                : "—"
            }
            icon={<Gauge size={14} />}
            accent="#067647"
            sub="median execution duration"
          />
          <StatCard
            label="P95 Latency"
            value={
              latency.execution_seconds.p95 != null
                ? `${latency.execution_seconds.p95}s`
                : "—"
            }
            icon={<Gauge size={14} />}
            accent="#006cd2"
            sub="95th percentile SLA"
          />
          <StatCard
            label="P99 Latency"
            value={
              latency.execution_seconds.p99 != null
                ? `${latency.execution_seconds.p99}s`
                : "—"
            }
            icon={<Gauge size={14} />}
            accent="#6d28d9"
            sub="tail latency threshold"
          />
        </div>
      </Panel>

      {/* 5. Backpressure and Worker Fleet Lifecycle (Two Columns) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Panel
          title="Backpressure & Fleet Capacity"
          subtitle="Worker slot saturation and rate-limit shedding"
          delay={0.2}
        >
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider font-semibold text-[var(--subtle)]">
                Backpressure Status
              </span>
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-bold rounded-sm ${bpBadgeClass}`}
              >
                ● {backpressure.status}
              </span>
            </div>

            <div>
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-[var(--subtle)]">Fleet Concurrency Utilization</span>
                <span className="font-mono font-bold">{backpressure.utilization_percent}%</span>
              </div>
              <div className="w-full h-3 bg-[var(--line-soft)] rounded-sm overflow-hidden">
                <div
                  className="h-full transition-all duration-500"
                  style={{
                    width: `${Math.min(100, backpressure.utilization_percent)}%`,
                    background:
                      backpressure.utilization_percent >= 90
                        ? "#b91c1c"
                        : backpressure.utilization_percent >= 75
                        ? "#d97706"
                        : "#067647",
                  }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-[var(--subtle)] mt-1">
                <span>{workers.running_tasks} active tasks</span>
                <span>{workers.capacity} total fleet slots</span>
              </div>
            </div>

            <div className="pt-2 border-t border-[var(--line)] flex items-center justify-between text-xs">
              <span className="text-[var(--subtle)]">HTTP 429 Rate-Limited Requests (1h)</span>
              <span className="font-mono font-bold">{backpressure.rate_limited_requests}</span>
            </div>
          </div>
        </Panel>

        <Panel
          title="Worker Fleet Lifecycle"
          subtitle="Autonomous worker heartbeats and failure reclaims"
          delay={0.22}
        >
          <div className="space-y-3">
            <div className="grid grid-cols-5 gap-2 text-center text-xs">
              <div className="p-2 bg-[var(--app-bg)] border border-[var(--line)]">
                <div className="text-sm font-bold text-[#067647] font-mono">{workers.healthy}</div>
                <div className="text-[10px] text-[var(--subtle)] uppercase">Healthy</div>
              </div>
              <div className="p-2 bg-[var(--app-bg)] border border-[var(--line)]">
                <div className="text-sm font-bold text-[#006cd2] font-mono">{workers.busy}</div>
                <div className="text-[10px] text-[var(--subtle)] uppercase">Busy</div>
              </div>
              <div className="p-2 bg-[var(--app-bg)] border border-[var(--line)]">
                <div className="text-sm font-bold text-[var(--subtle)] font-mono">{workers.idle}</div>
                <div className="text-[10px] text-[var(--subtle)] uppercase">Idle</div>
              </div>
              <div className="p-2 bg-[var(--app-bg)] border border-[var(--line)]">
                <div className="text-sm font-bold text-[#d97706] font-mono">{workers.recovering}</div>
                <div className="text-[10px] text-[var(--subtle)] uppercase">Recovering</div>
              </div>
              <div className="p-2 bg-[var(--app-bg)] border border-[var(--line)]">
                <div className="text-sm font-bold text-[#b91c1c] font-mono">{workers.unhealthy}</div>
                <div className="text-[10px] text-[var(--subtle)] uppercase">Failed</div>
              </div>
            </div>

            {workers.last_recovery ? (
              <div className="p-3 bg-[var(--app-bg)] border border-[#006cd2]/30 text-xs">
                <div className="flex items-center justify-between font-semibold text-[#006cd2] mb-1">
                  <span className="flex items-center gap-1.5">
                    <RefreshCw size={12} /> Last Recovery Event
                  </span>
                  <span className="text-[11px] text-[var(--subtle)]">
                    {workers.last_recovery.occurred_at
                      ? relativeTime(workers.last_recovery.occurred_at)
                      : "recent"}
                  </span>
                </div>
                <div className="text-[var(--text)]">
                  <span className="font-mono font-bold">{workers.last_recovery.worker_id}</span>:{" "}
                  {workers.last_recovery.reason}
                </div>
                <div className="text-[var(--subtle)] text-[11px] mt-0.5">
                  Reclaimed and re-queued {workers.last_recovery.recovered_tasks} task(s)
                </div>
              </div>
            ) : (
              <div className="p-3 bg-[var(--app-bg)] border border-[var(--line)] text-xs text-[var(--subtle)] flex items-center gap-1.5">
                <CheckCircle2 size={13} className="text-[#067647]" /> All workers reporting healthy heartbeats; 0 stale tasks.
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* 6. RabbitMQ Queue Backlog */}
      <Panel
        title={
          <span className="flex items-center gap-2">
            <Layers size={18} className="text-[var(--brand)]" />
            <span>RabbitMQ Queue Backlog</span>
          </span>
        }
        subtitle="Real-time message saturation across main, retry, and dead-letter queues"
        delay={0.25}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 pb-4 border-b border-[var(--line)]">
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-[#006cd2]">MAIN QUEUE</span>
              <span className="font-mono font-bold">{queues.main} msgs</span>
            </div>
            <div className="w-full h-2 bg-[var(--line-soft)] rounded-sm overflow-hidden">
              <div
                className="h-full bg-[#006cd2] transition-all"
                style={{
                  width: `${Math.min(
                    100,
                    (queues.main / Math.max(1, queues.main + queues.retry + queues.dlq)) * 100
                  )}%`,
                }}
              />
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-[#d97706]">RETRY QUEUE</span>
              <span className="font-mono font-bold">{queues.retry} msgs</span>
            </div>
            <div className="w-full h-2 bg-[var(--line-soft)] rounded-sm overflow-hidden">
              <div
                className="h-full bg-[#d97706] transition-all"
                style={{
                  width: `${Math.min(
                    100,
                    (queues.retry / Math.max(1, queues.main + queues.retry + queues.dlq)) * 100
                  )}%`,
                }}
              />
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-[#6d28d9]">DEAD-LETTER QUEUE</span>
              <span className="font-mono font-bold">{queues.dlq} msgs</span>
            </div>
            <div className="w-full h-2 bg-[var(--line-soft)] rounded-sm overflow-hidden">
              <div
                className="h-full bg-[#6d28d9] transition-all"
                style={{
                  width: `${Math.min(
                    100,
                    (queues.dlq / Math.max(1, queues.main + queues.retry + queues.dlq)) * 100
                  )}%`,
                }}
              />
            </div>
          </div>
        </div>

        {queues.by_type && queues.by_type.length > 0 ? (
          <div className="space-y-3">
            {queues.by_type.map((q) => (
              <div
                key={q.task_type}
                className="p-3 bg-[var(--app-bg)] border border-[var(--line)]"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-xs tracking-wider uppercase">
                    {q.task_type.replace(/_/g, " ")}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-sm ${
                      q.status === "Healthy"
                        ? "bg-[#067647]/10 text-[#067647]"
                        : "bg-[#d97706]/10 text-[#d97706]"
                    }`}
                  >
                    {q.status}
                  </span>
                </div>
                <div className="space-y-1.5">
                  <BarRow
                    label="Main"
                    value={q.main_depth}
                    max={Math.max(1, q.total_depth)}
                    color="#006cd2"
                  />
                  <BarRow
                    label="Retry"
                    value={q.retry_depth}
                    max={Math.max(1, q.total_depth)}
                    color="#d97706"
                  />
                  <BarRow
                    label="DLQ"
                    value={q.dlq_depth}
                    max={Math.max(1, q.total_depth)}
                    color="#6d28d9"
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-[var(--subtle)]">No task queues active at this time.</p>
        )}
      </Panel>
    </div>
  );
}
