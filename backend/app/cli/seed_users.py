# backend/app/cli/seed_users.py
"""Create or update the three accounts: admin, guardian and student.

Passwords are never taken as arguments (those end up in shell history and
process listings). Each one is read from its environment variable
(``SEED_ADMIN_PASSWORD``, ``SEED_GUARDIAN_PASSWORD``, ``SEED_STUDENT_PASSWORD``)
if set, otherwise asked for at a hidden prompt. Running it again updates the
existing accounts instead of duplicating them (idempotent).

Usage::

    python -m app.cli.seed_users \\
        --admin-email you@example.com --admin-name Admin \\
        --guardian-email guardian@example.com --guardian-name Alex \\
        --student-username sam10 --student-name Sam
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Callable, Mapping
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


MAX_PROMPT_ATTEMPTS = 3


class PasswordError(Exception):
    """A usable password couldn't be obtained."""


def resolve_password(
    env_name: str,
    label: str,
    *,
    env: Mapping[str, str],
    prompt: Callable[[str], str] | None,
) -> str:
    """Return a password from the environment, or ask for it at a hidden prompt.

    Args:
        env_name: Environment variable to read first.
        label: Who the password is for, shown in the prompt (e.g. "Admin").
        env: The environment to read from.
        prompt: Hidden-input function (``getpass.getpass``), or ``None`` when
            there's no terminal to ask on.

    Returns:
        A password of at least ``MIN_PASSWORD_LENGTH`` characters.

    Raises:
        PasswordError: If the environment value is too short, there's no
            terminal to prompt on, or no valid matching password was entered
            within ``MAX_PROMPT_ATTEMPTS`` tries.
    """
    from_env = env.get(env_name, "")
    if from_env:
        if len(from_env) < MIN_PASSWORD_LENGTH:
            raise PasswordError(f"{env_name} must be at least {MIN_PASSWORD_LENGTH} characters")
        return from_env
    if prompt is None:
        raise PasswordError(f"Set {env_name}, or run this in a terminal to be asked for it")
    for _ in range(MAX_PROMPT_ATTEMPTS):
        first = prompt(f"{label} password (at least {MIN_PASSWORD_LENGTH} characters): ")
        if len(first) < MIN_PASSWORD_LENGTH:
            print(f"Too short: it needs at least {MIN_PASSWORD_LENGTH} characters.")
            continue
        if prompt(f"{label} password again: ") != first:
            print("Those didn't match. Try again.")
            continue
        return first
    raise PasswordError(f"No valid {label.lower()} password entered")


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


def _collect_passwords() -> dict[str, str]:
    prompt = getpass.getpass if sys.stdin.isatty() else None
    try:
        return {
            key: resolve_password(
                f"SEED_{key.upper()}_PASSWORD", key.title(), env=os.environ, prompt=prompt
            )
            for key in ("admin", "guardian", "student")
        }
    except PasswordError as exc:
        sys.exit(str(exc))


async def _run(args: argparse.Namespace) -> None:
    passwords = _collect_passwords()
    accounts = {
        "admin": SeedAccount(Role.ADMIN, args.admin_email, args.admin_name, passwords["admin"]),
        "guardian": SeedAccount(
            Role.GUARDIAN, args.guardian_email, args.guardian_name, passwords["guardian"]
        ),
        "student": SeedAccount(
            Role.STUDENT, args.student_username, args.student_name, passwords["student"]
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
