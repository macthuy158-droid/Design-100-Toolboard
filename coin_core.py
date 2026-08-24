"""飞侠币 — the internal credit system shared between 小飞侠 developers.

A closed loop: publishing an approved tool mints a fixed reward, and a
developer who charges for their tool is paid out of the downloader's balance.
小游侠 are untouched — they keep buying with 人民币 through orders/entitlements.

The ledger is the source of truth; a balance is the sum of a user's rows. Every
grant carries a dedupe key so a replayed approval or a double-submitted form
cannot mint or spend twice. Deliberately no dependency on community_core, which
imports this module for the download gate.
"""

from datetime import datetime, timezone

from fastapi import HTTPException

import app_v2 as site

PUBLISH_REWARD = 10
COIN_NAME = "飞侠币"

REASON_LABELS = {
    "publish_reward": "发布工具奖励",
    "download_spend": "下载工具支出",
    "download_income": "工具被下载收入",
    "admin_adjust": "管理员调整",
}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def init_db():
    with site.db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS coin_ledger(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          delta INTEGER NOT NULL,
          reason TEXT NOT NULL,
          tool_id INTEGER,
          ref TEXT NOT NULL DEFAULT '',
          note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_coin_user ON coin_ledger(user_id,id DESC);
        ''')
        # One reward per submission, one charge per (buyer,tool), one payout per
        # (owner,tool,buyer) — enforced by the storage engine, not by app logic.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_coin_dedupe "
            "ON coin_ledger(user_id,reason,COALESCE(tool_id,0),ref)"
        )
        for table in ("tools", "tool_submissions"):
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if cols and "coin_price" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN coin_price INTEGER NOT NULL DEFAULT 0")


def coin_price(tool):
    """Tools predating the feature read as free rather than raising."""
    try:
        keys = tool.keys()
    except AttributeError:
        return 0
    return int(tool["coin_price"] or 0) if "coin_price" in keys else 0


def balance(conn, user_id):
    row = conn.execute(
        "SELECT COALESCE(SUM(delta),0) b FROM coin_ledger WHERE user_id=?", (user_id,)
    ).fetchone()
    return int(row["b"] or 0)


def has_access(conn, user_id, tool_id):
    return bool(conn.execute(
        "SELECT 1 FROM coin_ledger WHERE user_id=? AND tool_id=? AND reason='download_spend'",
        (user_id, tool_id),
    ).fetchone())


def is_owner(tool, user_id):
    owner = tool["owner_user_id"]
    return owner is not None and int(owner) == int(user_id)


def _record(conn, user_id, delta, reason, tool_id=None, ref="", note=""):
    """Append one ledger row. Returns False when the dedupe key already exists."""
    try:
        conn.execute(
            "INSERT INTO coin_ledger(user_id,delta,reason,tool_id,ref,note,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, delta, reason, tool_id, ref, note, now()),
        )
    except Exception as exc:  # UNIQUE violation on the dedupe index
        if "UNIQUE" in str(exc).upper():
            return False
        raise
    return True


def grant_publish_reward(conn, user_id, submission_id, tool_id, note=""):
    """Mint the fixed reward for one approved submission. Idempotent."""
    return _record(conn, user_id, PUBLISH_REWARD, "publish_reward",
                   tool_id=tool_id, ref=str(submission_id), note=note)


def purchase(conn, buyer, tool):
    """Charge the buyer and pay the tool owner. Raises 409 when unaffordable.

    Returns the price actually charged; 0 means nothing was owed (free tool,
    own tool, or already unlocked).
    """
    price = coin_price(tool)
    if price <= 0 or is_owner(tool, buyer["id"]):
        return 0
    if has_access(conn, buyer["id"], tool["id"]):
        return 0

    available = balance(conn, buyer["id"])
    if available < price:
        raise HTTPException(
            409,
            f"{COIN_NAME}不足：需要 {price} 个，当前余额 {available} 个。"
            f"发布工具或被他人下载可以获得{COIN_NAME}。",
        )

    if not _record(conn, buyer["id"], -price, "download_spend",
                   tool_id=tool["id"], note=tool["name"]):
        return 0  # concurrent unlock already charged this buyer

    owner = tool["owner_user_id"]
    if owner is not None:
        _record(conn, int(owner), price, "download_income", tool_id=tool["id"],
                ref=str(buyer["id"]), note=f"{tool['name']} · {buyer['display_name']}")
    return price


def adjust(conn, user_id, delta, note=""):
    """Administrative correction. Ref is timestamped so repeats are allowed."""
    return _record(conn, user_id, int(delta), "admin_adjust", ref=now(), note=note)


def recent(conn, user_id, limit=20):
    return conn.execute(
        "SELECT * FROM coin_ledger WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
