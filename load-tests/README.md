# TaskForge Load Tests

k6-based load testing harness for validating Postgres `task_attempts` write-throughput at 50+ concurrent workers.

## Prerequisites

- **k6**: `choco install k6` (Windows) or `brew install k6` (macOS/Linux)
- **Docker**: Docker Desktop with compose v2
- **Docker Compose**: `docker compose` (not `docker-compose`)

## Quick Start

```bash
# PowerShell (Windows)
.\load-tests\run-tests.ps1 -Scenario all

# Bash (Linux/macOS)
./load-tests/run-tests.sh all
```

## Scenarios

| Scenario    | VUs     | Duration | Purpose                                      |
|-------------|---------|----------|----------------------------------------------|
| `baseline`  | 10      | 5 min    | Verify normal operation at low load          |
| `stress`    | 50      | 10 min   | Push near capacity, measure p99 latency      |
| `spike`     | 10→200  | 9 min    | Test burst handling and recovery             |
| `endurance` | 30      | 30 min   | Detect memory leaks and connection exhaustion|
| `all`       | —       | —        | Run all scenarios sequentially               |

## Directory Structure

```
load-tests/
  k6/
    taskforge.js          # k6 load test script (all scenarios)
  results/                # JSON outputs and CSV analysis (gitignored)
  run-tests.sh            # Bash runner (Linux/macOS)
  run-tests.ps1           # PowerShell runner (Windows)
  README.md               # This file
```

## How It Works

1. **Pre-registration**: The script pre-registers ~300-600 test users and logs them in before the scenario starts, avoiding the 20 req/min auth rate limit during the test.
2. **Rate-limit-aware submission**: Each user submits at most 1-2 tasks per minute to stay under the 60 req/min per-user rate limit.
3. **Worker scaling**: The `docker-compose.loadtest.yml` overlay scales the worker service to 50 replicas (configurable via `WORKER_REPLICAS` env var).
4. **Prometheus scraping**: Metrics from the API, workers, and RabbitMQ are scraped by Prometheus and visualized in Grafana.
5. **Analysis**: After each run, Prometheus is queried for key bottleneck indicators and saved to CSV.

## Running Individual Scenarios

```bash
# Run only the baseline
.\load-tests\run-tests.ps1 -Scenario baseline

# Run only stress
.\load-tests\run-tests.ps1 -Scenario stress

# Start the stack without running tests
.\load-tests\run-tests.ps1 -Scenario setup

# Tear down the stack
.\load-tests\run-tests.ps1 -Scenario teardown

# Re-query Prometheus without re-running tests
.\load-tests\run-tests.ps1 -Scenario analyze
```

## Key Metrics to Watch

### Bottleneck Indicators

| Metric                                      | What It Tells You                                           |
|---------------------------------------------|-------------------------------------------------------------|
| `http_request_duration_seconds p99`         | API latency — spikes > 500ms indicate DB saturation        |
| `task_attempts_total rate`                  | Worker write throughput — plateau = DB bottleneck           |
| `pg_stat_activity_count` (active)           | DB connections in use — hitting pool limit = saturation     |
| `rabbitmq_queue_messages_ready`             | Queue backpressure — growing = workers can't keep up        |
| `worker_heartbeat_missed_total rate`        | Worker health — non-zero = workers dropping under load      |
| `http_requests_total` 4xx/5xx rate          | Error rate — > 5% = system under stress                     |

### Interpreting Results

**Postgres `task_attempts` is the bottleneck if:**
- API p99 latency spikes sharply while RabbitMQ queue depth stays low
- Active DB connections approach the pool limit (30 = 10 base + 20 overflow)
- `task_attempts` write rate plateaus before task submission rate does

**RabbitMQ/Worker is the bottleneck if:**
- RabbitMQ queue depth grows unboundedly
- Workers show missed heartbeats
- API latency stays flat but task completion rate drops

**Redis is the bottleneck if:**
- Rate-limit counters cause high Redis latency
- API 429 errors increase significantly

## Customization

### Adjust worker count
```powershell
$env:WORKER_REPLICAS = 25
.\load-tests\run-tests.ps1 -Scenario stress
```

### Adjust API URL
```powershell
$env:API_URL = 'http://staging.example.com:8000'
.\load-tests\run-tests.ps1 -Scenario stress
```

### Change rate limits (for testing beyond defaults)
Edit `.env` or the docker-compose overlay:
```yaml
environment:
  RATE_LIMIT_TASK_SUBMISSION_PER_MINUTE: 600
```

### Run k6 with cloud export
```powershell
$env:K6_CLOUD_TOKEN = 'your-token-here'
k6 run --out cloud load-tests/k6/taskforge.js
```

## Thresholds

The k6 script defines these failure thresholds:
- `task_submit_duration` p95 < 500ms, p99 < 1000ms
- `auth_latency` p95 < 300ms, p99 < 500ms
- `task_submit_success` rate >= 95%

If any threshold is breached, k6 exits with code 1 and the scenario is marked as failed.

## Extending Test Scenarios

The k6 script uses `options.scenarios` to define test profiles. Add a new scenario by:
1. Adding a new entry in `options.scenarios` with `executor`, `vus`, `duration`, and `exec`
2. Adding a corresponding PowerShell function in `run-tests.ps1`
3. Adding a corresponding bash function in `run-tests.sh`

See `k6/taskforge.js` lines 120-175 for the existing scenario definitions.
