import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import client from "../../api/client";
import type { APIKey, CreateAPIKeyRequest, CreateAPIKeyResponse } from "../../types";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import Modal from "../../components/ui/Modal";
import Field, { Spinner, EmptyState } from "../../components/ui/Field";
import { Button } from "../../components/ui/Button";
import { Copy, Check, Trash2, Key } from "lucide-react";

export default function ApiKeys() {
  const queryClient = useQueryClient();
  const [showNewKey, setShowNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const { data: keys, isLoading } = useQuery({
    queryKey: ["api-keys"],
    queryFn: async () => {
      const response = await client.get("/api-keys");
      return response.data as APIKey[];
    },
  });

  const createMutation = useMutation({
    mutationFn: async (name: string) => {
      const response = await client.post<CreateAPIKeyResponse>("/api-keys", { name } as CreateAPIKeyRequest);
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      setShowNewKey(data.key);
      setShowCreateModal(false);
      setNewKeyName("");
    },
  });

  const revokeMutation = useMutation({
    mutationFn: async (keyId: string) => {
      await client.delete(`/api-keys/${keyId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const copyToClipboard = (text: string, keyId: string) => {
    navigator.clipboard.writeText(text);
    setCopied(keyId);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="API Keys"
        subtitle="Manage your programmatic access keys"
        actions={
          <Button variant="nav" size="sm" withIcon onClick={() => setShowCreateModal(true)}>
            New Key
          </Button>
        }
      />

      {showNewKey && (
        <div
          className="rise p-5"
          style={{
            background: "rgba(6,118,71,0.06)",
            border: "1px solid rgba(6,118,71,0.3)",
            "--d": "0.05s",
          } as React.CSSProperties}
        >
          <span className="chip chip--succeeded">New API key created</span>
          <p className="mt-3 text-sm" style={{ color: "var(--subtle)" }}>
            This key will not be shown again. Save it securely.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code
              className="mono flex-1 overflow-x-auto px-4 py-3 text-sm"
              style={{ background: "#fff", border: "1px solid rgba(6,118,71,0.3)", color: "#067647" }}
            >
              {showNewKey}
            </code>
            <button
              onClick={() => copyToClipboard(showNewKey, "new")}
              className="icon-btn"
              aria-label="Copy key"
              style={{ background: "#fff" }}
            >
              {copied === "new" ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
          <button
            onClick={() => setShowNewKey(null)}
            className="navlink mt-3 !text-xs"
            style={{ color: "var(--brand)" }}
          >
            Done
          </button>
        </div>
      )}

      <Panel bodyClassName="" delay={0.08}>
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner size={26} />
          </div>
        ) : !keys?.length ? (
          <EmptyState
            icon={<Key size={22} />}
            title="No API keys yet"
            hint="Create your first key to get started."
          />
        ) : (
          <ul>
            {keys.map((key) => {
              const revoked = key.revoked_at !== null;
              return (
                <li
                  key={key.id}
                  className="flex flex-wrap items-center justify-between gap-4 px-6 py-4"
                  style={{ borderBottom: "1px solid var(--line-soft)" }}
                >
                  <div className="flex items-center gap-4">
                    <div
                      className="flex h-10 w-10 items-center justify-center"
                      style={{
                        border: "1px solid var(--line)",
                        background: "var(--app-bg)",
                        color: revoked ? "var(--line-strong)" : "var(--brand)",
                      }}
                    >
                      <Key size={16} />
                    </div>
                    <div>
                      <p
                        className="font-medium"
                        style={{
                          color: revoked ? "var(--subtle)" : "var(--text)",
                          textDecoration: revoked ? "line-through" : undefined,
                        }}
                      >
                        {key.name}
                      </p>
                      <p className="mono text-xs" style={{ color: "var(--subtle)" }}>
                        {key.key_prefix}…
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-xs" style={{ color: "var(--subtle)" }}>
                      {key.last_used_at
                        ? `Last used ${new Date(key.last_used_at).toLocaleDateString()}`
                        : "Never used"}
                    </span>
                    <button
                      onClick={() => revokeMutation.mutate(key.id)}
                      disabled={revoked}
                      className="icon-btn icon-btn--danger"
                      title="Revoke key"
                      aria-label={`Revoke ${key.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      {showCreateModal && (
        <Modal
          title="Create API Key"
          subtitle="Keys grant programmatic access to your queues"
          onClose={() => setShowCreateModal(false)}
        >
          <div className="space-y-5">
            <Field label="Key name">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                className="field__input"
                placeholder="e.g., Production Key"
                maxLength={100}
              />
            </Field>
            <div className="flex items-center justify-end gap-3">
              <Button variant="quiet" onClick={() => setShowCreateModal(false)}>
                Cancel
              </Button>
              <Button
                variant="nav"
                size="sm"
                withIcon
                disabled={!newKeyName.trim() || createMutation.isPending}
                onClick={() => createMutation.mutate(newKeyName)}
              >
                {createMutation.isPending ? "Creating…" : "Create Key"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
