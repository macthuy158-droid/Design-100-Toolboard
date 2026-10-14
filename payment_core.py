"""Cash tool/course orders and settlement; provider verification lives in Pay100.

Never call settle() with browser-supplied payment results. A pending order must
be bound by trusted checkout code before Pay100 can settle it.
"""
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Form, HTTPException, Request, Response

import app_v2 as site
import community_core as core

router = APIRouter()
PROVIDERS = {"wechat", "stripe"}
STATUS_LABELS = {"pending": "待付款", "paid": "已付款", "cancelled": "已取消", "refunded": "已退款"}


@router.get('/account/purchases/{order_id}/status')
def order_status(request: Request, order_id: int):
    user = core.current_user(request)
    if not user:
        raise HTTPException(401, 'Login required')
    with site.db() as conn:
        order = conn.execute('SELECT status FROM purchase_orders WHERE id=? AND user_id=?',
                             (order_id, user['id'])).fetchone()
    if not order:
        raise HTTPException(404, 'Order not found')
    from fastapi.responses import JSONResponse
    return JSONResponse({'status': order['status']}, headers={'Cache-Control': 'no-store'})


def init_db():
    with site.db() as conn:
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(tools)')}
        if 'legacy_coin_only' not in cols:
            conn.execute('ALTER TABLE tools ADD COLUMN legacy_coin_only INTEGER NOT NULL DEFAULT 0')
            conn.execute('UPDATE tools SET legacy_coin_only=1 WHERE price_cents=0 AND feixia_coin_price>0')
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES community_users(id),
            product_type TEXT NOT NULL CHECK(product_type IN ('tool','course')),
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            seller_user_id INTEGER,
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'pending',
            provider TEXT NOT NULL DEFAULT '',
            provider_txn TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            paid_at TEXT,
            code_url TEXT NOT NULL DEFAULT '',
            expires_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_pending
        ON purchase_orders(user_id,product_type,product_id) WHERE status='pending';
        CREATE TABLE IF NOT EXISTS purchase_entitlements (
            user_id INTEGER NOT NULL REFERENCES community_users(id),
            product_type TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
            granted_at TEXT NOT NULL,
            PRIMARY KEY(user_id,product_type,product_id)
        );
        CREATE TABLE IF NOT EXISTS payment_events (
            provider TEXT NOT NULL,
            event_id TEXT NOT NULL,
            order_no TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            received_at TEXT NOT NULL,
            PRIMARY KEY(provider,event_id),
            UNIQUE(provider,transaction_id)
        );
        CREATE INDEX IF NOT EXISTS idx_purchase_seller ON purchase_orders(seller_user_id,status);
        """)


def bind_order(conn, order_id, provider):
    """Bind in trusted server-side checkout, never from a browser amount."""
    if provider not in PROVIDERS:
        raise ValueError('unsupported provider')
    order = conn.execute('SELECT * FROM purchase_orders WHERE id=?', (order_id,)).fetchone()
    if not order or order['status'] != 'pending' or order['amount_cents'] <= 0:
        raise ValueError('order is not payable')
    if order['provider'] not in ('', provider):
        raise ValueError('order already bound to another provider')
    if provider == 'wechat' and order['currency'] != 'CNY':
        raise ValueError('wechat requires CNY')
    conn.execute('UPDATE purchase_orders SET provider=? WHERE id=?', (provider, order_id))


def settle(conn, event):
    """Validate immutable order facts and atomically grant tool access once."""
    required = {'provider', 'event_id', 'order_no', 'transaction_id', 'amount_minor', 'currency'}
    if set(event) != required:
        raise ValueError('invalid event fields')
    for key in required - {'amount_minor'}:
        if not isinstance(event[key], str) or not event[key] or len(event[key]) > 200:
            raise ValueError('invalid event value')
    if event['provider'] not in PROVIDERS or type(event['amount_minor']) is not int or event['amount_minor'] <= 0:
        raise ValueError('invalid provider or amount')
    # Serialize settlement and prevent concurrent notifications granting twice.
    conn.execute('BEGIN IMMEDIATE')
    order = conn.execute('SELECT * FROM purchase_orders WHERE order_no=?', (event['order_no'],)).fetchone()
    if not order:
        raise ValueError('unknown order')
    if (order['provider'] != event['provider'] or order['amount_cents'] != event['amount_minor']
            or order['currency'] != event['currency']):
        raise ValueError('payment does not match order')
    previous = conn.execute(
        'SELECT * FROM payment_events WHERE provider=? AND (event_id=? OR transaction_id=?)',
        (event['provider'], event['event_id'], event['transaction_id']),
    ).fetchall()
    for row in previous:
        if any(row[k] != event[k] for k in required - {'event_id'}):
            raise ValueError('event or transaction reused for another payment')
    if order['status'] == 'paid':
        if order['provider_txn'] != event['transaction_id']:
            raise ValueError('order already paid by another transaction')
        return False
    if order['status'] != 'pending':
        raise ValueError('order is not pending')
    if previous:
        raise ValueError('inconsistent settlement state')
    stamp = core.now()
    conn.execute(
        'INSERT INTO payment_events VALUES(?,?,?,?,?,?,?)',
        (event['provider'], event['event_id'], event['order_no'], event['transaction_id'],
         event['amount_minor'], event['currency'], stamp),
    )
    conn.execute("UPDATE purchase_orders SET status='paid',provider_txn=?,paid_at=? WHERE id=?",
                 (event['transaction_id'], stamp, order['id']))
    conn.execute('INSERT OR IGNORE INTO purchase_entitlements VALUES(?,?,?,?,?)',
                 (order['user_id'], order['product_type'], order['product_id'], order['id'], stamp))
    return True


def verify_bridge(body, timestamp, signature, secret, now=None):
    if len(secret.encode()) < 32:
        raise ValueError('bridge secret is not configured')
    if not timestamp.isdigit() or abs((time.time() if now is None else now) - int(timestamp)) > 300:
        raise ValueError('stale notification')
    expected = hmac.new(secret.encode(), timestamp.encode() + b'\n' + body,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError('invalid signature')


@router.post('/api/payments/settled')
async def payment_settled(request: Request):
    secret = os.getenv('PAY100_BRIDGE_SECRET', '')
    if len(secret.encode()) < 32:
        raise HTTPException(503, 'Payment bridge is not configured')
    # Limit actual streamed bytes, including requests without Content-Length.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 8192:
            raise HTTPException(413, 'Notification too large')
    try:
        verify_bridge(bytes(body), request.headers.get('X-Pay100-Timestamp', ''),
                      request.headers.get('X-Pay100-Signature', ''), secret)
    except ValueError:
        raise HTTPException(401, 'Invalid payment notification')
    try:
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError('invalid event')
        with site.db() as conn:
            settle(conn, event)
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(409, 'Payment does not match order')
    return Response(status_code=204)


def has_access(conn, user_id, product_type, product_id):
    return bool(conn.execute('''SELECT 1 FROM purchase_entitlements e
        JOIN purchase_orders o ON o.id=e.order_id
        WHERE e.user_id=? AND e.product_type=? AND e.product_id=? AND o.status='paid' ''',
        (user_id, product_type, product_id)).fetchone())


def yuan_to_cents(value):
    from decimal import Decimal, InvalidOperation
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 100000 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError('invalid price')
        return int(amount * 100)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, '价格须为 0—100000 元，最多两位小数。')


def csrf_token(request, admin=False):
    token = request.cookies.get(site.COOKIE_NAME if admin else core.USER_COOKIE, '')
    return hmac.new(core.SESSION_SECRET.encode(), (('admin-price:' if admin else 'purchase:') + token).encode(), hashlib.sha256).hexdigest()


def check_csrf(request, token, admin=False):
    if not token or not hmac.compare_digest(csrf_token(request, admin=admin), token):
        raise HTTPException(403, '请刷新页面后重试。')


def create_purchase(conn, user, product_type, product_id):
    import secrets
    conn.execute('BEGIN IMMEDIATE')
    if product_type == 'tool':
        product = conn.execute('SELECT * FROM tools WHERE id=? AND active=1', (product_id,)).fetchone()
        if not product:
            raise HTTPException(404, '工具不存在。')
        if product['tool_type'] == 'web_app':
            raise HTTPException(409, '网页工具暂不支持直接购买。')
        if core.can_download(conn, user, product):
            raise HTTPException(409, '你已可下载该工具，无需购买。')
        name, seller = product['name'], product['owner_user_id']
    elif product_type == 'course':
        import course_portal
        product = conn.execute("SELECT * FROM courses WHERE id=? AND status='published'", (product_id,)).fetchone()
        if not product:
            raise HTTPException(404, '课程不存在。')
        if course_portal.can_learn(conn, user, product):
            raise HTTPException(409, '你已可学习该课程，无需购买。')
        name, seller = product['title'], None
    else:
        raise HTTPException(400, '不支持该商品类型。')
    amount = int(product['price_cents'])
    if amount <= 0:
        raise HTTPException(409, '商品现金售价待确认，暂不接受购买。')
    existing = conn.execute("SELECT id FROM purchase_orders WHERE user_id=? AND product_type=? AND product_id=? AND status='pending'",
                            (user['id'], product_type, product_id)).fetchone()
    if existing:
        return existing['id']
    cursor = conn.execute('''INSERT INTO purchase_orders(order_no,user_id,product_type,product_id,
        product_name,seller_user_id,amount_cents,created_at) VALUES(?,?,?,?,?,?,?,?)''',
        ('D100' + secrets.token_hex(12).upper(), user['id'], product_type, product_id,
         name, seller, amount, core.now()))
    return cursor.lastrowid


def gateway_ready():
    from urllib.parse import urlsplit
    base = urlsplit(os.getenv('PAY100_GATEWAY_URL', ''))
    return (os.getenv('PAY100_CHECKOUT_ENABLED', '') == '1' and base.scheme == 'https'
            and bool(base.netloc) and not base.username and not base.password and not base.query
            and not base.fragment and len(os.getenv('PAY100_BRIDGE_SECRET', '').encode()) >= 32)


def gateway_checkout(order):
    """Proposed Pay100 contract. Disabled until its backend implements this API."""
    from urllib.request import Request as URLRequest
    from urllib.error import URLError
    secret = os.environ['PAY100_BRIDGE_SECRET']
    data = dict(order_no=order['order_no'], amount_minor=order['amount_cents'], currency=order['currency'],
                description=order['product_name'].encode('utf-8')[:127].decode('utf-8', errors='ignore'), provider='wechat')
    body = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
    req = URLRequest(os.environ['PAY100_GATEWAY_URL'].rstrip('/') + '/api/checkout', data=body,
                     headers={'Content-Type': 'application/json', 'X-Pay100-Timestamp': timestamp,
                              'X-Pay100-Signature': signature}, method='POST')
    try:
        # No redirects: forwarding a signed request to another host is not allowed.
        from urllib.request import HTTPRedirectHandler, build_opener
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(NoRedirect).open(req, timeout=10) as response:
            raw = response.read(8193)
            if len(raw) > 8192:
                raise ValueError('oversize response')
            verify_bridge(raw, response.headers.get('X-Pay100-Timestamp', ''),
                          response.headers.get('X-Pay100-Signature', ''), secret)
            result = json.loads(raw)
        if (result['order_no'] != order['order_no'] or result['amount_minor'] != order['amount_cents']
                or result['currency'] != order['currency'] or result['provider'] != 'wechat'
                or not isinstance(result['code_url'], str) or not result['code_url'].startswith('weixin://')
                or len(result['code_url']) > 2048 or type(result['expires_at']) is not int
                or result['expires_at'] <= time.time()):
            raise ValueError('gateway response does not match order')
        return result
    except (URLError, OSError, ValueError, KeyError, TypeError):
        raise HTTPException(502, '暂时无法生成付款二维码，请稍后重试。')


@router.post('/account/purchases/new/{product_type}/{product_id}')
def purchase(request: Request, product_type: str, product_id: int, csrf: str = Form('')):
    from fastapi.responses import RedirectResponse
    user = core.current_user(request)
    if not user:
        raise HTTPException(401, '请先登录。')
    check_csrf(request, csrf)
    with site.db() as conn:
        oid = create_purchase(conn, user, product_type, product_id)
    return RedirectResponse(f'/account/purchases/{oid}', 303)


def owned_order(conn, request, order_id):
    user = core.current_user(request)
    if not user:
        raise HTTPException(401, '请先登录。')
    order = conn.execute('SELECT * FROM purchase_orders WHERE id=? AND user_id=?', (order_id, user['id'])).fetchone()
    if not order:
        raise HTTPException(404, '订单不存在。')
    return order


@router.post('/account/purchases/{order_id}/wechat')
def wechat_checkout(request: Request, order_id: int, csrf: str = Form('')):
    from fastapi.responses import RedirectResponse
    check_csrf(request, csrf)
    if not gateway_ready():
        raise HTTPException(503, '微信支付正在准备中。')
    # Commit channel binding before remote call so a timeout cannot unbind the order.
    with site.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        order = owned_order(conn, request, order_id)
        if order['status'] == 'paid':
            return RedirectResponse(f'/account/purchases/{order_id}', 303)
        if order['code_url']:
            return RedirectResponse(f'/account/purchases/{order_id}', 303)
        try:
            bind_order(conn, order_id, 'wechat')
        except ValueError:
            raise HTTPException(409, '订单暂不可支付。')
    result = gateway_checkout(order)
    with site.db() as conn:
        conn.execute("UPDATE purchase_orders SET code_url=?,expires_at=? WHERE id=? AND status='pending' AND provider='wechat'",
                     (result['code_url'], result['expires_at'], order_id))
    return RedirectResponse(f'/account/purchases/{order_id}', 303)


@router.get('/account/purchases/{order_id}/qr')
def checkout_qr(request: Request, order_id: int):
    import qrcode
    from qrcode.image.svg import SvgPathImage
    with site.db() as conn:
        order = owned_order(conn, request, order_id)
    if order['status'] != 'pending' or not order['code_url'] or order['expires_at'] <= time.time():
        raise HTTPException(409, '二维码已失效。')
    import io
    buffer = io.BytesIO()
    qrcode.make(order['code_url'], image_factory=SvgPathImage).save(buffer)
    return Response(buffer.getvalue(), media_type='image/svg+xml', headers={'Cache-Control': 'no-store'})


@router.get('/account/purchases/{order_id}')
def purchase_page(request: Request, order_id: int):
    from fastapi.responses import HTMLResponse
    with site.db() as conn:
        order = owned_order(conn, request, order_id)
        if order['product_type'] == 'tool':
            product = conn.execute('SELECT slug FROM tools WHERE id=?', (order['product_id'],)).fetchone()
            target = '/tools/' + product['slug'] if product else '/tools'
        else:
            target = '/courses/' + str(order['product_id'])
    status = STATUS_LABELS.get(order['status'], '订单处理中')
    if order['status'] == 'paid':
        action = f'<p>购买成功，权益已开通。</p><a class="btn" href="{site.esc(target)}">查看商品</a>'
    elif order['status'] != 'pending':
        action = '<p>此订单暂不可支付。</p>'
    elif order['code_url'] and order['expires_at'] > time.time():
        action = f'<p>请用手机微信扫码付款。</p><img src="/account/purchases/{order_id}/qr" alt="微信付款二维码" width="240" height="240"><p id="pay-status">付款后会自动更新订单状态。</p>'
    elif order['code_url']:
        action = '<p>二维码已过期，请联系平台核对订单状态后再付款。</p>'
    elif gateway_ready():
        action = f'<form method="post" action="/account/purchases/{order_id}/wechat"><input type="hidden" name="csrf" value="{csrf_token(request)}"><button class="btn">微信支付</button></form>'
    else:
        action = '<p>微信支付正在准备中，暂时无法付款。</p>'
    extra = ''
    if order['status'] == 'pending':
        extra = f'''<script>(()=>{{let n=0;const timer=setInterval(async()=>{{if(++n>180){{clearInterval(timer);return;}}try{{const r=await fetch('/account/purchases/{order_id}/status',{{cache:'no-store'}});if(r.status===401){{clearInterval(timer);return;}}if(r.ok&&(await r.json()).status==='paid'){{clearInterval(timer);location.reload();}}}}catch(e){{}}}},5000);}})();</script>'''
    body = f'''<div style="max-width:640px;margin:48px auto;padding:28px;background:white;border-radius:24px"><p>订单 {site.esc(order['order_no'])} · {status}</p><h1>{site.esc(order['product_name'])}</h1><h2>¥{order['amount_cents']/100:.2f}</h2><p>人民币直接购买，付款后开通权益。</p>{action}<p><a href="{site.esc(target)}">返回商品</a> · <a href="/account/me">我的购买</a></p></div>'''
    return HTMLResponse(site.page(body, '订单 · 小飞侠设计100%', extra), headers={'Cache-Control': 'no-store'})
