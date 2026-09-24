import type { ComponentProps } from "react";
import { Link } from "react-router-dom";
import { ArrowGlyph } from "./Logo";

type Variant = "nav" | "light" | "ghost" | "quiet" | "danger";
type Size = "md" | "sm";

interface BaseProps {
  variant?: Variant;
  size?: Size;
  withIcon?: boolean;
  /** entrance wipe-in delay in seconds; enables the .wipe-r animation */
  delay?: number;
  className?: string;
  children: React.ReactNode;
}

function btnClass(
  { variant = "nav", size = "md", className = "" }: BaseProps,
  anim: "wipe" | "wipe-r" | null
) {
  return [
    "btn",
    `btn--${variant}`,
    size === "sm" ? "btn--sm" : "",
    anim ? (anim === "wipe" ? "wipe" : "wipe-r") : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
}

function delayStyle(delay?: number): React.CSSProperties | undefined {
  return delay !== undefined ? ({ "--d": `${delay}s` } as React.CSSProperties) : undefined;
}

function Inner({ children, withIcon }: { children: React.ReactNode; withIcon: boolean }) {
  return (
    <>
      <span className="btn__label">{children}</span>
      {withIcon && (
        <span className="btn__icon">
          <ArrowGlyph />
        </span>
      )}
    </>
  );
}

export function Button({
  children,
  variant,
  size,
  withIcon = false,
  delay,
  className,
  style,
  ...rest
}: BaseProps & ComponentProps<"button">) {
  return (
    <button
      className={btnClass({ children, variant, size, delay, className }, delay != null ? "wipe" : null)}
      style={{ ...delayStyle(delay), ...style }}
      {...rest}
    >
      <Inner withIcon={withIcon}>{children}</Inner>
    </button>
  );
}

export function ButtonLink({
  to,
  children,
  variant,
  size,
  withIcon = false,
  delay,
  className,
}: BaseProps & { to: string }) {
  return (
    <Link
      to={to}
      className={btnClass({ children, variant, size, delay, className }, null)}
      style={delayStyle(delay)}
    >
      <Inner withIcon={withIcon}>{children}</Inner>
    </Link>
  );
}

export default Button;
