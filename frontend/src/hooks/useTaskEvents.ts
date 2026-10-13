import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Task } from "../types";

export function useTaskEvents(taskId: string | null | undefined, enabled = true) {
  const queryClient = useQueryClient();
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!taskId || !enabled) return;

    const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
    const token = localStorage.getItem("access_token");
    const streamUrl = `${baseURL}/tasks/${taskId}/events${token ? `?token=${encodeURIComponent(token)}` : ""}`;

    const es = new EventSource(streamUrl);
    esRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Live patch active query cache for immediate UI responsiveness
        queryClient.setQueryData(["task", taskId], (prev: Task | undefined) => {
          if (!prev) return prev;
          return {
            ...prev,
            status: data.status ?? prev.status,
            completed_at: data.completed_at ?? prev.completed_at,
            result: data.result ?? prev.result,
          };
        });
        queryClient.invalidateQueries({ queryKey: ["tasks"] });
        queryClient.invalidateQueries({ queryKey: ["queues"] });

        if (["succeeded", "failed", "dead_letter", "cancelled"].includes(data.status)) {
          // Re-fetch full task record including synthesized diagnostics & attempts
          queryClient.invalidateQueries({ queryKey: ["task", taskId] });
          es.close();
        }
      } catch (err) {
        console.error("Failed to parse SSE event data", err);
      }
    };

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [taskId, enabled, queryClient]);
}
