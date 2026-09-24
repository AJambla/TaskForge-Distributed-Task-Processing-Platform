import type { ReactNode } from "react";

interface FieldProps {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}

export default function Field({ label, hint, children, className = "" }: FieldProps) {
  return (
    <div className={`field ${className}`}>
      <label className="field__label">{label}</label>
      {children}
      {hint && <div className="field__hint">{hint}</div>}
    </div>
  );
}

export function Spinner({ size = 22 }: { size?: number }) {
  return (
    <span
      className="tf-spin"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}

export function PageLoading() {
  return (
    <div className="flex items-center justify-center py-20">
      <Spinner size={28} />
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
}) {
  return (
    <div className="px-6 py-16 text-center">
      {icon && (
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center" style={{ color: "var(--subtle)", border: "1px solid var(--line)" }}>
          {icon}
        </div>
      )}
      <p style={{ color: "var(--muted)", fontWeight: 500 }}>{title}</p>
      {hint && (
        <p className="mt-1 text-sm" style={{ color: "var(--subtle)" }}>
          {hint}
        </p>
      )}
    </div>
  );
}
