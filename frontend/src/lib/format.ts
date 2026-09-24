export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const abs = Math.abs(diff);
  const suffix = (v: string) => (diff >= 0 ? `${v} ago` : `in ${v}`);
  if (abs < 5_000) return "just now";
  if (abs < 60_000) return suffix(`${Math.round(abs / 1000)}s`);
  if (abs < 3_600_000) return suffix(`${Math.round(abs / 60_000)}m`);
  if (abs < 86_400_000) return suffix(`${Math.round(abs / 3_600_000)}h`);
  return suffix(`${Math.round(abs / 86_400_000)}d`);
}

export function formatSeconds(
  seconds: number | null | undefined,
  digits = 1
): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${seconds.toFixed(digits)}s`;
  if (seconds < 3_600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
  }
  const h = Math.floor(seconds / 3_600);
  const m = Math.round((seconds % 3_600) / 60);
  return `${h}h ${m}m`;
}

export function durationBetween(
  startIso: string | null | undefined,
  endIso: string | null | undefined
): string {
  if (!startIso) return "—";
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  return formatSeconds((end - new Date(startIso).getTime()) / 1000, 2);
}

export function shortId(id: string, len = 8): string {
  return id.slice(0, len);
}

export function formatNumber(n: number): string {
  return n.toLocaleString();
}

export function timeOfDay(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
