import { useState } from "react";
import Modal from "./ui/Modal";
import { Button } from "./ui/Button";
import { AlertCircle, Check, Copy, KeyRound } from "lucide-react";
import type { CreateAPIKeyResponse } from "../types";

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (name: string) => Promise<void> | void;
  isCreating: boolean;
  createdKey: CreateAPIKeyResponse | null;
  onDone: () => void;
}

export default function ApiKeyModal({
  isOpen,
  onClose,
  onCreate,
  isCreating,
  createdKey,
  onDone,
}: ApiKeyModalProps) {
  const [name, setName] = useState("");
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onCreate(name.trim());
  };

  const handleCopy = async () => {
    if (!createdKey) return;
    try {
      await navigator.clipboard.writeText(createdKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // ignore
    }
  };

  if (createdKey) {
    return (
      <Modal
        title="API Key Generated"
        subtitle="Save this key in a secure location"
        onClose={onDone}
      >
        <div className="space-y-4">
          <div
            className="rounded-lg p-3.5 flex items-start gap-3 text-xs leading-relaxed"
            style={{
              background: "rgba(234, 88, 12, 0.1)",
              border: "1px solid rgba(234, 88, 12, 0.3)",
              color: "#fb923c",
            }}
          >
            <AlertCircle size={16} className="shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold mb-0.5">Save this secret key immediately.</p>
              <p className="opacity-90">
                For security reasons, TaskForge does not store the raw key and will never show it again.
              </p>
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--subtle)" }}>
              API Key ({createdKey.name})
            </label>
            <div
              className="flex items-center justify-between p-3 rounded-lg border gap-3"
              style={{ background: "var(--surface)", borderColor: "var(--line)" }}
            >
              <span className="mono text-xs select-all break-all font-medium" style={{ color: "var(--text)" }}>
                {createdKey.key}
              </span>
              <button
                type="button"
                onClick={handleCopy}
                className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition cursor-pointer hover:opacity-80"
                style={{
                  background: copied ? "rgba(16, 185, 129, 0.15)" : "var(--brand)",
                  color: copied ? "#10b981" : "#fff",
                }}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? "Copied!" : "Copy Key"}</span>
              </button>
            </div>
          </div>

          <div className="pt-2 flex justify-end">
            <Button variant="nav" onClick={onDone}>
              Done
            </Button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Create API Key"
      subtitle="Issue an authentication token for the TaskForge REST API"
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--subtle)" }}>
            Key Name / Description
          </label>
          <input
            type="text"
            required
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Production Ingestion Service, CI/CD Runner"
            className="field__input w-full !h-10"
          />
          <p className="text-[11px] mt-1" style={{ color: "var(--subtle)" }}>
            Give this key a recognizable name to track where it is being used.
          </p>
        </div>

        <div className="pt-3 flex justify-end gap-3">
          <Button variant="ghost" type="button" onClick={onClose} disabled={isCreating}>
            Cancel
          </Button>
          <Button variant="nav" type="submit" disabled={isCreating || !name.trim()} withIcon>
            <KeyRound size={14} />
            {isCreating ? "Generating…" : "Generate API Key"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
