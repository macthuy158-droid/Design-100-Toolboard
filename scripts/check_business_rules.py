"""CI smoke checks for the platform's core authorization rules.

Runs against a throwaway database by default. Earlier versions inherited the
real TOOLBOARD_DATA_DIR and left ci-* users, tools and orders behind in
production; set TOOLBOARD_CHECK_USE_REAL_DB=1 only if you actually want that.
"""

import os
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if os.getenv("TOOLBOARD_CHECK_USE_REAL_DB", "0") != "1":
    os.environ["TOOLBOARD_DATA_DIR"] = tempfile.mkdtemp(prefix="toolboard-check-")

from app import public_site as site  # noqa: E402
import coin_core  # noqa: E402
import community_core as core  # noqa: E402


def add_user(conn, token, role=core.ROLE_XIAOFEIXIA, active=1):
    username = f"ci-{role}-{token}"
    salt, digest = core.hash_password("ci-password")
    stamp = core.now()
    cur = conn.execute(
        """INSERT INTO community_users(
            username,display_name,email,password_salt,password_hash,role,active,
            created_at,updated_at
        ) VALUES(?,?,NULL,?,?,?,?,?,?)""",
        (username, username, salt, digest, role, active, stamp, stamp),
    )
    return cur.lastrowid


def add_tool(conn, slug, owner_id, coin_price=0, price_cents=0):
    stamp = core.now()
    cur = conn.execute(
        """INSERT INTO tools(
            slug,name,tagline,description,category,platform,icon_text,screenshots,
            downloads,active,created_at,updated_at,owner_user_id,price_cents,
            developer_name,feixia_coin_price
        ) VALUES(?,?,?,?,?,?,?,'',0,1,?,?,?,?,?,?)""",
        (slug, slug, "CI tool", "CI tool", "测试", "Windows", "CI",
         stamp, stamp, owner_id, price_cents, "CI Owner", coin_price),
    )
    return cur.lastrowid


def row(conn, table, row_id):
    return conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()


def main():
    token = secrets.token_hex(6)
    coin_core.init_db()

    with site.db() as conn:
        owner_id = add_user(conn, token + "-owner")
        buyer_id = add_user(conn, token + "-buyer")
        other_id = add_user(conn, token + "-other")
        off_id = add_user(conn, token + "-off", active=0)

        free_id = add_tool(conn, f"ci-free-{token}", owner_id, coin_price=0)
        paid_id = add_tool(conn, f"ci-paid-{token}", owner_id, coin_price=30, price_cents=1000)

        owner = row(conn, "community_users", owner_id)
        buyer = row(conn, "community_users", buyer_id)
        other = row(conn, "community_users", other_id)
        off = row(conn, "community_users", off_id)
        free_tool = row(conn, "tools", free_id)
        paid_tool = row(conn, "tools", paid_id)

        # ---- ownership ----
        assert core.is_tool_owner(paid_tool, owner), "original developer must own the tool"
        assert not core.is_tool_owner(paid_tool, other), "another developer must not own it"

        # ---- the download gate ----
        assert core.can_download(conn, owner, paid_tool), "owner downloads own tool free"
        assert core.can_download(conn, buyer, free_tool), "unpriced tool is free to download"
        assert not core.can_download(conn, buyer, paid_tool), "priced tool needs unlocking first"
        assert not core.can_download(conn, off, free_tool), "deactivated account must be refused"
        assert not core.can_download(conn, None, free_tool), "anonymous must be refused"

        # Historical balances/access survive, while no new exchange or reward is possible.
        coin_core._record(conn, buyer_id, 100, "register_bonus", note="historical fixture")
        for attempt in (
            lambda: coin_core.purchase(conn, buyer, paid_tool),
            lambda: coin_core.adjust(conn, buyer_id, 100),
            lambda: coin_core.spend(conn, buyer_id, 30, "bounty_escrow"),
        ):
            try:
                attempt()
                raise AssertionError("retired point mutation accepted")
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 410
        assert coin_core.balance(conn, buyer_id) == 100
        coin_core._record(conn, buyer_id, -30, "download_spend", tool_id=paid_id)
        assert core.can_download(conn, buyer, paid_tool), "old exchange retains download access"
        assert not core.can_download(conn, other, paid_tool)
        assert not coin_core.grant_publish_reward(conn, owner_id, 4242, paid_id)
        assert not coin_core.grant_register_bonus(conn, other_id)
        assert coin_core.balance(conn, owner_id) == 0
        assert coin_core.balance(conn, other_id) == 0

        # ---- legacy 人民币 entitlements are still honoured ----
        legacy_id = add_tool(conn, f"ci-legacy-{token}", owner_id, coin_price=50, price_cents=1000)
        legacy = row(conn, "tools", legacy_id)
        assert not core.can_download(conn, other, legacy)
        stamp = core.now()
        cur = conn.execute(
            "INSERT INTO orders(order_no,user_id,tool_id,amount_cents,status,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (f"CI-{token}", other_id, legacy_id, 1000, "pending", stamp),
        )
        order_id = cur.lastrowid
        conn.execute(
            "INSERT INTO entitlements(user_id,tool_id,order_id,granted_at) VALUES(?,?,?,?)",
            (other_id, legacy_id, order_id, stamp),
        )
        assert not core.can_download(conn, other, legacy), "pending order must not grant download"
        conn.execute("UPDATE orders SET status='paid',paid_at=? WHERE id=?", (stamp, order_id))
        assert core.can_download(conn, other, legacy), "paid order must still grant download"

    print("Business rule checks passed")
    print("- Owner downloads own tool; unpriced tools are free")
    print("- Priced tools require an unlock; deactivated accounts refused")
    print("- Historical exchanges keep download rights")
    print("- New point spending and adjustment refused")
    print("- Registration and publication no longer award points")
    print("- Legacy paid entitlements still honoured")


if __name__ == "__main__":
    main()
