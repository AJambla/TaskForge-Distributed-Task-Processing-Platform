import { useState } from "react";
import { KeyRound, LogOut, ShieldCheck, Trash2, UserRound } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { Button } from "../../components/ui/Button";
import ApiKeyModal from "../../components/ApiKeyModal";
import { useAuth } from "../../context/AuthContext";
import { useApiKeys } from "../../api/queries";
import client from "../../api/client";
import type { CreateAPIKeyResponse } from "../../types";
import { relativeTime } from "../../lib/format";

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
  const queryClient = useQueryClient();

  const { data: apiKeys = [], isLoading: isLoadingKeys } = useApiKeys();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreateAPIKeyResponse | null>(null);

  const createKeyMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await client.post<CreateAPIKeyResponse>("/api-keys", { name });
      return res.data;
    },
    onSuccess: (data) => {
      setCreatedKey(data);
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const revokeKeyMutation = useMutation({
    mutationFn: async (keyId: string) => {
      await client.delete(`/api-keys/${keyId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const handleOpenModal = () => {
    setCreatedKey(null);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setCreatedKey(null);
  };

  const handleRevoke = (id: string, name: string) => {
    if (window.confirm(`Are you sure you want to revoke API key "${name}"? Applications using this key will immediately be denied access.`)) {
      revokeKeyMutation.mutate(id);
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader title="Settings" subtitle="Your account, credentials, and API access" />

      <Panel
        title={
          <span className="inline-flex items-center gap-2">
            <UserRound size={14} style={{ color: "var(--subtle)" }} /> Account
          </span>
        }
        delay={0.08}
        bodyClassName=""
      >
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

      <Panel
        title={
          <div className="flex items-center justify-between w-full">
            <span className="inline-flex items-center gap-2">
              <KeyRound size={14} style={{ color: "var(--brand)" }} /> API Keys
            </span>
            <Button size="sm" variant="nav" onClick={handleOpenModal} withIcon>
              <KeyRound size={13} />
              Generate API Key
            </Button>
          </div>
        }
        delay={0.12}
        bodyClassName="p-0"
      >
        <div className="p-6 pb-2">
          <p className="text-xs" style={{ color: "var(--subtle)" }}>
            API keys allow external systems and automation workers to submit and query tasks via the TaskForge REST API using the <code className="mono text-xs text-[var(--brand)]">X-API-Key</code> header.
          </p>
        </div>

        {isLoadingKeys ? (
          <div className="p-6 text-center text-xs" style={{ color: "var(--subtle)" }}>
            Loading API keys…
          </div>
        ) : apiKeys.length === 0 ? (
          <div className="p-8 text-center text-xs" style={{ color: "var(--subtle)" }}>
            No API keys created yet. Generate one above to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="tbl w-full text-xs">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Key Prefix</th>
                  <th>Created</th>
                  <th>Last Used</th>
                  <th>Status</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {apiKeys.map((key) => {
                  const isRevoked = Boolean(key.revoked_at);
                  return (
                    <tr key={key.id}>
                      <td className="font-medium" style={{ color: "var(--text)" }}>
                        {key.name}
                      </td>
                      <td>
                        <span className="mono text-xs px-2 py-0.5 rounded" style={{ background: "var(--surface)", border: "1px solid var(--line)" }}>
                          {key.key_prefix}…
                        </span>
                      </td>
                      <td className="mono" title={new Date(key.created_at).toLocaleString()}>
                        {relativeTime(key.created_at)}
                      </td>
                      <td className="mono">
                        {key.last_used_at ? (
                          <span title={new Date(key.last_used_at).toLocaleString()}>
                            {relativeTime(key.last_used_at)}
                          </span>
                        ) : (
                          <span style={{ color: "var(--subtle)" }}>Never</span>
                        )}
                      </td>
                      <td>
                        {isRevoked ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium mono chip chip--failed">
                            Revoked
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium mono chip chip--succeeded">
                            Active
                          </span>
                        )}
                      </td>
                      <td className="text-right">
                        {!isRevoked && (
                          <button
                            type="button"
                            onClick={() => handleRevoke(key.id, key.name)}
                            disabled={revokeKeyMutation.isPending}
                            className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-1 rounded text-rose-400 hover:bg-rose-500/10 transition cursor-pointer"
                            title="Revoke this API key"
                          >
                            <Trash2 size={12} />
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Access" delay={0.16} bodyClassName="">
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

      <ApiKeyModal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onCreate={(name) => createKeyMutation.mutate(name)}
        isCreating={createKeyMutation.isPending}
        createdKey={createdKey}
        onDone={handleCloseModal}
      />
    </div>
  );
}
