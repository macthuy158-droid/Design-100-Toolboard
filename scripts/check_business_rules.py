"""CI smoke checks for the platform's core authorization rules."""

from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import public_site as site  # noqa: E402
import community_core as core  # noqa: E402


def add_user(conn, token, role):
    username = f"ci-{role}-{token}"
    salt, digest = core.hash_password("ci-password")
    stamp = core.now()
    cur = conn.execute(
        """INSERT INTO community_users(
            username,display_name,email,password_salt,password_hash,role,active,
            created_at,updated_at
        ) VALUES(?,?,NULL,?,?,?,1,?,?)""",
        (username, username, salt, digest, role, stamp, stamp),
    )
    return cur.lastrowid


def add_tool(conn, slug, owner_id, price_cents=1000):
    stamp = core.now()
    cur = conn.execute(
        """INSERT INTO tools(
            slug,name,tagline,description,category,platform,icon_text,screenshots,
            downloads,active,created_at,updated_at,owner_user_id,price_cents,
            developer_name
        ) VALUES(?,?,?,?,?,?,?,'',0,1,?,?,?,?,?)""",
        (
            slug,
            slug,
            "CI tool",
            "CI tool",
            "测试",
            "Windows",
            "CI",
            stamp,
            stamp,
            owner_id,
            price_cents,
            "CI Owner",
        ),
    )
    return cur.lastrowid


def main():
    token = secrets.token_hex(6)
    with site.db() as conn:
        owner_id = add_user(conn, token + "-owner", core.ROLE_XIAOFEIXIA)
        other_dev_id = add_user(conn, token + "-other", core.ROLE_XIAOFEIXIA)
        peer_id = add_user(conn, token + "-peer", core.ROLE_XIAOYOUXIA)

        paid_tool_id = add_tool(conn, f"ci-paid-{token}", owner_id, 1000)
        free_entitlement_tool_id = add_tool(conn, f"ci-zero-{token}", owner_id, 1000)

        owner = conn.execute("SELECT * FROM community_users WHERE id=?", (owner_id,)).fetchone()
        other_dev = conn.execute("SELECT * FROM community_users WHERE id=?", (other_dev_id,)).fetchone()
        peer = conn.execute("SELECT * FROM community_users WHERE id=?", (peer_id,)).fetchone()
        paid_tool = conn.execute("SELECT * FROM tools WHERE id=?", (paid_tool_id,)).fetchone()
        zero_tool = conn.execute("SELECT * FROM tools WHERE id=?", (free_entitlement_tool_id,)).fetchone()

        assert core.is_tool_owner(paid_tool, owner), "original developer must own the tool"
        assert not core.is_tool_owner(paid_tool, other_dev), "other Xiaofeixia must not own the tool"
        assert not core.is_tool_owner(paid_tool, peer), "Xiaoyouxia can never own developer tools"

        assert core.can_download(conn, owner, paid_tool), "Xiaofeixia must download for free"
        assert not core.can_download(conn, peer, paid_tool), "Xiaoyouxia must not download before payment"

        stamp = core.now()
        cur = conn.execute(
            "INSERT INTO orders(order_no,user_id,tool_id,amount_cents,status,created_at) VALUES(?,?,?,?,?,?)",
            (f"CI-PENDING-{token}", peer_id, paid_tool_id, 1000, "pending", stamp),
        )
        pending_order = cur.lastrowid
        conn.execute(
            "INSERT INTO entitlements(user_id,tool_id,order_id,granted_at) VALUES(?,?,?,?)",
            (peer_id, paid_tool_id, pending_order, stamp),
        )
        assert not core.can_download(conn, peer, paid_tool), "pending order must not grant download"

        conn.execute(
            "UPDATE orders SET status='paid',paid_at=? WHERE id=?",
            (stamp, pending_order),
        )
        assert core.can_download(conn, peer, paid_tool), "nonzero paid order must grant download"

        cur = conn.execute(
            "INSERT INTO orders(order_no,user_id,tool_id,amount_cents,status,created_at,paid_at) VALUES(?,?,?,?,?,?,?)",
            (f"CI-ZERO-{token}", peer_id, free_entitlement_tool_id, 0, "paid", stamp, stamp),
        )
        zero_order = cur.lastrowid
        conn.execute(
            "INSERT INTO entitlements(user_id,tool_id,order_id,granted_at) VALUES(?,?,?,?)",
            (peer_id, free_entitlement_tool_id, zero_order, stamp),
        )
        assert not core.can_download(conn, peer, zero_tool), "zero-value paid order must not grant download"

    print("Business rule checks passed")
    print("- Xiaofeixia free download")
    print("- Xiaoyouxia requires nonzero paid entitlement")
    print("- Tool updates remain owner-only")


if __name__ == "__main__":
    main()
