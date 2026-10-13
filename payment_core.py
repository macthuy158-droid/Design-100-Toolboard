"""Website settlement boundary; provider signature verification lives in Pay100.

Never call settle() with browser-supplied payment results. A pending order must
be bound by trusted checkout code before Pay100 can settle it.
"""
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response

import app_v2 as site
import community_core as core

router = APIRouter()
PROVIDERS = {"wechat", "stripe"}


@router.get('/account/orders/{order_id}/status')
def order_status(request: Request, order_id: int):
    user = core.current_user(request)
    if not user:
        raise HTTPException(401, 'Login required')
    with site.db() as conn:
        order = conn.execute('SELECT status FROM orders WHERE id=? AND user_id=?',
                             (order_id, user['id'])).fetchone()
    if not order:
        raise HTTPException(404, 'Order not found')
    from fastapi.responses import JSONResponse
    return JSONResponse({'status': order['status']}, headers={'Cache-Control': 'no-store'})


def init_db():
    with site.db() as conn:
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(orders)')}
        if 'currency' not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY'")
        conn.executescript('''
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
        ''')


def bind_order(conn, order_id, provider):
    """Called by future server-side checkout, never a public provider selector."""
    if provider not in PROVIDERS:
        raise ValueError('unsupported provider')
    order = conn.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    if not order or order['status'] != 'pending' or order['amount_cents'] <= 0:
        raise ValueError('order is not payable')
    if order['provider'] not in ('', provider):
        raise ValueError('order already bound to another provider')
    if provider == 'wechat' and order['currency'] != 'CNY':
        raise ValueError('wechat requires CNY')
    conn.execute('UPDATE orders SET provider=? WHERE id=?', (provider, order_id))


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
    order = conn.execute('SELECT * FROM orders WHERE order_no=?', (event['order_no'],)).fetchone()
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
    conn.execute("UPDATE orders SET status='paid',provider_txn=?,paid_at=? WHERE id=?",
                 (event['transaction_id'], stamp, order['id']))
    conn.execute('INSERT OR IGNORE INTO entitlements(user_id,tool_id,order_id,granted_at) VALUES(?,?,?,?)',
                 (order['user_id'], order['tool_id'], order['id'], stamp))
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
