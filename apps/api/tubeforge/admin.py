"""``tubeforge-admin``: one-time setup commands run by tubeforge.ps1 (OAUTH_SECURITY §2, §5).

  tubeforge-admin init-keys                       create the master key in Credential Manager
  tubeforge-admin create-owner --email E --name N prompts for the password (twice, hidden)
  tubeforge-admin has-owner                       exit code 0 if an owner exists, 1 otherwise
  tubeforge-admin reset-password --email E         new password (prompted); unlocks; signs out everywhere

Non-interactive (CI): the password can come from TUBEFORGE_OWNER_PASSWORD.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.audit import SYSTEM, record
from tubeforge.auth import passwords
from tubeforge.config import get_settings
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Role, User, UserRole
from tubeforge.db.session import get_engine
from tubeforge.secrets import SecretBox, default_store

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _owner_exists(db: Session) -> bool:
    return (
        db.scalar(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == "OWNER", User.deleted_at.is_(None))
            .limit(1)
        )
        is not None
    )


def init_keys() -> int:
    box = SecretBox(default_store(get_settings().env))
    created = box.ensure_master_key()
    print("Master key created in Windows Credential Manager." if created else "Master key already present.")
    return 0


def _read_password(email: str, name: str) -> str:
    env = os.environ.get("TUBEFORGE_OWNER_PASSWORD")
    if env:
        problems = passwords.password_problems(env, user_inputs=[email, name])
        if problems:
            raise SystemExit("TUBEFORGE_OWNER_PASSWORD rejected: " + " ".join(problems))
        return env
    print("Choose the owner password: at least 12 characters, hard to guess. Typing is hidden.")
    while True:
        first = getpass.getpass("Password: ")
        problems = passwords.password_problems(first, user_inputs=[email, name])
        if problems:
            print("Not accepted: " + " ".join(problems))
            continue
        if getpass.getpass("Repeat password: ") != first:
            print("The two passwords differ. Try again.")
            continue
        return first


def create_owner(email: str, name: str) -> int:
    if not EMAIL_RE.match(email):
        print("That e-mail address does not look valid.", file=sys.stderr)
        return 2
    engine = get_engine(get_settings().database_url)
    with Session(engine) as db:
        if _owner_exists(db):
            print("An owner account already exists. Nothing changed.")
            return 0
        password = _read_password(email, name)
        owner_role = db.scalar(select(Role).where(Role.name == "OWNER"))
        if owner_role is None:
            print("Roles are missing: run 'tubeforge-db upgrade' first.", file=sys.stderr)
            return 2
        user = User(
            id=uuid7(),
            email=email,
            display_name=name.strip() or "Owner",
            password_hash=passwords.hash_password(password),
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=owner_role.id, channel_id=None))
        record(
            db,
            actor=SYSTEM,
            action="user.create_owner",
            entity_type="user",
            entity_id=str(user.id),
            details={"email": email},
        )
        db.commit()
    print(f"Owner account created for {email}. Sign in at http://127.0.0.1:{get_settings().port}")
    return 0


def reset_password(email: str) -> int:
    from datetime import UTC, datetime

    from sqlalchemy import update

    from tubeforge.audit import security_event
    from tubeforge.db.models import Session as SessionRow

    with Session(get_engine(get_settings().database_url)) as db:
        user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
        if user is None:
            print("No account with that e-mail address.", file=sys.stderr)
            return 2
        password = _read_password(email, user.display_name)
        now = datetime.now(UTC)
        user.password_hash = passwords.hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        db.execute(
            update(SessionRow)
            .where(SessionRow.user_id == user.id, SessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        security_event(db, "PASSWORD_RESET_LOCAL", "WARNING", user_id=user.id)
        record(db, actor=SYSTEM, action="user.password_reset", entity_type="user", entity_id=str(user.id))
        db.commit()
    print("Password changed. All sessions were signed out; sign in again with the new password.")
    return 0


def has_owner() -> int:
    with Session(get_engine(get_settings().database_url)) as db:
        return 0 if _owner_exists(db) else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tubeforge-admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-keys")
    owner = sub.add_parser("create-owner")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", default="Owner")
    sub.add_parser("has-owner")
    reset = sub.add_parser("reset-password")
    reset.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "init-keys":
        sys.exit(init_keys())
    if args.cmd == "create-owner":
        sys.exit(create_owner(args.email, args.name))
    if args.cmd == "reset-password":
        sys.exit(reset_password(args.email))
    sys.exit(has_owner())
