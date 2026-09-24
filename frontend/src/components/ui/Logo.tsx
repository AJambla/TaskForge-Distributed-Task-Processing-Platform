interface LogoMarkProps {
  width?: number;
  delayBase?: number;
}

const BARS = [
  { x: 2, y: 2, w: 22 },
  { x: 5.5, y: 10, w: 26 },
  { x: 9, y: 18, w: 20 },
  { x: 12.5, y: 26, w: 24 },
];

const SKEW = 3.2;
const H = 4.4;

export function LogoMark({ width = 34, delayBase = 0.04 }: LogoMarkProps) {
  return (
    <svg
      className="logo-mark"
      viewBox="0 0 42 34"
      width={width}
      style={{ color: "#0a0a0a" }}
      aria-hidden="true"
    >
      {BARS.map((b, i) => (
        <polygon
          key={i}
          points={`${b.x},${b.y} ${b.x + b.w},${b.y} ${b.x + b.w + SKEW},${b.y + H} ${b.x + SKEW},${b.y + H}`}
          fill={i === 1 ? "#006cd2" : "currentColor"}
          style={{ animationDelay: `${delayBase + i * 0.05}s` }}
        />
      ))}
    </svg>
  );
}

export default function Logo({
  width = 34,
  withWordmark = true,
  className = "",
}: {
  width?: number;
  withWordmark?: boolean;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <LogoMark width={width} />
      {withWordmark && (
        <span
          className="font-semibold tracking-[-0.03em]"
          style={{ fontSize: width * 0.55, color: "var(--text)" }}
        >
          TaskForge
        </span>
      )}
    </span>
  );
}

export function ArrowGlyph() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 10h10.2M10.4 5.6 15.2 10l-4.8 4.4" />
    </svg>
  );
}
