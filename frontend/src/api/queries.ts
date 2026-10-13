import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type {
  APIKey,
  DLQInspectionResponse,
  HandlerInfo,
  MetricsSummaryResponse,
  QueueMetrics,
  QueueStats,
  Task,
  TaskListResponse,
  Worker,
} from "../types";

export function useMetricsSummary(enabled = true) {
  return useQuery({
    queryKey: ["metrics", "summary"],
    queryFn: async () => {
      const res = await client.get<MetricsSummaryResponse>("/metrics/summary");
      return res.data;
    },
    refetchInterval: 5_000,
    enabled,
    retry: false,
  });
}

export function useRecentTasks(pageSize = 100) {
  return useQuery({
    queryKey: ["tasks", "recent", pageSize],
    queryFn: async () => {
      const res = await client.get<TaskListResponse>("/tasks", {
        params: { page: 1, page_size: pageSize, sort: "-created_at" },
      });
      return res.data.data;
    },
    refetchInterval: 15_000,
  });
}

export function useQueueStats(enabled = true) {
  return useQuery({
    queryKey: ["queues", "stats"],
    queryFn: async () => {
      const res = await client.get<QueueStats>("/queues/stats");
      return res.data;
    },
    refetchInterval: 15_000,
    enabled,
    retry: false,
  });
}

export function useQueues(enabled = true) {
  return useQuery({
    queryKey: ["queues"],
    queryFn: async () => {
      const res = await client.get<{ queues: QueueMetrics[] }>("/queues");
      return res.data.queues;
    },
    refetchInterval: 5_000,
    enabled,
    retry: false,
  });
}

export function useWorkers(enabled = true) {
  return useQuery({
    queryKey: ["workers"],
    queryFn: async () => {
      const res = await client.get<Worker[]>("/workers");
      return res.data;
    },
    refetchInterval: 5_000,
    enabled,
    retry: false,
  });
}

export function bucketTasksByHour(tasks: Task[], hours = 12): { points: number[]; labels: string[] } {
  const now = new Date();
  const buckets = new Array(hours).fill(0) as number[];
  const labels: string[] = [];
  for (let i = hours - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 3_600_000);
    labels.push(`${String(d.getHours()).padStart(2, "0")}:00`);
  }
  for (const t of tasks) {
    const age = (now.getTime() - new Date(t.created_at).getTime()) / 3_600_000;
    if (age >= 0 && age < hours) {
      buckets[hours - 1 - Math.floor(age)] += 1;
    }
  }
  return { points: buckets, labels };
}

export function useApiKeys(enabled = true) {
  return useQuery({
    queryKey: ["api-keys"],
    queryFn: async () => {
      const res = await client.get<APIKey[]>("/api-keys");
      return res.data;
    },
    enabled,
  });
}

export function useHandlers(enabled = true) {
  return useQuery({
    queryKey: ["handlers"],
    queryFn: async () => {
      const res = await client.get<{ handlers: string[] | HandlerInfo[] }>("/handlers");
      return res.data.handlers;
    },
    staleTime: 60_000,
    enabled,
  });
}

export function useDLQInspection(enabled = true) {
  return useQuery({
    queryKey: ["queues", "dlq"],
    queryFn: async () => {
      const res = await client.get<DLQInspectionResponse>("/queues/dlq");
      return res.data;
    },
    refetchInterval: 10_000,
    enabled,
  });
}

