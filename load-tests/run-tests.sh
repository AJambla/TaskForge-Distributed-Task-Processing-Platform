#!/usr/bin/env bash
# TaskForge Load Test Runner
# Usage: ./load-tests/run-tests.sh [scenario]
#   scenario: baseline | stress | spike | endurance | all | analyze
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
K6_SCRIPT="${SCRIPT_DIR}/k6/taskforge.js"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
API_URL="${API_URL:-http://localhost:8000}"

mkdir -p "${RESULTS_DIR}"

# ─── Helpers ──────────────────────────────────────────────────────────────────

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

usage() {
  echo "Usage: $0 [baseline|stress|spike|endurance|all|analyze|setup|teardown]"
  echo ""
  echo "Scenarios:"
  echo "  baseline    - 10 VUs, 10 tasks/sec, 5 min"
  echo "  stress      - 50 VUs, ~100 tasks/sec, 10 min"
  echo "  spike       - ramp 10->200 VUs, hold 5min, ramp down"
  echo "  endurance   - 30 VUs, ~50 tasks/sec, 30 min"
  echo "  all         - run all scenarios sequentially"
  echo "  analyze     - query Prometheus for test results"
  echo "  setup       - start the load test stack"
  echo "  teardown    - stop the load test stack"
  exit 1
}

check_prereqs() {
  if ! command -v k6 &>/dev/null; then
    log "ERROR: k6 not found. Install: brew install k6  or  choco install k6"
    exit 1
  fi
  if ! command -v docker &>/dev/null; then
    log "ERROR: docker not found."
    exit 1
  fi
}

# ─── Stack management ─────────────────────────────────────────────────────────

setup() {
  log "Starting load test stack..."
  cd "${PROJECT_DIR}"
  docker compose -f docker-compose.yml -f docker-compose.loadtest.yml up -d --scale worker="${WORKER_REPLICAS:-50}"
  log "Waiting for services to start..."
  sleep 15
  log "Stack is ready. Workers: ${WORKER_REPLICAS:-50}"
}

teardown() {
  log "Tearing down load test stack..."
  cd "${PROJECT_DIR}"
  docker compose -f docker-compose.yml -f docker-compose.loadtest.yml down --remove-orphans
  log "Stack torn down."
}

# ─── Run scenarios ────────────────────────────────────────────────────────────

run_baseline() {
  log "Running BASELINE scenario (10 VUs, 5 min)..."
  local result_file="${RESULTS_DIR}/baseline_${TIMESTAMP}.json"
  local summary_file="${RESULTS_DIR}/baseline_summary_${TIMESTAMP}.json"
  cd "${PROJECT_DIR}"
  API_URL="${API_URL}" NUM_USERS=300 k6 run --out json="${result_file}" \
    --summary-export="${summary_file}" \
    "${K6_SCRIPT}" 2>&1 || true
  log "Baseline results: ${result_file}"
}

run_stress() {
  log "Running STRESS scenario (50 VUs, 10 min)..."
  local result_file="${RESULTS_DIR}/stress_${TIMESTAMP}.json"
  local summary_file="${RESULTS_DIR}/stress_summary_${TIMESTAMP}.json"
  cd "${PROJECT_DIR}"
  API_URL="${API_URL}" NUM_USERS=600 k6 run --out json="${result_file}" \
    --summary-export="${summary_file}" \
    "${K6_SCRIPT}" 2>&1 || true
  log "Stress results: ${result_file}"
}

run_spike() {
  log "Running SPIKE scenario (ramp 10->200 VUs, 9 min)..."
  local result_file="${RESULTS_DIR}/spike_${TIMESTAMP}.json"
  local summary_file="${RESULTS_DIR}/spike_summary_${TIMESTAMP}.json"
  cd "${PROJECT_DIR}"
  API_URL="${API_URL}" NUM_USERS=600 k6 run --out json="${result_file}" \
    --summary-export="${summary_file}" \
    "${K6_SCRIPT}" 2>&1 || true
  log "Spike results: ${result_file}"
}

