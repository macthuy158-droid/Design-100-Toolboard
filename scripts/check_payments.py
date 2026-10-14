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
        order_tool = add_tool(conn, 'test-' + number.lower(), None, coin_price=50, price_cents=100)
        cursor = conn.execute("INSERT INTO purchase_orders(order_no,user_id,product_type,product_id,product_name,amount_cents,created_at) VALUES(?,?,'tool',?,'Pay tool',?,?)",
                              (number, buyer, order_tool, 100, core.now()))
        if number != 'UNBOUND':
            payments.bind_order(conn, cursor.lastrowid, 'wechat')
    oid = conn.execute("SELECT id FROM purchase_orders WHERE order_no='PAY1'").fetchone()['id']

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
    assert conn.execute('SELECT COUNT(*) FROM purchase_entitlements').fetchone()[0] == 1

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
assert client.get(f'/account/purchases/{oid}/status').status_code == 401
client.cookies.set(core.USER_COOKIE, core.make_session(other))
assert client.get(f'/account/purchases/{oid}/status').status_code == 404
buyer_session = core.make_session(buyer)
client.cookies.set(core.USER_COOKIE, buyer_session)
result = client.get(f'/account/purchases/{oid}/status')
assert result.json() == {'status': 'paid'}
assert result.headers['cache-control'] == 'no-store'


# Cash-only tools cannot be downloaded for free or bought with zero points.
from unittest.mock import patch
import course_portal
with site.db() as conn:
    owner = add_user(conn, 'cash-owner')
    cash = add_tool(conn, 'cash-only', owner, coin_price=0, price_cents=9900)
    t = conn.execute('SELECT * FROM tools WHERE id=?', (cash,)).fetchone()
    buyer_row = conn.execute('SELECT * FROM community_users WHERE id=?', (buyer,)).fetchone()
    assert not core.can_download(conn, buyer_row, t)
    assert core.can_download(conn, conn.execute('SELECT * FROM community_users WHERE id=?', (owner,)).fetchone(), t)
    assert payments.yuan_to_cents('99.99') == 9999
    for value in ('NaN', 'Infinity', '-1', '1.001', '100001'):
        try:
            payments.yuan_to_cents(value)
        except Exception as error:
            assert getattr(error, 'status_code', 0) == 400
        else:
            raise AssertionError('invalid price accepted')
    stamp = core.now()
    cid = conn.execute("INSERT INTO courses(title,price_cents,status,created_at,updated_at) VALUES('Paid course',12345,'published',?,?)", (stamp,stamp)).lastrowid
    lesson = conn.execute("INSERT INTO course_lessons(course_id,title,video_url,created_at) VALUES(?,'Lesson','https://example.com/private-video',?)", (cid,stamp)).lastrowid

assert client.post(f'/account/purchases/new/tool/{cash}').status_code == 403
# Obtain the session-bound form token from a real product page.
import re
html = client.get('/tools/cash-only').text
assert '购买工具 · ¥99.00' in html
assert '社区兑换 ·' not in html
assert '/tools/cash-only/download' not in html
csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', html).group(1)
response = client.post(f'/account/purchases/new/tool/{cash}', data={'csrf':csrf, 'amount_minor':1}, follow_redirects=False)
assert response.status_code == 303
cash_url = response.headers['location']
assert client.post(f'/account/purchases/new/tool/{cash}', data={'csrf':csrf}, follow_redirects=False).headers['location'] == cash_url
with site.db() as conn:
    co = conn.execute('SELECT * FROM purchase_orders WHERE id=?', (int(cash_url.rsplit('/',1)[1]),)).fetchone()
    assert co['amount_cents'] == 9900
    conn.execute('UPDATE tools SET price_cents=10000 WHERE id=?', (cash,))
assert '¥99.00' in client.get(cash_url).text
assert client.post(cash_url+'/wechat', data={'csrf':csrf}).status_code == 503
assert 'private-video' not in client.get(f'/courses/{cid}').text
assert client.post(f'/courses/{cid}/enroll').status_code == 409
course_response = client.post(f'/account/purchases/new/course/{cid}', data={'csrf':csrf}, follow_redirects=False)
assert course_response.status_code == 303
course_oid = int(course_response.headers['location'].rsplit('/',1)[1])
with site.db() as conn:
    payments.bind_order(conn, course_oid, 'wechat')
    course_order = conn.execute('SELECT * FROM purchase_orders WHERE id=?', (course_oid,)).fetchone()
deliver(dict(provider='wechat',event_id='course-event',order_no=course_order['order_no'],transaction_id='course-txn',amount_minor=12345,currency='CNY'))
assert 'private-video' in client.get(f'/courses/{cid}').text
assert 'Paid course' in client.get('/courses/mine').text
assert 'Paid course' in client.get('/account/me').text
assert client.post(f'/account/purchases/new/course/{cid}',data={'csrf':csrf}).status_code == 409

# Test the website checkout using a simulated, authenticated gateway result.
os.environ['PAY100_BRIDGE_SECRET'] = secret
os.environ['PAY100_GATEWAY_URL'] = 'https://pay100.cloud'
os.environ['PAY100_CHECKOUT_ENABLED'] = '1'
with patch.object(payments,'gateway_checkout',return_value=dict(code_url='weixin://test-pay',expires_at=int(time.time())+600)):
    assert client.post(cash_url+'/wechat',data={'csrf':csrf},follow_redirects=False).status_code == 303
