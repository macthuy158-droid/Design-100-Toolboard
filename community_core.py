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
TOOL_CATEGORIES = ["CAD", "Rhino", "SketchUp", "Revit", "UE", "Figma", "Word", "GIS", "其他"]
DEFAULT_TOOL_CATEGORY = "其他"


def slug_from_name(name: str) -> str:
    from pypinyin import pinyin, Style
    raw = name.strip().lower()
    parts = []
    for ch in raw:
        if re.match(r"[a-z0-9]", ch):
            parts.append(ch)
        elif re.match(r"[\s_\-]", ch):
            parts.append("-")
        elif "一" <= ch <= "鿿":
            py = pinyin(ch, style=Style.NORMAL)
            parts.append(py[0][0] if py else "")
        else:
            parts.append("-")
    slug = re.sub(r"-+", "-", "".join(parts)).strip("-")
    return slug[:80] if slug else "tool"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_password(password: str, salt: Optional[str] = None):
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 240_000)
    return salt_bytes.hex(), digest.hex()


def verify_password(password: str, salt: str, expected: str):
    _, actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def _migrate_legacy_slugs(conn):
    legacy = conn.execute("SELECT id,slug FROM tools WHERE slug=?", ("文本100%",)).fetchone()
    target = conn.execute("SELECT id FROM tools WHERE slug=?", ("text-100",)).fetchone()
    if legacy and not target:
        conn.execute("UPDATE tools SET slug=?,updated_at=? WHERE id=?", ("text-100", now(), legacy["id"]))
        conn.execute("UPDATE tool_submissions SET slug=? WHERE tool_id=?", ("text-100", legacy["id"]))


def _backfill_legacy_tool_owners(conn):
    tools = conn.execute("SELECT id FROM tools WHERE owner_user_id IS NULL").fetchall()
    for tool in tools:
        first = conn.execute(
            "SELECT s.user_id,u.display_name FROM tool_submissions s "
            "JOIN community_users u ON u.id=s.user_id "
            "WHERE s.tool_id=? AND s.status='approved' ORDER BY s.id ASC LIMIT 1",
            (tool["id"],),
        ).fetchone()
        if first:
            conn.execute(
                "UPDATE tools SET owner_user_id=?,developer_name=?,updated_at=? WHERE id=?",
                (first["user_id"], first["display_name"], now(), tool["id"]),
            )


