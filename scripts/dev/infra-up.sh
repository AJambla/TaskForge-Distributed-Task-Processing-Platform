#!/usr/bin/env bash
# Start Docker infra + observability only (postgres:5433, redis, rabbitmq, prometheus, grafana, postgres_exporter, mailpit).
# api/worker/scheduler are gated behind the "app" profile and stay bare-metal.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT_DIR"
docker compose up -d
echo
echo "Postgres   -> localhost:5433   (native Postgres 18 holds :5432)"
echo "Redis      -> localhost:6379"
echo "RabbitMQ   -> localhost:5672  | mgmt UI http://localhost:15672 (taskforge/taskforge_dev)"
echo "Prometheus -> http://localhost:9090"
echo "Grafana    -> http://localhost:3000 (admin/admin)"
echo "Mailpit    -> SMTP localhost:1025   | web http://localhost:8025"
