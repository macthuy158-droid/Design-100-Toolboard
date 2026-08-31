"""Grant the joining bonus to accounts that predate it.

Safe to run repeatedly: the unique index on coin_ledger pins register_bonus to
one row per account, so a second run grants nothing. Pass --apply to write;
default is a dry run.

    python scripts/backfill_coins.py            # show what would happen
    python scripts/backfill_coins.py --apply    # grant
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("TOOLBOARD_DATA_DIR", os.path.join(ROOT, "data"))

import app_v2 as site  # noqa: E402
from runtime_support import install_database_connection  # noqa: E402

install_database_connection(site)

import coin_core  # noqa: E402
import community_core as core  # noqa: E402


def main():
    apply = "--apply" in sys.argv
    core.init_db()
    coin_core.init_db()

    with site.db() as conn:
        users = conn.execute(
            "SELECT id,display_name,role,active FROM community_users "
            "WHERE active=1 ORDER BY id"
        ).fetchall()
        pending = [
            u for u in users
            if not conn.execute(
                "SELECT 1 FROM coin_ledger WHERE user_id=? AND reason='register_bonus'",
                (u["id"],),
            ).fetchone()
        ]

    print(f"active accounts   : {len(users)}")
    print(f"awaiting bonus    : {len(pending)}")
    print(f"bonus per account : {coin_core.REGISTER_BONUS} {coin_core.COIN_NAME}")
    print(f"total to grant    : {len(pending) * coin_core.REGISTER_BONUS}")
    for u in pending:
        print(f"   #{u['id']:>2} {u['display_name']} ({u['role']})")

    if not apply:
        print("\nDRY RUN — pass --apply to grant")
        return

    granted = 0
    with site.db() as conn:
        for u in pending:
            if coin_core.grant_register_bonus(conn, u["id"], note="存量账号补发"):
                granted += 1
    print(f"\ngranted to {granted} accounts")

    with site.db() as conn:
        print("\nbalances:")
        for u in conn.execute(
            "SELECT id,display_name FROM community_users WHERE active=1 ORDER BY id"
        ).fetchall():
            print(f"   #{u['id']:>2} {u['display_name']}: "
                  f"{coin_core.balance(conn, u['id'])} {coin_core.COIN_NAME}")


main()
