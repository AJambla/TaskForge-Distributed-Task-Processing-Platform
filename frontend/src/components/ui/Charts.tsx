import { useId } from "react";

export const STATUS_COLORS: Record<string, string> = {
  queued: "#006cd2",
  running: "#d97706",
  succeeded: "#067647",
  failed: "#b91c1c",
  retrying: "#c2410c",
  dead_letter: "#6d28d9",
  cancelled: "#6b7378",
};

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

export function Donut({
  segments,
  size = 168,
  thickness = 26,
  centerValue,
  centerLabel,
}: {
  segments: DonutSegment[];
  size?: number;
  thickness?: number;
  centerValue?: string;
  centerLabel?: string;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="donut" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden>
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--line-soft, #eceef0)"
            strokeWidth={thickness}
          />
          {total > 0 &&
            segments.map((seg) => {
              const len = (seg.value / total) * c;
              const el = (
                <circle
                  key={seg.label}
                  cx={size / 2}
                  cy={size / 2}
                  r={r}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth={thickness}
                  strokeDasharray={`${len} ${c - len}`}
                  strokeDashoffset={-offset}
                />
              );
              offset += len;
              return el;
            })}
        </g>
      </svg>
      <div className="donut__center">
        {centerValue && <span className="donut__value">{centerValue}</span>}
        {centerLabel && <span className="donut__label">{centerLabel}</span>}
      </div>
    </div>
  );
}

export function DonutLegend({ segments }: { segments: DonutSegment[] }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <ul className="donut-legend">
      {segments.map((seg) => (
        <li key={seg.label}>
          <span className="donut-legend__swatch" style={{ background: seg.color }} />
          <span className="donut-legend__label">{seg.label.replace(/_/g, " ")}</span>
          <span className="donut-legend__value mono">{seg.value.toLocaleString()}</span>
          <span className="donut-legend__pct mono">
            {((seg.value / total) * 100).toFixed(1)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export function AreaLine({
  points,
  labels,
  height = 180,
  color = "var(--brand)",
}: {
  points: number[];
  labels?: string[];
  height?: number;
  color?: string;
}) {
  const gradId = useId();
  const w = 600;
  const h = height;
  const pad = 8;
  const max = Math.max(...points, 1);
  const step = points.length > 1 ? (w - pad * 2) / (points.length - 1) : 0;
  const xy = points.map(
    (p, i) => [pad + i * step, h - pad - (p / max) * (h - pad * 2)] as const
  );
  const line = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area =
    points.length > 0
      ? `M ${xy[0][0]},${h - pad} L ${line.replace(/ /g, " L ")} L ${xy[xy.length - 1][0]},${h - pad} Z`
      : "";

  return (
    <div className="arealine">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ height, width: "100%" }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={pad}
            x2={w - pad}
            y1={pad + f * (h - pad * 2)}
            y2={pad + f * (h - pad * 2)}
            stroke="var(--line-soft, #eceef0)"
            strokeWidth="1"
          />
        ))}
        {area && <path d={area} fill={`url(#${gradId})`} />}
        {xy.length > 1 && (
          <polyline
            points={line}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        )}
        {xy.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={i === xy.length - 1 ? 3.5 : 0} fill={color} />
        ))}
      </svg>
      {labels && (
        <div className="arealine__labels mono">
          {labels.map((l, i) => (
            <span key={i}>{l}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function BarRow({
  label,
  value,
  max,
  color = "var(--brand)",
  suffix,
}: {
  label: string;
  value: number;
  max: number;
  color?: string;
  suffix?: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="bar-row">
      <span className="bar-row__label">{label}</span>
      <span className="bar-row__track">
        <span className="bar-row__fill" style={{ width: `${pct}%`, background: color }} />
      </span>
      <span className="bar-row__value mono">
        {value.toLocaleString()}
        {suffix}
      </span>
    </div>
  );
}

export function Sparkline({
  points,
  width = 96,
  height = 28,
  color = "var(--brand)",
}: {
  points: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (points.length < 2) return <svg width={width} height={height} aria-hidden />;
  const max = Math.max(...points, 1);
  const step = width / (points.length - 1);
  const line = points
    .map((p, i) => `${(i * step).toFixed(1)},${(height - 2 - (p / max) * (height - 6)).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