run_endurance() {
  log "Running ENDURANCE scenario (30 VUs, 30 min)..."
  local result_file="${RESULTS_DIR}/endurance_${TIMESTAMP}.json"
  local summary_file="${RESULTS_DIR}/endurance_summary_${TIMESTAMP}.json"
  cd "${PROJECT_DIR}"
  API_URL="${API_URL}" NUM_USERS=600 k6 run --out json="${result_file}" \
    --summary-export="${summary_file}" \
    "${K6_SCRIPT}" 2>&1 || true
  log "Endurance results: ${result_file}"
}

run_all() {
  setup
  run_baseline
  run_stress
  run_spike
  run_endurance
  analyze
  teardown
}

# ─── Analysis ─────────────────────────────────────────────────────────────────

analyze() {
  log "Querying Prometheus for bottleneck analysis..."
  local analysis_file="${RESULTS_DIR}/analysis_${TIMESTAMP}.csv"

  echo "timestamp,metric,value" > "${analysis_file}"

  local queries=(
    "taskforge_api_http_requests_duration_seconds_p99:histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job=\"taskforge-api\"}[5m])) by (le))"
    "taskforge_api_http_requests_duration_seconds_p95:histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job=\"taskforge-api\"}[5m])) by (le))"
    "taskforge_task_attempts_rate:sum(rate(task_attempts_total[5m]))"
    "taskforge_tasks_processed_rate:sum(rate(tasks_processed_total[5m]))"
    "taskforge_queue_depth:sum(rabbitmq_queue_messages_ready)"
    "taskforge_active_connections:sum(pg_stat_activity_count{datname=\"taskforge\",state=\"active\"})"
    "taskforge_worker_missed_heartbeats:sum(rate(worker_heartbeat_missed_total[5m]))"
    "taskforge_api_errors_4xx:sum(rate(http_requests_total{job=\"taskforge-api\",status=~\"4..\"}[5m]))"
    "taskforge_api_errors_5xx:sum(rate(http_requests_total{job=\"taskforge-api\",status=~\"5..\"}[5m]))"
  )

  for q in "${queries[@]}"; do
    local name="${q%%:*}"
    local expr="${q#*:}"
    local val
    val=$(curl -s "${PROMETHEUS_URL}/api/v1/query" \
      --data-urlencode "query=${expr}" 2>/dev/null \
      | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data['data']['result']:
    print(data['data']['result'][0]['value'][1])
else:
    print('0')
" 2>/dev/null || echo "0")
    echo "$(date -Iseconds),${name},${val}" >> "${analysis_file}"
  done

  log "Analysis saved to ${analysis_file}"
  log ""
  log "=== Bottleneck Analysis Summary ==="
  log "Grafana dashboard: http://localhost:3000/d/taskforge-loadtest"
  log "Prometheus targets: http://localhost:9090/targets"
  log "k6 results JSON: ${RESULTS_DIR}/*_${TIMESTAMP}.*"
  log ""
  log "Key things to check:"
  log "  1. API p99 latency — should stay < 500ms. Spike = DB bottleneck."
  log "  2. task_attempts write rate vs DB connections — if connections saturate"
  log "     (approaching pool_size + max_overflow = 30) before RabbitMQ builds up,"
  log "     the bottleneck is Postgres write throughput."
  log "  3. RabbitMQ queue depth — if queues grow unboundedly, workers are the bottleneck."
  log "  4. Worker heartbeat misses — indicates workers are dropping under load."
}

# ─── Main ─────────────────────────────────────────────────────────────────────

check_prereqs

case "${1:-all}" in
  baseline)    run_baseline ;;
  stress)      run_stress ;;
  spike)       run_spike ;;
  endurance)   run_endurance ;;
  all)         run_all ;;
  analyze)     analyze ;;
  setup)       setup ;;
  teardown)    teardown ;;
  *)           usage ;;
esac
