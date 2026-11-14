# backend/app/cli/seed_users.py
"""Create or update the three accounts: admin, guardian and student.

Passwords are read from the environment (never from arguments, which end up
in shell history and process listings). Running it again updates the
existing accounts instead of duplicating them (idempotent).

Usage::

    SEED_ADMIN_PASSWORD=... SEED_GUARDIAN_PASSWORD=... SEED_STUDENT_PASSWORD=... \\
    python -m app.cli.seed_users \\
        --admin-email you@example.com --admin-name Admin \\
        --guardian-email guardian@example.com --guardian-name Alex \\
        --student-username sam10 --student-name Sam
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import MIN_PASSWORD_LENGTH, hash_password
from app.auth.service import normalise_identifier
from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models.user import GuardianLink, Role, User


@dataclass(frozen=True, slots=True)
class SeedAccount:
    """One account to create or update."""

    role: Role
    identifier: str
    display_name: str
    password: str


def _password_from_env(name: str) -> str:
    value = os.environ.get(name, "")
    if len(value) < MIN_PASSWORD_LENGTH:
        sys.exit(f"{name} must be set and at least {MIN_PASSWORD_LENGTH} characters")
    return value


async def upsert_account(session: AsyncSession, account: SeedAccount) -> User:
    """Create the account, or update its name and password if it exists.

    Args:
        session: Database session (caller commits).
        account: What to create.

    Returns:
        The persisted user.
    """
    key = normalise_identifier(account.identifier)
    column = User.username if account.role is Role.STUDENT else User.email
    user = await session.scalar(select(User).where(column == key))
    password_hash = await asyncio.to_thread(hash_password, account.password)
    if user is None:
        user = User(
            role=account.role,
            username=key if account.role is Role.STUDENT else None,
            email=None if account.role is Role.STUDENT else key,
            display_name=account.display_name,
            password_hash=password_hash,
        )
        session.add(user)
    else:
        user.display_name = account.display_name
        user.password_hash = password_hash
        user.failed_login_count = 0
        user.locked_until = None
    await session.flush()
    return user


async def link_guardian(session: AsyncSession, guardian: User, student: User) -> None:
    """Link a guardian to a student; does nothing if the link exists."""
    await session.execute(
        insert(GuardianLink)
        .values(guardian_id=guardian.id, student_id=student.id)
        .on_conflict_do_nothing()
    )


async def _run(args: argparse.Namespace) -> None:
    accounts = {
        "admin": SeedAccount(
            Role.ADMIN, args.admin_email, args.admin_name, _password_from_env("SEED_ADMIN_PASSWORD")
        ),
        "guardian": SeedAccount(
            Role.GUARDIAN,
            args.guardian_email,
            args.guardian_name,
            _password_from_env("SEED_GUARDIAN_PASSWORD"),
        ),
        "student": SeedAccount(
            Role.STUDENT,
            args.student_username,
            args.student_name,
            _password_from_env("SEED_STUDENT_PASSWORD"),
        ),
    }
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            users = {name: await upsert_account(session, acc) for name, acc in accounts.items()}
            await link_guardian(session, users["guardian"], users["student"])
            await session.commit()
    finally:
        await engine.dispose()
    print("Seeded admin, guardian and student accounts.")


def main() -> None:
    """Parse arguments and seed the accounts."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-name", default="Admin")
    parser.add_argument("--guardian-email", required=True)
    parser.add_argument("--guardian-name", required=True)
    parser.add_argument("--student-username", required=True)
    parser.add_argument("--student-name", required=True)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
