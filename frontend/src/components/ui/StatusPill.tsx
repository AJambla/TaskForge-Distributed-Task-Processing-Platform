import type { ReactNode } from "react";

const ICONS: Record<string, ReactNode> = {
  queued: (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
      <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  ),
  running: <span className="chip-dot" aria-hidden />,
  succeeded: <Check />,
  failed: <Cross />,
  retrying: <Refresh />,
  dead_letter: <Box />,
  cancelled: <Minus />,
  online: <span className="chip-dot" aria-hidden />,
  offline: (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
      <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  ),
  draining: <Refresh />,
};

function Check() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
      <path d="M2 6.5 4.8 9 10 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function Cross() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
      <path d="M3 3l6 6M9 3l-6 6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
function Refresh() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
      <path d="M10 6a4 4 0 1 1-1.2-2.85M10 1.5V4H7.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function Box() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
      <rect x="2" y="2" width="8" height="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
function Minus() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
      <path d="M2.5 6h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export default function StatusPill({ status }: { status: string }) {
  return (
    <span className={`chip chip--${status}`}>
      {ICONS[status]}
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function OutcomeText({ outcome }: { outcome: string }) {
  const cls =
    outcome === "success"
      ? "chip--succeeded"
      : outcome === "failure"
        ? "chip--failed"
        : outcome === "timeout"
          ? "chip--retrying"
          : "chip--cancelled";
  return (
    <span className={`chip ${cls}`}>{outcome || "running"}</span>
  );
}
