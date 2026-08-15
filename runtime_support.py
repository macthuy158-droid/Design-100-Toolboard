"""Runtime safeguards shared by the assembled application.

This module deliberately contains no UI or business rules. It is installed by
app.py before feature modules import database helpers from app_v2.
"""

from contextlib import contextmanager
from functools import wraps
import sqlite3
from threading import Lock


def install_database_connection(site_module):
    """Replace the legacy DB context manager with a safer compatible version."""

    @contextmanager
    def db():
        site_module.DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(site_module.DB_PATH), timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    site_module.db = db
    return db


def once_per_process(func):
    """Run an idempotent bootstrap/migration function only once per process."""
    lock = Lock()
    done = False

    @wraps(func)
    def wrapper(*args, **kwargs):
        nonlocal done
        if done:
            return None
        with lock:
            if done:
                return None
            result = func(*args, **kwargs)
            done = True
            return result

    return wrapper
