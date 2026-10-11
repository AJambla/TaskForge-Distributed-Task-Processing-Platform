"""Unit tests for Organizations and Multi-Tenant collaboration (IMP-24)."""
from __future__ import annotations

import uuid
import pytest
from app.models.organization import Organization, OrganizationMembership
from app.models.task import Task
from app.models.user import User


def test_organization_and_membership_models():
    user_id = uuid.uuid4()
    org = Organization(
        id=uuid.uuid4(),
        name="Acme Corp",
        slug="acme-corp",
    )
    membership = OrganizationMembership(
        id=uuid.uuid4(),
        organization_id=org.id,
        user_id=user_id,
        role="owner",
    )
    org.memberships.append(membership)

    assert org.name == "Acme Corp"
    assert org.slug == "acme-corp"
    assert len(org.memberships) == 1
    assert org.memberships[0].role == "owner"
    assert org.memberships[0].user_id == user_id


def test_task_with_organization_scope():
    user = User(id=uuid.uuid4(), email="alice@acme.com", role="user")
    org = Organization(id=uuid.uuid4(), name="Engineering", slug="engineering")

    task = Task(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=org.id,
        task_type="email_send",
        payload={"to": "dev@acme.com"},
        status="queued",
    )

    assert task.org_id == org.id
    assert task.user_id == user.id
    assert task.task_type == "email_send"
