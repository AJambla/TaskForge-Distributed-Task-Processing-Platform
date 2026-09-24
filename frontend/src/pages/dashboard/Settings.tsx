import { Link } from "react-router-dom";
import { KeyRound, LogOut, ShieldCheck, UserRound } from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { useAuth } from "../../context/AuthContext";

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
      style={{ borderTop: "1px solid var(--line-soft)" }}
    >
      <span className="text-sm" style={{ color: "var(--subtle)" }}>
        {label}
      </span>
      <span
        className={mono ? "mono text-sm" : "text-sm font-medium"}
        style={{ color: "var(--text)" }}
      >
        {value}
      </span>
    </div>
  );
}

export default function Settings() {
  const { user, logout } = useAuth();

  return (
    <div className="space-y-8">
      <PageHeader title="Settings" subtitle="Your account and session" />

      <Panel title={<span className="inline-flex items-center gap-2"><UserRound size={14} style={{ color: "var(--subtle)" }} /> Account</span>} delay={0.08} bodyClassName="">
        <Row label="Email" value={user?.email || "—"} />
        <Row
          label="Role"
          value={
            <span className="inline-flex items-center gap-2">
              <ShieldCheck size={13} style={{ color: "var(--brand)" }} />
              {user?.role ?? "user"}
            </span>
          }
        />
        <Row label="Account ID" value={user?.id || "—"} mono />
      </Panel>

      <Panel title="Access" delay={0.16} bodyClassName="">
        <div
          className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
          style={{ borderTop: "1px solid var(--line-soft)" }}
        >
          <span className="text-sm" style={{ color: "var(--subtle)" }}>
            Manage the API keys your services use to submit tasks
          </span>
          <Link to="/app/api-keys" className="navlink inline-flex items-center gap-1.5" style={{ color: "var(--brand)" }}>
            <KeyRound size={14} /> API Keys
          </Link>
        </div>
        <div
          className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
          style={{ borderTop: "1px solid var(--line-soft)" }}
        >
          <span className="text-sm" style={{ color: "var(--subtle)" }}>
            End this session on this device
          </span>
          <button
            onClick={logout}
            className="navlink inline-flex items-center gap-1.5"
            style={{ color: "#b91c1c" }}
          >
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </Panel>
    </div>
  );
}
