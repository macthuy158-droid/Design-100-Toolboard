"""飞侠币 — the single credit currency the platform runs on.

Nobody pays cash. A 小飞侠 earns 飞侠币 by registering and by publishing tools,
and spends them downloading other people's tools or funding bounties; whatever
a downloader spends, the tool's owner receives. The store is a closed loop.

The ledger is the source of truth; a balance is the sum of a user's rows. Every
grant carries a dedupe key backed by a unique index, so a replayed approval
cannot mint twice and a resubmitted unlock cannot charge twice. Deliberately no
dependency on community_core, which imports this module for the download gate.
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
    "admin_adjust": "管理员充值 / 调整",
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
    elif "price_cents" in cols:
        # Never went through the two-currency step: convert straight from 元,
        # at ¥1 = 1 游侠币 = 0.5 飞侠币.
        conn.execute(
            f"UPDATE {table} SET {PRICE_COLUMN}=(CAST(price_cents/100 AS INTEGER)+1)/2 "
            f"WHERE price_cents>0 AND {PRICE_COLUMN}=0"
        )


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
    """Mint the joining bonus. The empty ref pins it to one row per account."""
    return _record(conn, user_id, REGISTER_BONUS, "register_bonus", note=note)


def grant_publish_reward(conn, user_id, submission_id, tool_id, note=""):
    """Mint the fixed reward for one approved submission. Idempotent."""
    return _record(conn, user_id, PUBLISH_REWARD, "publish_reward",
                   tool_id=tool_id, ref=str(submission_id), note=note)


def purchase(conn, buyer, tool):
    """Charge the buyer and pay the tool owner.

    Raises 409 when the tool is unpriced or the balance will not cover it.
    Returns the amount charged; 0 means nothing was owed.
    """
    price = coin_price(tool)
    if is_owner(tool, buyer["id"]):
        return 0
    if has_access(conn, buyer["id"], tool["id"]):
        return 0
    if price <= 0:
        raise HTTPException(409, f"该工具尚未设置{COIN_NAME}价格，请联系开发者或管理员。")

    available = balance(conn, buyer["id"])
    if available < price:
        raise HTTPException(
            409, f"{COIN_NAME}不足：需要 {price} 个，当前余额 {available} 个。"
        )

    if not _record(conn, buyer["id"], -price, "download_spend",
                   tool_id=tool["id"], note=tool["name"]):
        return 0  # a concurrent unlock already charged this buyer

    owner = tool["owner_user_id"]
    if owner is not None:
        _record(conn, int(owner), price, "download_income", tool_id=tool["id"],
                ref=str(buyer["id"]), note=f"{tool['name']} · {buyer['display_name']}")
    return price


def spend(conn, user_id, amount, reason, ref="", note=""):
    """Debit a balance, refusing to go negative. Used for bounty escrow."""
    amount = int(amount)
    if amount <= 0:
        return 0
    available = balance(conn, user_id)
    if available < amount:
        raise HTTPException(
            409, f"{COIN_NAME}不足：需要 {amount} 个，当前余额 {available} 个。"
        )
    _record(conn, user_id, -amount, reason, ref=ref or now(), note=note)
    return amount


def credit(conn, user_id, amount, reason, ref="", note=""):
    """Credit a balance — a bounty refund or payout."""
    amount = int(amount)
    if amount <= 0:
        return 0
    _record(conn, user_id, amount, reason, ref=ref or now(), note=note)
    return amount


def adjust(conn, user_id, delta, note=""):
    """Administrative top-up or correction. Timestamped so repeats are allowed."""
    return _record(conn, user_id, int(delta), "admin_adjust", ref=now(), note=note)


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
