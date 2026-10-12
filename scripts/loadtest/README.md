# TaskForge k6 Load Generation

This directory contains the k6 load testing suite for **TaskForge** (Phase 6.1).

It generates realistic, high-throughput distributed task ingestion workloads across priority tiers (`high`, `normal`, `low`) to validate:
1. **Submission Throughput**: Request ingestion rate at the FastAPI gateway.
2. **Gateway Latency**: Sub-millisecond and p95/p99 request response times.
3. **Adaptive Backpressure Shedding**: Deterministic HTTP 429 shedding when Redis-cached queue depth exceeds `backpressure_critical_depth`.
4. **Anti-Starvation Fairness**: 60% high / 30% normal / 10% low weighted traffic generation.

---

## Prerequisites

Install [k6](https://k6.io/docs/get-started/installation/):

- **Windows (winget)**: `winget install k6 --source winget`
- **Windows (Chocolatey)**: `choco install k6`
- **macOS (Homebrew)**: `brew install k6`
- **Linux (Debian/Ubuntu)**:
  ```bash
  sudo gpg -k
  sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
  echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
  sudo apt-get update && sudo apt-get install k6
  ```
- **Docker**:
  ```bash
  docker run --network=host -i grafana/k6 run - < scripts/loadtest/taskforge_load.js
  ```

---

## Execution Profiles

The script supports 4 profiles configured via the `PROFILE` environment variable:

| Profile | Description | Target Virtual Users | Duration |
|---|---|---|---|
| `smoke` | Quick sanity test for API connectivity & auth | 5 VUs | 10 seconds |
| `standard` | 5-stage benchmark: Ramp-up → Sustained → Burst → Overload → Cooldown | Up to 300 VUs | 2 minutes |
| `burst` | Immediate high-priority surge testing anti-starvation fair queueing | 200 VUs | 50 seconds |
| `overload` | Rate-based arrival surge to trigger adaptive backpressure (HTTP 429) | Up to 2,000 req/s | 40 seconds |

---

## Running Load Tests

### 1. Smoke Test (Sanity Check)
```bash
k6 run -e PROFILE=smoke scripts/loadtest/taskforge_load.js
```

### 2. Standard Benchmark (Ramp-up + Sustained + Burst)
```bash
k6 run scripts/loadtest/taskforge_load.js
```

### 3. Backpressure Overload Test
```bash
k6 run -e PROFILE=overload scripts/loadtest/taskforge_load.js
```

### 4. Custom API Target & API Key
```bash
k6 run -e BASE_URL=http://localhost:8000 -e API_KEY=tf_live_your_key_here scripts/loadtest/taskforge_load.js
```

---

## Telemetry Metrics Exported

In addition to standard k6 HTTP metrics (`http_req_duration`, `http_reqs`), the test collects:
- `tf_tasks_submitted_total`: Total task creation attempts initiated.
- `tf_tasks_accepted_201_total`: Tasks successfully admitted into PostgreSQL & outbox.
- `tf_backpressure_429_total`: Tasks shed due to queue depth saturation.
- `tf_backpressure_ratio`: Percentage of requests rejected by backpressure admission control.
- `tf_submit_duration_ms`: End-to-end task submission latency distribution (p50, p95, p99).
