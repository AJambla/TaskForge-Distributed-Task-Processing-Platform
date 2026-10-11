import http from 'k6/http';
import { check, sleep } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

const API_URL = __ENV.API_URL || 'http://localhost:8000';
const SCENARIO = __ENV.SCENARIO || 'baseline';

const scenarios = {
  baseline: {
    executor: 'ramping-vus',
    startVUs: 1,
    stages: [
      { duration: '30s', target: 10 },
      { duration: '1m', target: 10 },
      { duration: '30s', target: 0 },
    ],
  },
  stress: {
    executor: 'ramping-vus',
    startVUs: 1,
    stages: [
      { duration: '1m', target: 50 },
      { duration: '2m', target: 50 },
      { duration: '30s', target: 0 },
    ],
  },
  spike: {
    executor: 'ramping-vus',
    startVUs: 1,
    stages: [
      { duration: '30s', target: 10 },
      { duration: '30s', target: 100 },
      { duration: '1m', target: 100 },
      { duration: '30s', target: 10 },
      { duration: '30s', target: 0 },
    ],
  },
  endurance: {
    executor: 'constant-vus',
    vus: 30,
    duration: '5m',
  },
};

export const options = {
  scenarios: {
    default: scenarios[SCENARIO] || scenarios.baseline,
  },
  thresholds: {
    http_req_duration: ['p(95)<1000', 'p(99)<2000'],
    http_req_failed: ['rate<0.05'],
  },
};

export function setup() {
  const users = [];
  const numUsers = parseInt(__ENV.NUM_USERS || '10', 10);
  const password = 'TestUserPassword123!';

  for (let i = 0; i < Math.min(numUsers, 50); i++) {
    const email = `loadtest_${Date.now()}_${i}_${Math.floor(Math.random() * 10000)}@example.com`;
    const regPayload = JSON.stringify({ email, password });
    const regRes = http.post(`${API_URL}/api/v1/auth/register`, regPayload, {
      headers: { 'Content-Type': 'application/json' },
    });

    if (regRes.status === 201 || regRes.status === 200) {
      const loginPayload = JSON.stringify({ email, password });
      const loginRes = http.post(`${API_URL}/api/v1/auth/login`, loginPayload, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (loginRes.status === 200) {
        const body = JSON.parse(loginRes.body);
        users.push({ token: body.access_token, email });
      }
    }
  }

  return { users };
}

export default function (data) {
  const users = data.users || [];
  let authHeader = {};
  if (users.length > 0) {
    const user = users[__VU % users.length];
    authHeader = { Authorization: `Bearer ${user.token}` };
  }

  const taskTypes = ['email_send', 'image_resize', 'webhook_delivery'];
  const taskType = taskTypes[Math.floor(Math.random() * taskTypes.length)];

  let payload = {};
  if (taskType === 'email_send') {
    payload = {
      task_type: 'email_send',
      payload: {
        to: 'recipient@example.com',
        subject: 'Load test email',
        body: 'TaskForge load testing payload content',
      },
    };
  } else if (taskType === 'image_resize') {
    payload = {
      task_type: 'image_resize',
      payload: {
        source_url: 'https://via.placeholder.com/300',
        width: 150,
        height: 150,
      },
    };
  } else {
    payload = {
      task_type: 'webhook_delivery',
      payload: {
        url: 'https://httpbin.org/post',
        method: 'POST',
        headers: { 'X-Source': 'TaskForge-LoadTest' },
        body: { test: true },
      },
    };
  }

  const res = http.post(`${API_URL}/api/v1/tasks`, JSON.stringify(payload), {
    headers: Object.assign(
      {
        'Content-Type': 'application/json',
        'Idempotency-Key': uuidv4(),
      },
      authHeader
    ),
  });

  check(res, {
    'task submission status is 201 or 429': (r) => r.status === 201 || r.status === 429,
  });

  sleep(1);
}
