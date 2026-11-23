"""Create a TicketDesk user, or reset an existing user's password and role.

Passwords are typed at a prompt (never passed on the command line, so they
don't end up in shell history or process listings).

Usage, from the repository root:
    python -m scripts.create_user admin --role admin --full-name "Admin"
    python -m scripts.create_user priya --role agent
    python -m scripts.create_user ravi                    # role defaults to "user"

For automation, --password-env NAME reads the password from that environment variable.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import build_engine
from app.models import ROLES, User
from app.security import hash_password


def read_password(env_name: str | None) -> str:
    if env_name:
        value = os.environ.get(env_name, "")
        if not value:
            sys.exit(f"Environment variable {env_name} is empty")
        return value
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords did not match")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--role", choices=ROLES, default="user")
    parser.add_argument("--full-name", default="")
    parser.add_argument("--password-env", metavar="NAME")
    args = parser.parse_args()

    username = args.username.strip().lower()
    password = read_password(args.password_env)
    if len(password) < 8:
        sys.exit("Use a password of at least 8 characters")

    engine = build_engine(Settings.from_env())
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            db.add(User(username=username, full_name=args.full_name, role=args.role,
                        password_hash=hash_password(password)))
            action = "Created"
        else:
            user.password_hash = hash_password(password)
            user.role = args.role
            if args.full_name:
                user.full_name = args.full_name
            action = "Updated"
        db.commit()
    print(f"{action} user '{username}' with role '{args.role}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
