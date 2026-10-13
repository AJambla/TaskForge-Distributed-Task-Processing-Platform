import { useState } from "react";
import { Check, Copy, ChevronDown, ChevronRight } from "lucide-react";

interface JsonViewerProps {
  data: unknown;
  label?: string;
  emptyText?: string;
  defaultExpanded?: boolean;
  highlightSuccess?: boolean;
}

export default function JsonViewer({
  data,
  label,
  emptyText = "None",
  defaultExpanded = true,
  highlightSuccess = false,
}: JsonViewerProps) {
  const [copied, setCopied] = useState(false);
  const [collapsed, setCollapsed] = useState(!defaultExpanded);

  if (data === null || data === undefined) {
    return (
      <div className="rounded-lg p-3 text-xs" style={{ background: "var(--surface)", border: "1px solid var(--line)" }}>
        {label && <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--subtle)" }}>{label}</div>}
        <span className="italic" style={{ color: "var(--subtle)" }}>{emptyText}</span>
      </div>
    );
  }

  const jsonString = typeof data === "string" ? data : JSON.stringify(data, null, 2);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(jsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div
      className="rounded-lg overflow-hidden text-xs"
      style={{
        background: highlightSuccess ? "rgba(16, 185, 129, 0.04)" : "var(--surface)",
        border: highlightSuccess ? "1px solid rgba(16, 185, 129, 0.3)" : "1px solid var(--line)",
      }}
    >
      <div
        className="flex items-center justify-between px-3 py-2 border-b select-none"
        style={{ borderColor: highlightSuccess ? "rgba(16, 185, 129, 0.2)" : "var(--line)" }}
      >
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center gap-1.5 font-semibold text-[11px] uppercase tracking-wider hover:opacity-80 transition cursor-pointer"
          style={{ color: highlightSuccess ? "#10b981" : "var(--subtle)" }}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          <span>{label || "Data"}</span>
        </button>

        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded hover:opacity-80 transition cursor-pointer"
          style={{
            background: "var(--surface-muted, rgba(255, 255, 255, 0.05))",
            color: copied ? "#10b981" : "var(--subtle)",
            border: "1px solid var(--line)",
          }}
          title="Copy JSON"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>

      {!collapsed && (
        <pre
          className="p-3 mono overflow-x-auto text-[11.5px] leading-relaxed max-h-72 whitespace-pre"
          style={{ color: "var(--text)" }}
        >
          {jsonString}
        </pre>
      )}
    </div>
  );
}
