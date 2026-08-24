"""飞侠币 / 游侠币 — the two credit currencies the store runs on.

Nobody pays cash at the point of download. 小飞侠 spend 飞侠币, earned by
publishing; 小游侠 spend 游侠币, topped up by an administrator. Either way the
tool's owner is credited in the same currency the downloader spent, so the
store is a closed loop per currency.

The ledger is the source of truth; a balance is the sum of a user's rows in one
currency. Every grant carries a dedupe key backed by a unique index, so a
replayed approval cannot mint twice and a resubmitted unlock cannot charge
twice. Deliberately no dependency on community_core, which imports this module
for the download gate.
"""

from datetime import datetime, timezone

from fastapi import HTTPException

import app_v2 as site

FEIXIA = "feixia"
YOUXIA = "youxia"

CURRENCIES = {FEIXIA: "飞侠币", YOUXIA: "游侠币"}
PRICE_COLUMN = {FEIXIA: "feixia_coin_price", YOUXIA: "youxia_coin_price"}

PUBLISH_REWARD = 10  # minted in 飞侠币 when a submission is approved
MAX_PRICE = 9999

REASON_LABELS = {
    "publish_reward": "发布工具奖励",
    "download_spend": "下载工具支出",
    "download_income": "工具被下载收入",
    "admin_adjust": "管理员充值 / 调整",
}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def label(currency):
    return CURRENCIES.get(currency, currency)


def currency_for_role(role):
    """小飞侠 transact in 飞侠币, everyone else in 游侠币."""
    return FEIXIA if role == "xiaofeixia" else YOUXIA


def _migrate_price_columns(conn, table):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if not cols:
        return
    # The first cut of the feature shipped a single 飞侠币 column named
    # coin_price; name it for its currency now that there are two.
    if "coin_price" in cols and "feixia_coin_price" not in cols:
        conn.execute(f"ALTER TABLE {table} RENAME COLUMN coin_price TO feixia_coin_price")
        cols.add("feixia_coin_price")
    if "feixia_coin_price" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN feixia_coin_price INTEGER NOT NULL DEFAULT 0")
    if "youxia_coin_price" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN youxia_coin_price INTEGER NOT NULL DEFAULT 0")
        # Carry existing 人民币 pricing across at ¥1 = 1 游侠币 so tools that
        # were already on sale stay purchasable instead of silently delisting.
        if "price_cents" in cols:
            conn.execute(
                f"UPDATE {table} SET youxia_coin_price=MAX(CAST(price_cents/100 AS INTEGER),0) "
                f"WHERE price_cents>0"
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
        if "currency" not in cols:
            conn.execute(
                f"ALTER TABLE coin_ledger ADD COLUMN currency TEXT NOT NULL DEFAULT '{FEIXIA}'"
            )
            # The single-currency index cannot tell 飞侠币 from 游侠币 apart.
            conn.execute("DROP INDEX IF EXISTS idx_coin_dedupe")
        # One reward per submission, one charge per (buyer,tool,currency), one
        # payout per (owner,tool,buyer,currency) — enforced by the storage
        # engine rather than by application logic.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_coin_dedupe "
            "ON coin_ledger(user_id,currency,reason,COALESCE(tool_id,0),ref)"
        )
        for table in ("tools", "tool_submissions"):
            _migrate_price_columns(conn, table)


def coin_price(tool, currency):
    """Rows predating the feature read as unpriced rather than raising."""
    column = PRICE_COLUMN.get(currency)
    if not column:
        return 0
    try:
        keys = tool.keys()
    except AttributeError:
        return 0
    return int(tool[column] or 0) if column in keys else 0


def balance(conn, user_id, currency):
    row = conn.execute(
        "SELECT COALESCE(SUM(delta),0) b FROM coin_ledger WHERE user_id=? AND currency=?",
        (user_id, currency),
    ).fetchone()
    return int(row["b"] or 0)


def has_access(conn, user_id, tool_id, currency):
    return bool(conn.execute(
        "SELECT 1 FROM coin_ledger WHERE user_id=? AND tool_id=? AND currency=? "
        "AND reason='download_spend'",
        (user_id, tool_id, currency),
    ).fetchone())


def is_owner(tool, user_id):
    owner = tool["owner_user_id"]
    return owner is not None and int(owner) == int(user_id)


def _record(conn, user_id, currency, delta, reason, tool_id=None, ref="", note=""):
    """Append one ledger row. Returns False when the dedupe key already exists."""
    try:
        conn.execute(
            "INSERT INTO coin_ledger(user_id,currency,delta,reason,tool_id,ref,note,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (user_id, currency, delta, reason, tool_id, ref, note, now()),
        )
    except Exception as exc:  # UNIQUE violation on the dedupe index
        if "UNIQUE" in str(exc).upper():
            return False
        raise
    return True


def grant_publish_reward(conn, user_id, submission_id, tool_id, note=""):
    """Mint the fixed 飞侠币 reward for one approved submission. Idempotent."""
    return _record(conn, user_id, FEIXIA, PUBLISH_REWARD, "publish_reward",
                   tool_id=tool_id, ref=str(submission_id), note=note)


def purchase(conn, buyer, tool, currency):
    """Charge the buyer and pay the tool owner, both in `currency`.

    Raises 409 when the tool is unpriced or the balance will not cover it.
    Returns the amount charged; 0 means nothing was owed.
    """
    price = coin_price(tool, currency)
    if is_owner(tool, buyer["id"]):
        return 0
    if has_access(conn, buyer["id"], tool["id"], currency):
        return 0
    name = label(currency)
    if price <= 0:
        raise HTTPException(409, f"该工具尚未设置{name}价格，请联系开发者或管理员。")

    available = balance(conn, buyer["id"], currency)
    if available < price:
        raise HTTPException(
            409,
            f"{name}不足：需要 {price} 个，当前余额 {available} 个。",
        )

    if not _record(conn, buyer["id"], currency, -price, "download_spend",
                   tool_id=tool["id"], note=tool["name"]):
        return 0  # a concurrent unlock already charged this buyer

    owner = tool["owner_user_id"]
    if owner is not None:
        _record(conn, int(owner), currency, price, "download_income", tool_id=tool["id"],
                ref=str(buyer["id"]), note=f"{tool['name']} · {buyer['display_name']}")
    return price


def adjust(conn, user_id, currency, delta, note=""):
    """Administrative top-up or correction. Timestamped so repeats are allowed."""
    return _record(conn, user_id, currency, int(delta), "admin_adjust",
                   ref=now(), note=note)


def recent(conn, user_id, currency, limit=20):
    return conn.execute(
        "SELECT * FROM coin_ledger WHERE user_id=? AND currency=? ORDER BY id DESC LIMIT ?",
        (user_id, currency, limit),
    ).fetchall()


def earned(conn, user_id, currency):
    row = conn.execute(
        "SELECT COALESCE(SUM(delta),0) s FROM coin_ledger "
        "WHERE user_id=? AND currency=? AND delta>0",
        (user_id, currency),
    ).fetchone()
    return int(row["s"] or 0)
