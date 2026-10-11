"""Unit tests for PgBouncer configuration and architecture (IMP-15)."""
from pathlib import Path


def test_docker_compose_includes_pgbouncer():
    compose_path = Path(__file__).resolve().parent.parent.parent / "docker-compose.yml"
    assert compose_path.exists()
    content = compose_path.read_text(encoding="utf-8")

    assert "pgbouncer:" in content
    assert "POOL_MODE: transaction" in content
    assert "MAX_CLIENT_CONN:" in content
    assert "6432:6432" in content
