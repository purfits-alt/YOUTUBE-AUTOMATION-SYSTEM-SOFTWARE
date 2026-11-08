"""Seed data: roles, permissions, role grants (OAUTH_SECURITY §3) and the system_settings row.

IDs are deterministic (uuid5) so the seed is reproducible. The lists below are a frozen copy of
tubeforge.auth.permissions at this revision; later changes need a new migration
(tests/unit/test_permissions.py compares them).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMESPACE = uuid.UUID("6f0e3b1e-7a51-4c1e-9a3b-2f6d1c0b5e11")

PERMISSIONS: list[tuple[str, str]] = [
    ("dashboard.view", "View dashboards and search"),
    ("channel.view", "View channels"),
    ("channel.manage", "Create and edit channels, onboarding"),
    ("channel.mode", "Change operating mode and Private-only mode (owner)"),
    ("oauth.manage", "Connect or disconnect YouTube (OAuth)"),
    ("strategy.view", "View channel blueprints"),
    ("strategy.manage", "Edit and approve blueprints"),
    ("research.view", "View research, niches, trends"),
    ("research.run", "Run discovery and trend scans"),
    ("research.lookup", "Look up one public channel or video"),
    ("content.view", "View ideas, projects, scripts, storyboards"),
    ("content.edit", "Edit scripts, storyboards, timelines, metadata"),
    ("content.approve", "Approve research, script and cut gates"),
    ("project.cancel", "Cancel a project"),
    ("asset.view", "View assets"),
    ("asset.edit", "Upload assets, set rights"),
    ("stock.search", "Search free stock providers"),
    ("stock.import", "Import stock media"),
    ("stock.purchase", "Buy paid stock (owner)"),
    ("voice.view", "View voice configuration"),
    ("voice.profile", "Manage own voice profiles (owner)"),
    ("render.run", "Start, cancel and retry renders"),
    ("upload.view", "View uploads and schedule"),
    ("upload.execute", "Run uploads"),
    ("publish.decide", "Approve publish, privacy, made-for-kids (owner)"),
    ("approval.view", "View approvals"),
    ("audit.view", "View audit reports"),
    ("audit.override", "Override audits (owner)"),
    ("analytics.view", "View analytics"),
    ("comments.moderate", "Moderate comments"),
    ("agents.view", "View agents and runs"),
    ("agents.manage", "Configure agents"),
    ("providers.view", "View providers and usage"),
    ("providers.manage", "Enable providers, set limits and credentials"),
    ("providers.paid", "Activate paid providers, budgets (owner)"),
    ("emergency.activate", "Press Emergency Stop"),
    ("emergency.clear", "Clear Emergency Stop (owner)"),
    ("publishing.control", "Publishing kill switch"),
    ("controls.manage", "Kill switches"),
    ("settings.manage", "Settings, users, roles, backups"),
    ("security.view", "Audit log, security events, posture (owner)"),
]

ROLE_DESCRIPTIONS: dict[str, str] = {
    "OWNER": "Owner: all permissions",
    "EDITOR": "Edits content; cannot approve or publish",
    "REVIEWER": "Reviews and comments; may be delegated gate approvals",
    "VIEWER": "Read-only",
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "OWNER": [
        "agents.manage",
        "agents.view",
        "analytics.view",
        "approval.view",
        "asset.edit",
        "asset.view",
        "audit.override",
        "audit.view",
        "channel.manage",
        "channel.mode",
        "channel.view",
        "comments.moderate",
        "content.approve",
        "content.edit",
        "content.view",
        "controls.manage",
        "dashboard.view",
        "emergency.activate",
        "emergency.clear",
        "oauth.manage",
        "project.cancel",
        "providers.manage",
        "providers.paid",
        "providers.view",
        "publish.decide",
        "publishing.control",
        "render.run",
        "research.lookup",
        "research.run",
        "research.view",
        "security.view",
        "settings.manage",
        "stock.import",
        "stock.purchase",
        "stock.search",
        "strategy.manage",
        "strategy.view",
        "upload.execute",
        "upload.view",
        "voice.profile",
        "voice.view",
    ],
    "EDITOR": [
        "agents.view",
        "analytics.view",
        "approval.view",
        "asset.edit",
        "asset.view",
        "audit.view",
        "channel.view",
        "content.edit",
        "content.view",
        "dashboard.view",
        "emergency.activate",
        "providers.view",
        "render.run",
        "research.lookup",
        "research.run",
        "research.view",
        "stock.import",
        "stock.search",
        "strategy.view",
        "upload.view",
        "voice.view",
    ],
    "REVIEWER": [
        "agents.view",
        "analytics.view",
        "approval.view",
        "asset.view",
        "audit.view",
        "channel.view",
        "content.view",
        "dashboard.view",
        "emergency.activate",
        "providers.view",
        "research.view",
        "strategy.view",
        "upload.view",
        "voice.view",
    ],
    "VIEWER": [
        "agents.view",
        "analytics.view",
        "approval.view",
        "asset.view",
        "audit.view",
        "channel.view",
        "content.view",
        "dashboard.view",
        "providers.view",
        "research.view",
        "strategy.view",
        "upload.view",
        "voice.view",
    ],
}


def seed_id(kind: str, code: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{code}")


def upgrade() -> None:
    bind = op.get_bind()
    for code, description in PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:id, :code, :d)"),
            {"id": seed_id("permission", code), "code": code, "d": description},
        )
    for role, description in ROLE_DESCRIPTIONS.items():
        bind.execute(
            sa.text("INSERT INTO roles (id, name, description) VALUES (:id, :name, :d)"),
            {"id": seed_id("role", role), "name": role, "d": description},
        )
        for code in ROLE_PERMISSIONS[role]:
            bind.execute(
                sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
                {"r": seed_id("role", role), "p": seed_id("permission", code)},
            )
    bind.execute(sa.text("INSERT INTO system_settings (id) VALUES (1)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM system_settings"))
    bind.execute(sa.text("DELETE FROM role_permissions"))
    bind.execute(sa.text("DELETE FROM user_roles"))
    bind.execute(sa.text("DELETE FROM roles"))
    bind.execute(sa.text("DELETE FROM permissions"))
