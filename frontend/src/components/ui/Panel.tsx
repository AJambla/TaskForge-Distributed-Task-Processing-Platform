import type { ReactNode } from "react";

interface PanelProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** entrance fade-up delay in seconds */
  delay?: number;
}

export default function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  bodyClassName,
  delay,
}: PanelProps) {
  return (
    <section
      className={`panel ${delay !== undefined ? "rise" : ""} ${className}`}
      style={delay !== undefined ? ({ "--d": `${delay}s` } as React.CSSProperties) : undefined}
    >
      {(title || actions) && (
        <header className="panel__head">
          <div>
            {title && <h2 className="panel__title">{title}</h2>}
            {subtitle && <p className="panel__sub">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {bodyClassName === undefined ? (
        <div className="panel__body">{children}</div>
      ) : (
        <div className={bodyClassName}>{children}</div>
      )}
    </section>
  );
}
