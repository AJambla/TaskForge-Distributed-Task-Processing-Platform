import { AlertTriangle, Clock, RefreshCw, Server, ZapOff } from "lucide-react";
import type { FailureClassification, FailureDiagnostics } from "../types";
import { relativeTime } from "../lib/format";

const CLASSIFICATION_META: Record<
  FailureClassification,
  { label: string; icon: React.ReactNode; color: string; bg: string; border: string }
> = {
  TRANSIENT_ERROR: {
    label: "Transient Error",
    icon: <RefreshCw size={14} className="animate-spin" />,
    color: "#d97706",
    bg: "rgba(217, 119, 6, 0.1)",
    border: "rgba(217, 119, 6, 0.25)",
  },
  RATE_LIMITED: {
    label: "Rate Limited (429)",
    icon: <Clock size={14} />,
    color: "#ea580c",
    bg: "rgba(234, 88, 12, 0.1)",
    border: "rgba(234, 88, 12, 0.25)",
  },
  TIMEOUT: {
    label: "Execution Timeout",
    icon: <Clock size={14} />,
    color: "#9333ea",
    bg: "rgba(147, 51, 234, 0.1)",
    border: "rgba(147, 51, 234, 0.25)",
  },
  WORKER_CRASH: {
    label: "Worker Crash / Stale Node",
    icon: <Server size={14} />,
    color: "#e11d48",
    bg: "rgba(225, 29, 72, 0.1)",
    border: "rgba(225, 29, 72, 0.25)",
  },
  FATAL_ERROR: {
    label: "Fatal Error",
    icon: <ZapOff size={14} />,
    color: "#b91c1c",
    bg: "rgba(185, 28, 28, 0.1)",
    border: "rgba(185, 28, 28, 0.25)",
  },
};

interface FailureDiagnosticsCardProps {
  diagnostics: FailureDiagnostics;
}

export default function FailureDiagnosticsCard({ diagnostics }: FailureDiagnosticsCardProps) {
  const meta = CLASSIFICATION_META[diagnostics.classification] || {
    label: diagnostics.classification,
    icon: <AlertTriangle size={14} />,
    color: "#b91c1c",
    bg: "rgba(185, 28, 28, 0.1)",
    border: "rgba(185, 28, 28, 0.25)",
  };

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{
        background: meta.bg,
        border: `1px solid ${meta.border}`,
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold mono"
            style={{
              background: meta.bg,
              color: meta.color,
              border: `1px solid ${meta.border}`,
            }}
          >
            {meta.icon}
            {meta.label}
          </span>
          <span className="text-xs" style={{ color: "var(--subtle)" }}>
            Attempt #{diagnostics.failed_attempt}
          </span>
        </div>

        {diagnostics.will_retry && diagnostics.next_retry_at ? (
          <span className="inline-flex items-center gap-1 text-xs mono font-medium" style={{ color: meta.color }}>
            <RefreshCw size={12} /> Next retry {relativeTime(diagnostics.next_retry_at)}
          </span>
        ) : (
          <span className="text-xs font-medium" style={{ color: "#b91c1c" }}>
            Terminal failure (no further retries)
          </span>
        )}
      </div>

      <div className="space-y-1.5 text-xs">
        <div>
          <span className="font-semibold uppercase tracking-wider text-[10px]" style={{ color: "var(--subtle)" }}>
            Root Cause:{" "}
          </span>
          <span className="font-medium" style={{ color: "var(--text)" }}>
            {diagnostics.cause_description}
          </span>
        </div>

        <div>
          <span className="font-semibold uppercase tracking-wider text-[10px]" style={{ color: "var(--subtle)" }}>
            Recovery Action:{" "}
          </span>
          <span style={{ color: "var(--text)" }}>
            {diagnostics.recovery_action}
          </span>
        </div>
      </div>
    </div>
  );
}
