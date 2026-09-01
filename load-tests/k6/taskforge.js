import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Counter } from 'k6/metrics';

// ─── Custom metrics ───────────────────────────────────────────────────────────
const taskSubmitDuration = new Trend('task_submit_duration', true);
const authLatency = new Trend('auth_latency', true);
const tasksCreated = new Counter('tasks_created');
const tasksFailed = new Counter('tasks_failed');

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const NUM_USERS = parseInt(__ENV.NUM_USERS || '300', 10);
const taskTypes = ['email_send', 'image_resize', 'webhook_delivery'];

// ─── Setup: register and login all users once before VUs start ────────────────
export function setup() {
  const users = [];
  for (let i = 0; i < NUM_USERS; i++) {
    users.push({
      email: `loadtest_${i}@taskforge.dev`,
      password: 'LoadTest123!',
    });
  }

  // Batch register
  group('register_users', function () {
    for (const user of users) {
      const payload = JSON.stringify({
        email: user.email,
        password: user.password,
      });
      const res = http.post(`${BASE_URL}/api/v1/auth/register`, payload, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.status !== 201) {
        // User may already exist from a previous run
        check(res, { 'register or exists': (r) => r.status === 201 || r.status === 409 });
      }
      sleep(0.01);
    }
  });

  // Batch login to collect tokens
  const tokens = new Array(NUM_USERS).fill(null);
  group('login_users', function () {
    for (let i = 0; i < NUM_USERS; i++) {
      const payload = JSON.stringify({
        email: users[i].email,
        password: users[i].password,
      });
      const start = Date.now();
      const res = http.post(`${BASE_URL}/api/v1/auth/login`, payload, {
        headers: { 'Content-Type': 'application/json' },
      });
      authLatency.add(Date.now() - start);
      if (res.status === 200) {
        tokens[i] = res.json().access_token;
      }
      sleep(0.005);
    }
  });

  const failedLogins = tokens.filter((t) => t === null).length;
  if (failedLogins > 0) {
    console.error(`WARNING: ${failedLogins}/${NUM_USERS} logins failed`);
  }

  return { tokens, numUsers: NUM_USERS };
}

// ─── Default VU function ──────────────────────────────────────────────────────
export default function (data) {
  const { tokens, numUsers } = data;
  const userIndex = __VU % numUsers;
  const token = tokens[userIndex];

  if (!token) {
    console.error(`VU ${__VU}: no token for user ${userIndex}, skipping`);
    return;
  }

  const taskType = taskTypes[__ITER % 3];
  const idx = __ITER;

  let payload;
  if (taskType === 'email_send') {
    payload = JSON.stringify({
      task_type: 'email_send',
      payload: {
        to: `user${userIndex}@example.com`,
        subject: `Load test email ${idx}`,
        body: 'This is a load test email body.',
      },
      priority: Math.floor(Math.random() * 10) - 5,
      max_attempts: 3,
    });
  } else if (taskType === 'image_resize') {
    payload = JSON.stringify({
      task_type: 'image_resize',
      payload: {
        source_url: 'https://httpbin.org/image/png',
        width: 100 + (idx % 10) * 50,
        height: 100 + (idx % 10) * 50,
      },
      priority: Math.floor(Math.random() * 10) - 5,
      max_attempts: 3,
    });
  } else {
    payload = JSON.stringify({
      task_type: 'webhook_delivery',
      payload: {
        url: `${BASE_URL}/api/v1/healthz`,
        headers: { 'X-Test': 'loadtest' },
        body: { event: 'task_complete', iteration: idx },
      },
      priority: Math.floor(Math.random() * 10) - 5,
      max_attempts: 3,
    });
  }

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  };

  const start = Date.now();
  const res = http.post(`${BASE_URL}/api/v1/tasks`, payload, params);
  taskSubmitDuration.add(Date.now() - start);

  if (res.status === 201) {
    tasksCreated.add(1);
  } else {
    tasksFailed.add(1);
  }

  check(res, {
    'submit returns 201 or 429': (r) => r.status === 201 || r.status === 429,
  });

  // Pace: ~1 task per user per minute to stay under rate limit
  // With NUM_USERS users and target RPS, sleep = 60 / (RPS * num_users_per_vu)
  sleep(1.0);
}

// ─── k6 options ───────────────────────────────────────────────────────────────
export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-vus',
      vus: 10,
      duration: '5m',
      exec: 'default',
      tags: { test_type: 'baseline' },
    },
    stress: {
      executor: 'constant-vus',
      vus: 50,
      duration: '10m',
      exec: 'default',
      tags: { test_type: 'stress' },
    },
    spike: {
      executor: 'ramping-vus',
      startVUs: 10,
      stages: [
        { duration: '2m', target: 200 },
        { duration: '5m', target: 200 },
        { duration: '2m', target: 10 },
      ],
      exec: 'default',
      tags: { test_type: 'spike' },
    },
    endurance: {
      executor: 'constant-vus',
      vus: 30,
      duration: '30m',
      exec: 'default',
      tags: { test_type: 'endurance' },
    },
  },
  thresholds: {
    'task_submit_duration': ['p(95)<500', 'p(99)<1000'],
    'auth_latency': ['p(95)<300', 'p(99)<500'],
    'tasks_created': ['count>=0'],
    'tasks_failed{test_type:baseline}': ['count<5'],
    'tasks_failed{test_type:stress}': ['count<20'],
    'tasks_failed{test_type:spike}': ['count<50'],
    'tasks_failed{test_type:endurance}': ['count<10'],
  },
};
