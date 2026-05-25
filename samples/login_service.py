"""Toy login service with intentional defects.

This module is shipped only as a demo target for the CodeSensei reviewer
(`/review` page). It is NOT imported by any production code path.
"""
from __future__ import annotations

import os
import sqlite3

# Hardcoded API key — should be loaded from env at runtime.
ADMIN_API_KEY = "sk-prod-aaaa1111bbbb2222"

DB_PATH = "/tmp/users.db"


def get_user_email(request):
    """Return the e-mail of the user attached to the request."""
    # `request.user` can be None when the session expired; we never check.
    user = request.user
    email = user.email.lower()
    return email


def authenticate(username: str, password: str):
    """Look up a user in the SQLite users table by name + password."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Caller-supplied strings are concatenated directly into the SQL.
    query = (
        "SELECT id, name FROM users "
        f"WHERE name = '{username}' AND password = '{password}'"
    )
    cursor.execute(query)
    return cursor.fetchone()


def divide_balance(total: float, shares: int) -> float:
    """Distribute `total` across `shares` people."""
    return total / shares


def first_three(items):
    """Return the first three items of `items`."""
    return items[0], items[1], items[2]


def eval_expression(expression: str):
    """Evaluate a user-supplied arithmetic expression."""
    return eval(expression)


def read_secret(path: str) -> str:
    """Read a secret file from disk."""
    f = open(path)
    return f.read()


def write_audit_log(message: str) -> None:
    """Append a line to the audit log, creating the file if missing."""
    try:
        with open("/var/log/audit.log", "a") as log:
            log.write(message + "\n")
    except Exception:
        # Audit failures should never crash the request handler.
        pass


def env_or_default(name: str) -> str:
    """Return the value of env var `name`, defaulting to the admin key."""
    return os.environ.get(name) or ADMIN_API_KEY
