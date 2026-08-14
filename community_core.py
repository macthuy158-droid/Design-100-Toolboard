import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import app_v2 as site

BRAND_NAME = "小飞侠设计100%"
ROLE_XIAOFEIXIA = "xiaofeixia"
ROLE_XIAOYOUXIA = "xiaoyouxia"
USER_COOKIE = "design100_user"
SESSION_SECRET = os.getenv("TOOLBOARD_SESSION_SECRET", "") or site.SESSION_SECRET
CAD_LICENSE_DB = Path(os.getenv("CAD100_LICENSE_DB", "/opt/cad100-license/data/license.db"))
SUBMISSION_DIR = site.DATA_DIR / "submissions"
MAX_UPLOAD_BYTES = int(os.getenv("TOOLBOARD_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
VALID_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_password(password: str, salt: Optional[str] = None):
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 240_000)
    return salt_bytes.hex(), digest.hex()


def verify_password(password: str, salt: str, expected: str):
    _, actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def init_db():
    site.init_db()
    SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)
    with site.db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS community_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL,
            email TEXT UNIQUE COLLATE NOCASE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('xiaofeixia','xiaoyouxia')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            tool_id INTEGER NOT NULL,
            amount_cents INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            provider TEXT NOT NULL DEFAULT '',
            provider_txn TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            paid_at TEXT,
            FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS entitlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tool_id INTEGER NOT NULL,
            order_id INTEGER,
            granted_at TEXT NOT NULL,
            UNIQUE(user_id,tool_id),
            FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tool_id,user_id),
            FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tool_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            submission_type TEXT NOT NULL DEFAULT 'new_tool',
            tool_id INTEGER,
            slug TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            tagline TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '效率工具',
            platform TEXT NOT NULL DEFAULT 'Windows',
            icon_text TEXT NOT NULL DEFAULT '100',
            price_cents INTEGER NOT NULL DEFAULT 0,
            version TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            package_name TEXT NOT NULL,
            package_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            admin_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tool_id INTEGER NOT NULL,
            release_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reviews_tool ON reviews(tool_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_submissions_status ON tool_submissions(status,id DESC);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id,id DESC);
        ''')
        cols = {r['name'] for r in conn.execute("PRAGMA table_info(tools)").fetchall()}
        if 'owner_user_id' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN owner_user_id INTEGER")
        if 'price_cents' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN price_cents INTEGER NOT NULL DEFAULT 0")
        if 'developer_name' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN developer_name TEXT NOT NULL DEFAULT ''")


def make_session(user_id: int):
    exp = int(time.time()) + 7 * 86400
    payload = f"{user_id}.{exp}"
    sig = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def current_user(request):
    token = request.cookies.get(USER_COOKIE, "")
    try:
        uid, exp, sig = token.split(".", 2)
        payload = f"{uid}.{exp}"
        expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if int(exp) < int(time.time()) or not hmac.compare_digest(sig, expected):
            return None
        with site.db() as conn:
            return conn.execute("SELECT * FROM community_users WHERE id=? AND active=1", (int(uid),)).fetchone()
    except Exception:
        return None


def role_label(role: str):
    return "小飞侠" if role == ROLE_XIAOFEIXIA else "小游侠"


def can_download(conn, user, tool):
    if not user or not user['active']:
        return False
    if user['role'] == ROLE_XIAOFEIXIA:
        return True
    return bool(conn.execute("SELECT id FROM entitlements WHERE user_id=? AND tool_id=?", (user['id'], tool['id'])).fetchone())


def import_cad_users():
    if not CAD_LICENSE_DB.exists():
        raise FileNotFoundError(str(CAD_LICENSE_DB))
    source = sqlite3.connect(str(CAD_LICENSE_DB))
    source.row_factory = sqlite3.Row
    try:
        names = [r['name'] for r in source.execute("SELECT name FROM users WHERE active=1 ORDER BY id").fetchall()]
    finally:
        source.close()
    imported = 0
    with site.db() as conn:
        for raw in names:
            name = " ".join(str(raw).strip().split())
            if not name or conn.execute("SELECT id FROM community_users WHERE username=? COLLATE NOCASE", (name,)).fetchone():
                continue
            salt, digest = hash_password(name)
            stamp = now()
            conn.execute("INSERT INTO community_users(username,display_name,email,password_salt,password_hash,role,active,created_at,updated_at) VALUES(?,?,NULL,?,?,?,1,?,?)", (name,name,salt,digest,ROLE_XIAOFEIXIA,stamp,stamp))
            imported += 1
    return imported


def add_xiaofeixia(name: str, password: str = ""):
    clean = " ".join(name.strip().split())
    salt, digest = hash_password(password or clean)
    stamp = now()
    with site.db() as conn:
        cur = conn.execute("INSERT INTO community_users(username,display_name,email,password_salt,password_hash,role,active,created_at,updated_at) VALUES(?,?,NULL,?,?,?,1,?,?)", (clean,clean,salt,digest,ROLE_XIAOFEIXIA,stamp,stamp))
        return cur.lastrowid


def grant_order(order_id: int):
    with site.db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            return False
        stamp = now()
        conn.execute("UPDATE orders SET status='paid',provider='manual',paid_at=? WHERE id=?", (stamp,order_id))
        conn.execute("INSERT OR IGNORE INTO entitlements(user_id,tool_id,order_id,granted_at) VALUES(?,?,?,?)", (order['user_id'],order['tool_id'],order_id,stamp))
    return True
