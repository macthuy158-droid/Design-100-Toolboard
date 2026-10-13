"""Settlement security checks against a disposable database; no real payments."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TOOLBOARD_DATA_DIR'] = tempfile.mkdtemp(prefix='payments-check-')
os.environ['PAY100_BRIDGE_SECRET'] = 'test-bridge-secret-' + 'x' * 32

from fastapi.testclient import TestClient
from app import app, public_site as site
import community_core as core
import payment_core as payments
from scripts.check_business_rules import add_user, add_tool


def rejected(event):
    try:
        with site.db() as conn:
            payments.settle(conn, event)
    except ValueError:
        return
    raise AssertionError('invalid event accepted')


def deliver(event):
    with site.db() as conn:
        return payments.settle(conn, event)


with site.db() as conn:
    buyer = add_user(conn, 'pay-buyer', core.ROLE_XIAOYOUXIA)
    other = add_user(conn, 'pay-other', core.ROLE_XIAOYOUXIA)
    tool = add_tool(conn, 'pay-tool', None, coin_price=50, price_cents=100)
    for number in ('PAY1', 'PAY2', 'UNBOUND'):
        cursor = conn.execute('INSERT INTO orders(order_no,user_id,tool_id,amount_cents,created_at) VALUES(?,?,?,?,?)',
                              (number, buyer, tool, 100, core.now()))
        if number != 'UNBOUND':
            payments.bind_order(conn, cursor.lastrowid, 'wechat')
    oid = conn.execute("SELECT id FROM orders WHERE order_no='PAY1'").fetchone()['id']

event = dict(provider='wechat', event_id='event1', order_no='PAY1',
             transaction_id='txn1', amount_minor=100, currency='CNY')
for mutation in ({'amount_minor': 1}, {'amount_minor': True}, {'currency': 'USD'},
                 {'provider': 'stripe'}, {'order_no': 'UNBOUND'}, {'order_no': 'missing'}):
    rejected({**event, **mutation})
with ThreadPoolExecutor(max_workers=2) as pool:
    assert sorted(pool.map(deliver, [event, event])) == [False, True]
assert deliver({**event, 'event_id': 'new-event-same-transaction'}) is False
rejected({**event, 'order_no': 'PAY2'})
rejected({**event, 'transaction_id': 'txn2'})
rejected({**event, 'order_no': 'PAY2', 'transaction_id': 'txn2'})
with site.db() as conn:
    assert conn.execute('SELECT COUNT(*) FROM payment_events').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM entitlements').fetchone()[0] == 1
assert core.grant_order(oid) is True
with site.db() as conn:
    assert conn.execute('SELECT provider FROM orders WHERE id=?', (oid,)).fetchone()[0] == 'wechat'
    oid2 = conn.execute("SELECT id FROM orders WHERE order_no='PAY2'").fetchone()[0]
assert core.grant_order(oid2) is False

client = TestClient(app)
body = json.dumps(event).encode()
timestamp = str(int(time.time()))
secret = os.environ['PAY100_BRIDGE_SECRET']
signature = hmac.new(secret.encode(), timestamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
headers = {'X-Pay100-Timestamp': timestamp, 'X-Pay100-Signature': signature}
assert client.post('/api/payments/settled', content=body, headers=headers).status_code == 204
assert client.post('/api/payments/settled', content=body + b' ', headers=headers).status_code == 401
assert client.post('/api/payments/settled', content=body).status_code == 401
old = str(int(timestamp) - 301)
old_sig = hmac.new(secret.encode(), old.encode() + b'\n' + body, hashlib.sha256).hexdigest()
assert client.post('/api/payments/settled', content=body, headers={
    'X-Pay100-Timestamp': old, 'X-Pay100-Signature': old_sig}).status_code == 401
assert client.post('/api/payments/settled', content=b'x' * 8193).status_code == 413
os.environ.pop('PAY100_BRIDGE_SECRET')
assert client.post('/api/payments/settled', content=body, headers=headers).status_code == 503
assert client.get(f'/account/orders/{oid}/status').status_code == 401
client.cookies.set(core.USER_COOKIE, core.make_session(other))
assert client.get(f'/account/orders/{oid}/status').status_code == 404
client.cookies.set(core.USER_COOKIE, core.make_session(buyer))
result = client.get(f'/account/orders/{oid}/status')
assert result.json() == {'status': 'paid'}
assert result.headers['cache-control'] == 'no-store'
print('Payment settlement checks passed')
