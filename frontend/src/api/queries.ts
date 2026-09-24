import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type { QueueMetrics, QueueStats, Task, TaskListResponse, Worker } from "../types";

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
