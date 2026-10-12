/**
 * TaskForge k6 Load Generation Script (Phase 6.1)
 *
 * Simulates high-throughput distributed task ingestion across priority tiers
 * (high, normal, low) to measure:
 * - Ingestion throughput (requests/sec)
 * - HTTP submission latency (p50, p95, p99)
 * - Adaptive backpressure shedding rate (HTTP 429)
 * - Error rate & anti-starvation distribution
 *
 * Usage:
 *   k6 run scripts/loadtest/taskforge_load.js
 *   k6 run -e PROFILE=smoke scripts/loadtest/taskforge_load.js
 *   k6 run -e PROFILE=burst -e BASE_URL=http://localhost:8000 scripts/loadtest/taskforge_load.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// --- Custom Telemetry Metrics ---
export const tasksSubmitted = new Counter('tf_tasks_submitted_total');
export const tasksAccepted = new Counter('tf_tasks_accepted_201_total');
export const backpressure429 = new Counter('tf_backpressure_429_total');
export const backpressureRate = new Rate('tf_backpressure_ratio');
export const submissionErrorRate = new Rate('tf_submission_error_ratio');
export const submitLatencyMs = new Trend('tf_submit_duration_ms', true);

// --- Environment Configuration ---
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const DEMO_EMAIL = __ENV.DEMO_EMAIL || 'demo@taskforge.dev';
const DEMO_PASSWORD = __ENV.DEMO_PASSWORD || 'TaskForge123!';
const API_KEY = __ENV.API_KEY || '';
const PROFILE = __ENV.PROFILE || 'standard';

// --- Staged Scenario Profiles ---
const scenarioProfiles = {
  smoke: {
    executor: 'constant-vus',
    vus: 5,
    duration: '10s',
  },
  standard: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '20s', target: 30 },   // Stage 1: Ramp-up
      { duration: '40s', target: 50 },   // Stage 2: Sustained load
      { duration: '20s', target: 150 },  // Stage 3: Burst surge
      { duration: '20s', target: 300 },  // Stage 4: Overload & backpressure test
      { duration: '20s', target: 0 },    // Stage 5: Recovery & cooldown
    ],
  },
  burst: {
    executor: 'ramping-vus',
    startVUs: 20,
    stages: [
      { duration: '10s', target: 200 },  // Immediate aggressive surge
      { duration: '30s', target: 200 },
      { duration: '10s', target: 0 },
    ],
  },
  overload: {
    executor: 'ramping-arrival-rate',
    startRate: 100,
    timeUnit: '1s',
    preAllocatedVUs: 200,
    maxVUs: 1000,
    stages: [
      { duration: '10s', target: 500 },  // 500 req/s
      { duration: '20s', target: 2000 }, // 2000 req/s to force queue saturation & 429s
      { duration: '10s', target: 0 },
    ],
  },
};

export const options = {
  scenarios: {
    load_test: scenarioProfiles[PROFILE] || scenarioProfiles.standard,
  },
  thresholds: {
    tf_submission_error_ratio: ['rate<0.05'], // Max 5% unexpected errors (excluding 429 backpressure)
    http_req_duration: ['p(95)<500'],        // 95% of API requests complete under 500ms
  },
};

/**
 * Setup hook: executes once before VUs start.
 * Obtains authentication token via login endpoint if API_KEY is not set.
 */
export function setup() {
  if (API_KEY) {
    return { token: API_KEY };
  }

  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  if (loginRes.status === 200) {
    const data = loginRes.json();
    return { token: data.access_token };
  }

  // Fallback: attempt registration if user does not exist
  const regRes = http.post(
    `${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  if (regRes.status === 201) {
    const retryLogin = http.post(
      `${BASE_URL}/api/v1/auth/login`,
      JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
      { headers: { 'Content-Type': 'application/json' } }
    );
    if (retryLogin.status === 200) {
      return { token: retryLogin.json().access_token };
    }
  }

  console.warn(`Auth setup failed (status ${loginRes.status}). Submissions may fail if auth is enforced.`);
  return { token: '' };
}

/**
 * Helper to generate pseudo-random UUID v4 for idempotency keys.
 */
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Main VU iteration: submits tasks to TaskForge API gateway.
 */
export default function (data) {
  // Priority distribution: 60% high (8), 30% normal (5), 10% low (1)
  const rand = Math.random();
  let priority = 5;
  let priorityTier = 'normal';
  if (rand < 0.6) {
    priority = 8;
    priorityTier = 'high';
  } else if (rand > 0.9) {
    priority = 1;
    priorityTier = 'low';
  }

  const taskType = Math.random() < 0.5 ? 'email_send' : 'webhook_delivery';
  const payload =
    taskType === 'email_send'
      ? { recipient: `bench_${__VU}_${__ITER}@example.com`, subject: `Benchmark Task ${priorityTier}`, body: 'k6 load task' }
      : { target_url: 'https://httpbin.org/post', event: 'benchmark.event', priority: priorityTier };

  const requestBody = JSON.stringify({
    task_type: taskType,
    priority: priority,
    payload: payload,
    timeout_seconds: 30,
    max_retries: 3,
  });

  const headers = {
    'Content-Type': 'application/json',
    'Idempotency-Key': generateUUID(),
  };

  if (data && data.token) {
    headers['Authorization'] = `Bearer ${data.token}`;
  }

  const startMs = Date.now();
  const res = http.post(`${BASE_URL}/api/v1/tasks`, requestBody, { headers: headers });
  const latency = Date.now() - startMs;

  submitLatencyMs.add(latency);
  tasksSubmitted.add(1);

  if (res.status === 201) {
    tasksAccepted.add(1);
    backpressureRate.add(0);
    submissionErrorRate.add(0);
    check(res, {
      'status is 201': (r) => r.status === 201,
      'has task id': (r) => {
        const body = r.json();
        return body && body.id !== undefined;
      },
    });
  } else if (res.status === 429) {
    // Backpressure shedding mode
    backpressure429.add(1);
    backpressureRate.add(1);
    submissionErrorRate.add(0); // 429 is deliberate backpressure, not a server crash
    check(res, {
      'backpressure has Retry-After header': (r) => r.headers['Retry-After'] !== undefined,
    });
    // Back off slightly on 429
    sleep(0.05);
  } else {
    submissionErrorRate.add(1);
    backpressureRate.add(0);
    console.error(`Unexpected HTTP ${res.status}: ${res.body}`);
  }

  // Small pacing interval between iterations
  sleep(0.01);
}
