#!/usr/bin/env python3
"""TaskForge development synthetic database seeder (IMP-11).

Seeds the database with test users, API keys, and diverse tasks across
all lifecycle statuses (queued, running, succeeded, failed, dead_letter).
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid

# Ensure backend directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.api_key import APIKey
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.core.security import hash_password, generate_api_key


async def seed_database(task_count: int = 50) -> dict[str, int]:
    """Seed test users, api keys, and tasks. Returns summary count dict."""
    async with AsyncSessionLocal() as db:
        # 1. Create or get admin & regular user
        result = await db.execute(select(User).where(User.email == "demo@taskforge.dev"))
        demo_user = result.scalar_one_or_none()
        if not demo_user:
            demo_user = User(
                email="demo@taskforge.dev",
                password_hash=hash_password("TaskForge123!"),
                role="user",
            )
            db.add(demo_user)
            await db.flush()

        result_admin = await db.execute(select(User).where(User.email == "admin@taskforge.dev"))
        admin_user = result_admin.scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                email="admin@taskforge.dev",
                password_hash=hash_password("AdminSecure123!"),
                role="admin",
            )
            db.add(admin_user)
            await db.flush()

        # 2. Seed API Key if none exists
        res_key = await db.execute(select(APIKey).where(APIKey.user_id == demo_user.id))
        key_record = res_key.scalar_one_or_none()
        if not key_record:
            raw_key, key_hash, prefix = generate_api_key()
            key_record = APIKey(
                user_id=demo_user.id,
                name="Local Development Key",
                key_hash=key_hash,
                key_prefix=prefix,
            )
            db.add(key_record)
            await db.flush()

        # 3. Seed sample tasks with diverse statuses
        statuses = ["queued", "running", "succeeded", "failed", "dead_letter"]
        task_types = [
            ("email_send", {"to": "customer@example.com", "subject": "Welcome to TaskForge", "body": "Hello!"}),
            ("image_resize", {"source_url": "https://images.example.com/sample.png", "width": 800, "height": 600}),
            ("webhook_delivery", {"url": "https://httpbin.org/post", "headers": {"X-Source": "Seed"}, "body": {"event": "ping"}}),
        ]

        now = datetime.now(timezone.utc)
        created_tasks = 0

        for i in range(task_count):
            status = statuses[i % len(statuses)]
            t_type, payload = task_types[i % len(task_types)]
            created_at = now - timedelta(minutes=i * 5)
            started_at = created_at + timedelta(seconds=2) if status != "queued" else None
            completed_at = started_at + timedelta(seconds=5) if status in ("succeeded", "failed", "dead_letter") else None

            task = Task(
                user_id=demo_user.id,
                task_type=t_type,
                payload=payload,
                status=status,
                priority=10 if i % 5 == 0 else 0,
                max_attempts=3,
                attempt_count=1 if status in ("running", "succeeded") else (3 if status in ("failed", "dead_letter") else 0),
                created_at=created_at,
                started_at=started_at,
                completed_at=completed_at,
                result={"status": "ok", "processed_bytes": 1024} if status == "succeeded" else None,
            )
            db.add(task)
            await db.flush()

            if status in ("succeeded", "failed", "dead_letter"):
                attempt = TaskAttempt(
                    task_id=task.id,
                    attempt_number=1,
                    outcome="success" if status == "succeeded" else "failure",
                    started_at=started_at,
                    finished_at=completed_at,
                    error_message="Simulated failure for demo" if status in ("failed", "dead_letter") else None,
                    result={"status": "ok", "processed_bytes": 1024} if status == "succeeded" else None,
                )
                db.add(attempt)

            created_tasks += 1

        await db.commit()
        return {
            "users": 2,
            "tasks": created_tasks,
        }


def main():
    print("Seeding TaskForge development database...")
    summary = asyncio.run(seed_database(task_count=30))
    print(f"Seeding completed successfully: {summary}")


if __name__ == "__main__":
    main()
