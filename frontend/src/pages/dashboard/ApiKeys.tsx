import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "../../api/client";
import type { APIKey, CreateAPIKeyRequest, CreateAPIKeyResponse } from "../../types";
import { Plus, Copy, Check, Trash2, Loader2, Key } from "lucide-react";
import { useState } from "react";

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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">API Keys</h1>
          <p className="text-slate-400 mt-1">Manage your programmatic access keys</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-2 px-4 rounded-lg transition-colors"
        >
          <Plus size={16} />
          New Key
        </button>
      </div>

      {showNewKey && (
        <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4">
          <div className="flex items-center gap-2 text-green-400 mb-2">
            <Check size={16} />
            <span className="font-medium">New API key created</span>
          </div>
          <p className="text-sm text-green-300/70 mb-3">
            This key will not be shown again. Save it securely.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-slate-950 border border-green-500/20 rounded-lg px-4 py-2 text-sm font-mono text-green-300">
              {showNewKey}
            </code>
            <button
              onClick={() => copyToClipboard(showNewKey, "new")}
              className="p-2 text-green-400 hover:text-green-300 hover:bg-green-500/10 rounded-lg transition-colors"
            >
              {copied === "new" ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
          <button
            onClick={() => setShowNewKey(null)}
            className="mt-3 text-sm text-green-400/70 hover:text-green-400"
          >
            Done
          </button>
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={32} className="text-indigo-500 animate-spin" />
          </div>
        ) : !keys?.length ? (
          <div className="text-center py-16 text-slate-400">
            <Key className="mx-auto mb-4 opacity-50" size={48} />
            <p>No API keys yet</p>
            <p className="text-sm mt-1">Create your first key to get started</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {keys.map((key) => (
              <div key={key.id} className="px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-slate-800 rounded-lg flex items-center justify-center">
                    <Key size={18} className="text-slate-400" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-200">{key.name}</p>
                    <p className="text-sm text-slate-500 font-mono">{key.key_prefix}…</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-slate-500">
                    {key.last_used_at
                      ? `Last used ${new Date(key.last_used_at).toLocaleDateString()}`
                      : "Never used"}
                  </span>
                  <button
                    onClick={() => revokeMutation.mutate(key.id)}
                    disabled={key.revoked_at !== null}
                    className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-800 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    title="Revoke key"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-slate-800">
              <h2 className="text-lg font-semibold text-slate-100">Create API Key</h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <Plus size={20} className="rotate-45" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Key name
                </label>
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="e.g., Production Key"
                  maxLength={100}
                />
              </div>
              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => createMutation.mutate(newKeyName)}
                  disabled={!newKeyName.trim() || createMutation.isPending}
                  className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-medium py-2 px-4 rounded-lg transition-colors"
                >
                  {createMutation.isPending ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Key size={16} />
                      Create Key
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
