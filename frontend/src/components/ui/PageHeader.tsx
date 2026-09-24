import type { ReactNode } from "react";

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  back?: { label: string; to: string } | null;
}

export default function PageHeader({ title, subtitle, actions, back }: PageHeaderProps) {
  return (
    <div className="wipe" style={{ "--d": "0.02s" } as React.CSSProperties}>
      {back && (
        <a
          href={back.to}
          className="section-label inline-flex items-center gap-2 hover:text-brand"
          style={{ color: "var(--subtle)" }}
        >
          <span aria-hidden>←</span> {back.label}
        </a>
      )}
      <div className="flex flex-wrap items-end justify-between gap-4 pt-2">
        <div>
          <h1
            className="font-semibold"
            style={{ fontSize: 28, letterSpacing: "-0.03em", color: "var(--text)" }}
          >
            {title}
          </h1>
          {subtitle && (
            <p className="mt-1.5" style={{ color: "var(--subtle)", fontSize: 14 }}>
              {subtitle}
            </p>
          )}
        </div>
        {actions && <div className="flex items-center gap-3">{actions}</div>}
      </div>
      <div
        className="mt-5"
        style={{ height: 1, background: "linear-gradient(90deg, var(--brand) 0 56px, var(--line) 56px 100%)" }}
      />
    </div>
  );
}
