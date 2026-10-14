"""Community contribution points, independent of cash purchases.

Points are awarded for registration and publishing, exchanged for opted-in
community tools or used in bounties. No cash recharge or withdrawal exists.
The ledger is the balance source of truth; unique dedupe keys prevent repeated
awards and exchanges. Cash sales and entitlements live in payment_core.
"""

import math
from datetime import datetime, timezone

from fastapi import HTTPException

import app_v2 as site

COIN_NAME = "飞侠币"
PRICE_COLUMN = "feixia_coin_price"

REGISTER_BONUS = 100  # minted once when an account is created
PUBLISH_REWARD = 10   # minted when a submission is approved
MAX_PRICE = 9999

REASON_LABELS = {
    "register_bonus": "注册赠送",
    "publish_reward": "发布工具奖励",
    "download_spend": "下载工具支出",
    "download_income": "工具被下载收入",
    "bounty_escrow": "发布悬赏冻结",
    "bounty_refund": "悬赏取消退回",
    "bounty_payout": "悬赏赏金收入",
    "admin_adjust": "社区积分奖励 / 调整",
}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _migrate_price_columns(conn, table):
    """Collapse the old two-currency pricing onto a single 飞侠币 price.

    Tools were briefly priced separately for 院内 and 院外 downloaders. 游侠币
    is gone, and the surviving 飞侠币 price is half what 院外 used to pay,
    rounded up so a priced tool never lands on 0 and gets given away.
    """
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if not cols:
        return
    if "coin_price" in cols and PRICE_COLUMN not in cols:
        conn.execute(f"ALTER TABLE {table} RENAME COLUMN coin_price TO {PRICE_COLUMN}")
        cols.add(PRICE_COLUMN)
    if PRICE_COLUMN not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {PRICE_COLUMN} INTEGER NOT NULL DEFAULT 0")
        cols.add(PRICE_COLUMN)

    if "youxia_coin_price" in cols:
        conn.execute(
            f"UPDATE {table} SET {PRICE_COLUMN}=(youxia_coin_price+1)/2 "
            f"WHERE youxia_coin_price>0 AND {PRICE_COLUMN}=0"
        )
        conn.execute(f"ALTER TABLE {table} DROP COLUMN youxia_coin_price")


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
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(coin_ledger)").fetchall()}
        if "currency" in cols:
            # 游侠币 is retired; its rows never existed in production.
            conn.execute("DELETE FROM coin_ledger WHERE currency<>'feixia'")
            conn.execute("DROP INDEX IF EXISTS idx_coin_dedupe")
            conn.execute("ALTER TABLE coin_ledger DROP COLUMN currency")
        # One bonus per account, one reward per submission, one charge per
        # (buyer,tool), one payout per (owner,tool,buyer) — enforced by the
        # storage engine rather than by application logic.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_coin_dedupe "
            "ON coin_ledger(user_id,reason,COALESCE(tool_id,0),ref)"
        )
        for table in ("tools", "tool_submissions"):
            _migrate_price_columns(conn, table)


def half_price(amount):
    """The 飞侠币 price for something previously quoted at `amount` 游侠币."""
    return math.ceil(int(amount or 0) / 2)


def coin_price(tool):
    """Rows predating the feature read as unpriced rather than raising."""
    try:
        keys = tool.keys()
    except AttributeError:
        return 0
    return int(tool[PRICE_COLUMN] or 0) if PRICE_COLUMN in keys else 0


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


def grant_register_bonus(conn, user_id, note="注册赠送"):
    """Retired: keep the signature for historical callers, mint nothing."""
    return False

def grant_publish_reward(conn, user_id, submission_id, tool_id, note=""):
    """Contribution records remain in submissions; no new points are minted."""
    return False

def purchase(conn, buyer, tool):
    """Retired: old ledger entries still grant access via has_access()."""
    raise HTTPException(410, "积分兑换已停用，请使用人民币购买。")

def spend(conn, user_id, amount, reason, ref="", note=""):
    raise HTTPException(410, "积分支出已停用。")

def credit(conn, user_id, amount, reason, ref="", note=""):
    """Credit a balance — a bounty refund or payout."""
    amount = int(amount)
    if amount <= 0:
        return 0
    _record(conn, user_id, amount, reason, ref=ref or now(), note=note)
    return amount


def adjust(conn, user_id, delta, note=""):
    raise HTTPException(410, "历史积分为只读存档。")


def recent(conn, user_id, limit=20):
    return conn.execute(
        "SELECT * FROM coin_ledger WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()


def earned(conn, user_id):
    row = conn.execute(
        "SELECT COALESCE(SUM(delta),0) s FROM coin_ledger WHERE user_id=? AND delta>0",
        (user_id,),
    ).fetchone()
    return int(row["s"] or 0)
