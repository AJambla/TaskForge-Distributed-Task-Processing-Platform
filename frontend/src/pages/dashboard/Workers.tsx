import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import client from "../../api/client";
import type { Worker } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { PageLoading, EmptyState } from "../../components/ui/Field";
import StatusPill from "../../components/ui/StatusPill";
import { Server } from "lucide-react";

function relativeTime(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function LoadBar({ current, limit }: { current: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, (current / limit) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="h-[6px] w-24" style={{ background: "var(--line)" }}>
        <div
          className="h-full"
          style={{
            width: `${pct}%`,
            background: pct >= 90 ? "#b91c1c" : "var(--brand)",
            transition: "width 0.4s cubic-bezier(0.16,1,0.3,1)",
          }}
        />
      </div>
      <span className="mono text-xs" style={{ color: "var(--subtle)" }}>
        {current}/{limit}
      </span>
    </div>
  );
}

export default function Workers() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["workers"],
    queryFn: async () => {
      const response = await client.get("/workers");
      return response.data as Worker[];
    },
    refetchInterval: 5000,
  });

  const isForbidden =
    (error as { response?: { status?: number } })?.response?.status === 403;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Workers"
        subtitle={
          <span className="inline-flex items-center gap-2">
            <span className="chip-dot" style={{ color: "var(--brand)" }} aria-hidden />
            Live worker pool status, refreshed every 5 seconds
          </span>
        }
      />

      {isForbidden ? (
        <Panel delay={0.08}>
          <EmptyState icon={<Server size={22} />} title="Worker visibility is restricted to admins." />
        </Panel>
      ) : isLoading ? (
        <PageLoading />
      ) : !data?.length ? (
        <Panel delay={0.08}>
          <EmptyState icon={<Server size={22} />} title="No workers have registered yet" />
        </Panel>
      ) : (
        <Panel bodyClassName="overflow-x-auto" delay={0.08}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Hostname</th>
                <th>Status</th>
                <th>Load</th>
                <th>Processed</th>
                <th>Failed</th>
                <th>Last Heartbeat</th>
              </tr>
            </thead>
            <tbody>
              {data.map((worker) => (
                <tr key={worker.id}>
                  <td>
                    <Link
                      to={`/app/workers/${worker.id}`}
                      className="navlink font-medium"
                      style={{ fontSize: 14 }}
                    >
                      {worker.hostname}
                    </Link>
                  </td>
                  <td>
                    <StatusPill status={worker.status} />
                  </td>
                  <td>
                    <LoadBar current={worker.current_task_count} limit={worker.concurrency_limit} />
                  </td>
                  <td className="mono text-sm">{worker.tasks_processed}</td>
                  <td className="mono text-sm" style={{ color: worker.tasks_failed > 0 ? "#b91c1c" : undefined }}>
                    {worker.tasks_failed}
                  </td>
                  <td style={{ color: "var(--subtle)" }}>{relativeTime(worker.last_heartbeat_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}
