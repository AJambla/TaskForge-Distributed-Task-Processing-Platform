import type { ReactNode } from "react";

export default function StatCard({
  label,
  value,
  unit,
  sub,
  icon,
  accent = "var(--brand)",
  right,
  delay,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  icon?: ReactNode;
  accent?: string;
  right?: ReactNode;
  delay?: number;
}) {
  return (
    <div
      className={`stat ${delay !== undefined ? "rise" : ""}`}
      style={delay !== undefined ? ({ "--d": `${delay}s` } as React.CSSProperties) : undefined}
    >
      <div className="stat__top">
        <span className="stat__label">
          {icon && (
            <span className="stat__icon" style={{ color: accent }}>
              {icon}
            </span>
          )}
          {label}
        </span>
        {right}
      </div>
      <div className="stat__value">
        {value}
        {unit && <span className="stat__unit">{unit}</span>}
      </div>
      {sub && <div className="stat__sub">{sub}</div>}
    </div>
  );
}