def _install_submission_guards(conn):
    conn.executescript('''
    DROP TRIGGER IF EXISTS trg_release_owner_guard;
    CREATE TRIGGER trg_release_owner_guard
    BEFORE UPDATE OF status ON tool_submissions
    WHEN NEW.status='approved' AND OLD.status<>'approved' AND NEW.submission_type='new_release'
    BEGIN
      SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM tools
        WHERE id=NEW.tool_id AND owner_user_id=NEW.user_id
      ) THEN RAISE(ABORT, 'only tool owner can approve a release') END;
    END;

    DROP TRIGGER IF EXISTS trg_release_price_sync;
    CREATE TRIGGER trg_release_price_sync
    AFTER UPDATE OF status ON tool_submissions
    WHEN NEW.status='approved' AND OLD.status<>'approved' AND NEW.submission_type='new_release'
    BEGIN
      UPDATE tools
      SET price_cents=NEW.price_cents,
          developer_name=(SELECT display_name FROM community_users WHERE id=NEW.user_id),
          updated_at=COALESCE(NEW.reviewed_at, NEW.created_at)
      WHERE id=NEW.tool_id;
    END;
    ''')


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
        CREATE TABLE IF NOT EXISTS xiaofeixia_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE COLLATE NOCASE,
            real_name TEXT NOT NULL COLLATE NOCASE,
            used INTEGER NOT NULL DEFAULT 0,
            used_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            used_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_reviews_tool ON reviews(tool_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_submissions_status ON tool_submissions(status,id DESC);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id,id DESC);
        ''')
        sub_cols = {r['name'] for r in conn.execute("PRAGMA table_info(tool_submissions)").fetchall()}
        if 'tool_type' not in sub_cols:
            conn.execute("ALTER TABLE tool_submissions ADD COLUMN tool_type TEXT NOT NULL DEFAULT 'desktop'")
        if 'app_url' not in sub_cols:
            conn.execute("ALTER TABLE tool_submissions ADD COLUMN app_url TEXT NOT NULL DEFAULT ''")
        conn.executescript('''
        ''')
        cols = {r['name'] for r in conn.execute("PRAGMA table_info(tools)").fetchall()}
        if 'owner_user_id' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN owner_user_id INTEGER")
        if 'price_cents' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN price_cents INTEGER NOT NULL DEFAULT 0")
        if 'developer_name' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN developer_name TEXT NOT NULL DEFAULT ''")
        if 'tool_type' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN tool_type TEXT NOT NULL DEFAULT 'desktop'")
        if 'app_url' not in cols:
            conn.execute("ALTER TABLE tools ADD COLUMN app_url TEXT NOT NULL DEFAULT ''")
        _migrate_legacy_slugs(conn)
        _backfill_legacy_tool_owners(conn)
        _install_submission_guards(conn)


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


def is_tool_owner(tool, user):
    if not tool or not user or user['role'] != ROLE_XIAOFEIXIA:
        return False
    owner = tool['owner_user_id']
    return owner is not None and int(owner) == int(user['id'])


def can_download(conn, user, tool):
    if not user or not user['active']:
        return False
    if user['role'] == ROLE_XIAOFEIXIA:
        import coin_core
        price = coin_core.coin_price(tool)
        if price <= 0 or coin_core.is_owner(tool, user['id']):
            return True
        return coin_core.has_access(conn, user['id'], tool['id'])
    return bool(conn.execute(
        "SELECT e.id FROM entitlements e JOIN orders o ON o.id=e.order_id "
        "WHERE e.user_id=? AND e.tool_id=? AND o.status='paid' AND o.amount_cents>0 LIMIT 1",
        (user['id'], tool['id']),
    ).fetchone())


def generate_invite_code(real_name: str):
    from pypinyin import pinyin, Style
    py = "".join(s[0] for s in pinyin(real_name, style=Style.NORMAL))
    return py + "cswadi"


def create_invite(real_name: str):
    clean = " ".join(real_name.strip().split())
    if not clean:
        raise ValueError("姓名不能为空。")
    code = generate_invite_code(clean)
    stamp = now()
    with site.db() as conn:
        existing = conn.execute(
            "SELECT code FROM xiaofeixia_invites WHERE real_name=? COLLATE NOCASE AND used=0",
            (clean,),
        ).fetchone()
        if existing:
            return existing["code"], False
        conn.execute(
            "INSERT INTO xiaofeixia_invites(code,real_name,used,created_at) VALUES(?,?,0,?)",
            (code, clean, stamp),
        )
    return code, True


def batch_create_invites():
    if not CAD_LICENSE_DB.exists():
        raise FileNotFoundError(str(CAD_LICENSE_DB))
    source = sqlite3.connect(str(CAD_LICENSE_DB))
    source.row_factory = sqlite3.Row
    try:
        names = [r["name"] for r in source.execute("SELECT name FROM users WHERE active=1 ORDER BY id").fetchall()]
    finally:
        source.close()
    created = 0
    for raw in names:
        name = " ".join(str(raw).strip().split())
        if not name:
            continue
        _, is_new = create_invite(name)
        if is_new:
            created += 1
    return created


def validate_invite(code: str, real_name: str):
    clean_code = code.strip()
    clean_name = " ".join(real_name.strip().split())
    with site.db() as conn:
        invite = conn.execute(
            "SELECT * FROM xiaofeixia_invites WHERE code=? COLLATE NOCASE",
            (clean_code,),
        ).fetchone()
    if not invite:
        return None, "邀请码不存在。"
    if invite["used"]:
        return None, "该邀请码已被使用。"
    if invite["real_name"].lower() != clean_name.lower():
        return None, "姓名与邀请码不匹配。"
    return invite, None


def mark_invite_used(invite_id: int, user_id: int):
    with site.db() as conn:
        conn.execute(
            "UPDATE xiaofeixia_invites SET used=1,used_by_user_id=?,used_at=? WHERE id=?",
            (user_id, now(), invite_id),
        )


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
        if int(order['amount_cents'] or 0) <= 0:
            return False
        stamp = now()
        conn.execute("UPDATE orders SET status='paid',provider='manual',paid_at=? WHERE id=?", (stamp,order_id))
        conn.execute("INSERT OR IGNORE INTO entitlements(user_id,tool_id,order_id,granted_at) VALUES(?,?,?,?)", (order['user_id'],order['tool_id'],order_id,stamp))
    return True
