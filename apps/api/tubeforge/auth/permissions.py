"""Permission codes and role grants (OAUTH_SECURITY §3, BACKEND_SPECIFICATION §4 "Perm").

The seed migration (0003) stores a frozen copy of these lists; tests assert they match.
"""

from __future__ import annotations

from typing import Final

PERMISSIONS: Final[dict[str, str]] = {
    "dashboard.view": "View dashboards and search",
    "channel.view": "View channels",
    "channel.manage": "Create and edit channels, onboarding",
    "channel.mode": "Change operating mode and Private-only mode (owner)",
    "oauth.manage": "Connect or disconnect YouTube (OAuth)",
    "strategy.view": "View channel blueprints",
    "strategy.manage": "Edit and approve blueprints",
    "research.view": "View research, niches, trends",
    "research.run": "Run discovery and trend scans",
    "research.lookup": "Look up one public channel or video",
    "content.view": "View ideas, projects, scripts, storyboards",
    "content.edit": "Edit scripts, storyboards, timelines, metadata",
    "content.approve": "Approve research, script and cut gates",
    "project.cancel": "Cancel a project",
    "asset.view": "View assets",
    "asset.edit": "Upload assets, set rights",
    "stock.search": "Search free stock providers",
    "stock.import": "Import stock media",
    "stock.purchase": "Buy paid stock (owner)",
    "voice.view": "View voice configuration",
    "voice.profile": "Manage own voice profiles (owner)",
    "render.run": "Start, cancel and retry renders",
    "upload.view": "View uploads and schedule",
    "upload.execute": "Run uploads",
    "publish.decide": "Approve publish, privacy, made-for-kids (owner)",
    "approval.view": "View approvals",
    "audit.view": "View audit reports",
    "audit.override": "Override audits (owner)",
    "analytics.view": "View analytics",
    "comments.moderate": "Moderate comments",
    "agents.view": "View agents and runs",
    "agents.manage": "Configure agents",
    "providers.view": "View providers and usage",
    "providers.manage": "Enable providers, set limits and credentials",
    "providers.paid": "Activate paid providers, budgets (owner)",
    "emergency.activate": "Press Emergency Stop",
    "emergency.clear": "Clear Emergency Stop (owner)",
    "publishing.control": "Publishing kill switch",
    "controls.manage": "Kill switches",
    "settings.manage": "Settings, users, roles, backups",
    "security.view": "Audit log, security events, posture (owner)",
}

_VIEW = {
    "dashboard.view",
    "channel.view",
    "strategy.view",
    "research.view",
    "content.view",
    "asset.view",
    "upload.view",
    "approval.view",
    "audit.view",
    "analytics.view",
    "agents.view",
    "providers.view",
    "voice.view",
}

ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "OWNER": frozenset(PERMISSIONS),
    "EDITOR": frozenset(
        _VIEW
        | {
            "content.edit",
            "asset.edit",
            "research.run",
            "research.lookup",
            "stock.search",
            "stock.import",
            "render.run",
            "emergency.activate",
        }
    ),
    # "Approve gates (if delegated)" is granted per user later, not by default.
    "REVIEWER": frozenset(_VIEW | {"emergency.activate"}),
    "VIEWER": frozenset(_VIEW),
}

ROLE_DESCRIPTIONS: Final[dict[str, str]] = {
    "OWNER": "Owner: all permissions",
    "EDITOR": "Edits content; cannot approve or publish",
    "REVIEWER": "Reviews and comments; may be delegated gate approvals",
    "VIEWER": "Read-only",
}