assert client.get(cash_url+'/qr').status_code == 200
assert 'image/svg+xml' in client.get(cash_url+'/qr').headers['content-type']
client.cookies.set(core.USER_COOKIE,core.make_session(other))
assert client.get(cash_url).status_code == 404
assert client.get(cash_url+'/qr').status_code == 404
client.cookies.set(core.USER_COOKIE,buyer_session)
deliver(dict(provider='wechat',event_id='cash-event',order_no=co['order_no'],transaction_id='cash-txn',amount_minor=9900,currency='CNY'))
assert client.get(cash_url+'/qr').status_code == 409
with site.db() as conn:
    tool_row=conn.execute('SELECT * FROM tools WHERE id=?',(cash,)).fetchone()
    assert core.can_download(conn,buyer_row,tool_row)
    import coin_core
    assert coin_core.has_access(conn,buyer,tool_row["id"]) is False
assert '购买成功' in client.get(cash_url).text
assert '¥99.00' in client.get('/account/me').text
# Verify list views and admin read access without writing real state.
assert client.get('/courses').status_code == 200
assert '¥123.45' in client.get('/courses').text
assert client.get('/tools').status_code == 200
assert client.get('/manage/community/purchases', follow_redirects=False).status_code in (303,401,403)
with patch('admin_portal.require_admin', return_value=None):
    result=client.get('/manage/community/purchases')
    assert result.status_code == 200 and 'cash-txn' in result.text
# Legacy points-only tools stay protected, while new zero-cash tools are free.
with site.db() as conn:
    legacy = add_tool(conn,'points-legacy',owner,coin_price=50)
    conn.execute('UPDATE tools SET legacy_coin_only=1 WHERE id=?',(legacy,))
    assert not core.can_download(conn,buyer_row,conn.execute('SELECT * FROM tools WHERE id=?',(legacy,)).fetchone())
    free = add_tool(conn,'new-free',owner,coin_price=50)
    assert core.can_download(conn,buyer_row,conn.execute('SELECT * FROM tools WHERE id=?',(free,)).fetchone())
    assert not coin_core.has_access(conn,buyer,free)
# Retired points cannot be redeemed, including during a cash checkout.
with site.db() as conn:
    exchange = add_tool(conn,'exchange-both',owner,coin_price=10,price_cents=2500)
    coin_core._record(conn,buyer,100,'admin_adjust',ref='historical-test-award')
exchange_result=client.post(f'/account/purchases/new/tool/{exchange}',data={'csrf':csrf},follow_redirects=False)
exchange_oid=int(exchange_result.headers['location'].rsplit('/',1)[1])
with site.db() as conn:
    payments.bind_order(conn,exchange_oid,'wechat')
assert client.post('/account/tools/exchange-both/coin-unlock',data={'csrf':csrf}).status_code == 410
with site.db() as conn:
    assert coin_core.balance(conn,buyer) == 100
# Owner-only cash pricing and CSRF protections.
assert client.post('/account/tools/exchange-both/cash-price',data={'csrf':csrf,'price_yuan':'1'}).status_code == 403
client.cookies.set(core.USER_COOKIE,core.make_session(owner))
owner_html=client.get('/account/me').text
owner_csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',owner_html).group(1)
assert client.post('/account/tools/exchange-both/cash-price',data={'price_yuan':'2'}).status_code == 403
assert client.post('/account/tools/exchange-both/cash-price',data={'csrf':owner_csrf,'price_yuan':'2.50'},follow_redirects=False).status_code == 303
with site.db() as conn:
    assert conn.execute('SELECT price_cents FROM tools WHERE id=?',(exchange,)).fetchone()[0] == 250
# Exercise the real gateway adapter with signed/tampered simulated responses.
class GatewayResponse:
    def __init__(self,payload,tamper=False):
        self.raw=json.dumps(payload).encode()
        ts=str(int(time.time()))
        sig=hmac.new(secret.encode(),ts.encode()+b'\n'+self.raw,hashlib.sha256).hexdigest()
        self.headers={'X-Pay100-Timestamp':ts,'X-Pay100-Signature':'bad' if tamper else sig}
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,limit): return self.raw[:limit]
class GatewayOpener:
    def __init__(self,response): self.response=response
    def open(self,request,timeout):
        assert request.full_url=='https://pay100.cloud/api/checkout'
        sent=json.loads(request.data)
        assert sent['amount_minor']==9900 and sent['order_no']==co['order_no']
        payments.verify_bridge(request.data,request.get_header('X-pay100-timestamp'),request.get_header('X-pay100-signature'),secret)
        return self.response
payload=dict(order_no=co['order_no'],amount_minor=9900,currency='CNY',provider='wechat',code_url='weixin://test',expires_at=int(time.time())+600)
with patch('urllib.request.build_opener',return_value=GatewayOpener(GatewayResponse(payload))):
    assert payments.gateway_checkout(co)['code_url']=='weixin://test'
for response in (GatewayResponse(payload,tamper=True),GatewayResponse({**payload,'amount_minor':1})):
    with patch('urllib.request.build_opener',return_value=GatewayOpener(response)):
        try:
            payments.gateway_checkout(co)
        except Exception as error:
            assert getattr(error,'status_code',0)==502
        else:
            raise AssertionError('untrusted gateway response accepted')
print('Payment checks passed: settlement, cash tools, courses, signed checkout, CSRF, legacy access and pricing')
