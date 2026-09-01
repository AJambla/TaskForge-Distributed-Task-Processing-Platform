# TaskForge Load Test Runner (PowerShell)
# Usage: .\load-tests\run-tests.ps1 [-Scenario baseline|stress|spike|endurance|all|analyze|setup|teardown]
[CmdletBinding()]
param(
    [ValidateSet('baseline', 'stress', 'spike', 'endurance', 'all', 'analyze', 'setup', 'teardown')]
    [string]$Scenario = 'all'
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$ResultsDir = Join-Path $ScriptDir 'results'
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$K6Script = Join-Path $ScriptDir 'k6\taskforge.js'
$PrometheusUrl = if ($env:PROMETHEUS_URL) { $env:PROMETHEUS_URL } else { 'http://localhost:9090' }
$ApiUrl = if ($env:API_URL) { $env:API_URL } else { 'http://localhost:8000' }

New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

function Log($msg) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
}

function Check-Prereqs {
    if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) {
        throw "k6 not found. Install: choco install k6  or  winget install Grafana.k6"
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "docker not found."
    }
}

function Setup {
    Log "Starting load test stack..."
    $workerCount = if ($env:WORKER_REPLICAS) { $env:WORKER_REPLICAS } else { 50 }
    Push-Location $ProjectDir
    try {
        docker compose -f docker-compose.yml -f docker-compose.loadtest.yml up -d --scale worker="${workerCount}"
        Log "Waiting for services to start..."
        Start-Sleep -Seconds 15
        Log "Stack is ready. Workers: ${workerCount}"
    } finally {
        Pop-Location
    }
}

function Teardown {
    Log "Tearing down load test stack..."
    Push-Location $ProjectDir
    try {
        docker compose -f docker-compose.yml -f docker-compose.loadtest.yml down --remove-orphans
        Log "Stack torn down."
    } finally {
        Pop-Location
    }
}

function Run-Scenario($name, $numUsers) {
    Log "Running ${name} scenario..."
    $resultFile = Join-Path $ResultsDir "${name}_${Timestamp}.json"
    $summaryFile = Join-Path $ResultsDir "${name}_summary_${Timestamp}.json"
    Push-Location $ProjectDir
    try {
        $env:API_URL = $ApiUrl
        $env:NUM_USERS = $numUsers
        k6 run --out json="${resultFile}" --summary-export="${summaryFile}" $K6Script 2>&1 | Out-Null
    } catch {
        Log "Warning: k6 run for ${name} encountered issues: $_"
    } finally {
        Pop-Location
    }
    Log "${name} results: ${resultFile}"
}

function Run-Baseline  { Run-Scenario 'baseline'  300 }
function Run-Stress     { Run-Scenario 'stress'     600 }
function Run-Spike      { Run-Scenario 'spike'      600 }
function Run-Endurance  { Run-Scenario 'endurance'  600 }

function Run-All {
    Setup
    Run-Baseline
    Run-Stress
    Run-Spike
    Run-Endurance
    Analyze
    Teardown
}

function Analyze {
    Log "Querying Prometheus for bottleneck analysis..."
    $analysisFile = Join-Path $ResultsDir "analysis_${Timestamp}.csv"
    @"
timestamp,metric,value
"@ | Out-File -FilePath $analysisFile -Encoding utf8

    $queries = @(
        @{ name='api_p99_latency'; expr='histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="taskforge-api"}[5m])) by (le))' },
        @{ name='api_p95_latency'; expr='histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="taskforge-api"}[5m])) by (le))' },
        @{ name='task_attempts_rate'; expr='sum(rate(task_attempts_total[5m]))' },
        @{ name='tasks_processed_rate'; expr='sum(rate(tasks_processed_total[5m]))' },
        @{ name='queue_depth'; expr='sum(rabbitmq_queue_messages_ready)' },
        @{ name='active_db_connections'; expr='sum(pg_stat_activity_count{datname="taskforge",state="active"})' },
        @{ name='worker_missed_heartbeats'; expr='sum(rate(worker_heartbeat_missed_total[5m]))' },
        @{ name='api_errors_4xx'; expr='sum(rate(http_requests_total{job="taskforge-api",status=~"4.."}[5m]))' },
        @{ name='api_errors_5xx'; expr='sum(rate(http_requests_total{job="taskforge-api",status=~"5.."}[5m]))' }
    )

    foreach ($q in $queries) {
        $body = @{ query = $q.expr } | ConvertTo-Json -Compress
        try {
            $resp = Invoke-RestMethod -Uri "${PrometheusUrl}/api/v1/query" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 5
            $val = if ($resp.data.result.Count -gt 0) { $resp.data.result[0].value[1] } else { '0' }
            "$((Get-Date -ISO8601),'$($q.name)',$val" | Out-File -FilePath $analysisFile -Append -Encoding utf8
        } catch {
            "$((Get-Date -ISO8601),'$($q.name)',0" | Out-File -FilePath $analysisFile -Append -Encoding utf8
        }
    }

    Log "Analysis saved to ${analysisFile}"
    Log ""
    Log "=== Bottleneck Analysis Summary ==="
    Log "Grafana dashboard: http://localhost:3000/d/taskforge-loadtest"
    Log "Prometheus targets: http://localhost:9090/targets"
    Log "k6 results JSON: ${ResultsDir}\*_${Timestamp}.*"
    Log ""
    Log "Key things to check:"
    Log "  1. API p99 latency — should stay < 500ms. Spike = DB bottleneck."
    Log "  2. task_attempts write rate vs DB connections — if connections saturate"
    Log "     (approaching pool_size + max_overflow = 30) before RabbitMQ builds up,"
    Log "     the bottleneck is Postgres write throughput."
    Log "  3. RabbitMQ queue depth — if queues grow unboundedly, workers are the bottleneck."
    Log "  4. Worker heartbeat misses — indicates workers are dropping under load."
}

Check-Prereqs

switch ($Scenario) {
    'baseline'   { Run-Baseline }
    'stress'     { Run-Stress }
    'spike'      { Run-Spike }
    'endurance'  { Run-Endurance }
    'all'        { Run-All }
    'analyze'    { Analyze }
    'setup'      { Setup }
    'teardown'   { Teardown }
}
