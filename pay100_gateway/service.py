"""Pay100 Native gateway. Run independently of the website; never copy secrets here."""
import asyncio
import hashlib
import hmac
import json
import logging
import re
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

LOG = logging.getLogger('pay100')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def signed_headers(body, secret):
    stamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), stamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
    return {'Content-Type': 'application/json', 'X-Pay100-Timestamp': stamp,
            'X-Pay100-Signature': signature}


def check_signature(body, headers, secret):
    stamp = headers.get('X-Pay100-Timestamp', '')
    try:
        if abs(time.time() - int(stamp)) > 300:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(401, 'invalid bridge timestamp')
    expected = hmac.new(secret.encode(), stamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, headers.get('X-Pay100-Signature', '')):
        raise HTTPException(401, 'invalid bridge signature')


def https_url(url):
    p = urlsplit(url)
    return p.scheme == 'https' and bool(p.netloc) and not (p.username or p.password or p.fragment or p.query)


class Gateway:
    def __init__(self, db_path, sdk, appid, mchid, public_key_id, secret, settlement_url):
        if len(secret.encode()) < 32 or not https_url(settlement_url):
            raise ValueError('Configure a separate 32-byte bridge secret and HTTPS settlement URL')
        self.db_path, self.sdk = Path(db_path), sdk
        self.appid, self.mchid, self.public_key_id = appid, mchid, public_key_id
        self.secret, self.settlement_url = secret, settlement_url
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            # Do not alter the existing payment_orders table or historical TEST payments.
            c.executescript('''
                CREATE TABLE IF NOT EXISTS gateway_orders (
                    order_no TEXT PRIMARY KEY, amount_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL, description TEXT NOT NULL,
                    expires_at INTEGER NOT NULL, code_url TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    transaction_id TEXT UNIQUE, paid_at TEXT,
                    next_query INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS gateway_outbox (
                    order_no TEXT PRIMARY KEY REFERENCES gateway_orders(order_no),
                    event_id TEXT UNIQUE NOT NULL, payload BLOB NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0
                );
            ''')

    def connect(self):
        c = sqlite3.connect(self.db_path, timeout=20)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def checkout(self, data):
        if not isinstance(data, dict) or set(data) != {'order_no', 'amount_minor', 'currency', 'description', 'provider'}:
            raise HTTPException(400, 'invalid checkout fields')
        order_no, amount, desc = data['order_no'], data['amount_minor'], data['description']
        if (not isinstance(order_no, str) or not re.fullmatch(r'D100[A-Z0-9]{1,28}', order_no)
                or type(amount) is not int or not 1 <= amount <= 100000000
                or data['currency'] != 'CNY' or data['provider'] != 'wechat'
                or not isinstance(desc, str) or not 1 <= len(desc.encode()) <= 127):
            raise HTTPException(400, 'invalid checkout values')
        # Persist immutable binding BEFORE the network call. Ambiguous requests retry the same
        # merchant order number and deadline, never manufacture a replacement order.
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM gateway_orders WHERE order_no=?', (order_no,)).fetchone()
            if row and (row['amount_minor'], row['currency'], row['description']) != (amount, 'CNY', desc):
                raise HTTPException(409, 'order snapshot mismatch')
            if not row:
                c.execute('INSERT INTO gateway_orders(order_no,amount_minor,currency,description,expires_at) VALUES(?,?,?,?,?)',
                          (order_no, amount, 'CNY', desc, int(time.time()) + 900))
            c.commit()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM gateway_orders WHERE order_no=?', (order_no,)).fetchone()
            if row['status'] != 'PENDING' or row['expires_at'] <= time.time():
                raise HTTPException(409, 'order paid, closed or expired; query before any replacement')
            code_url = row['code_url']
            if not code_url:
                deadline = datetime.fromtimestamp(row['expires_at'], timezone.utc).isoformat()
                try:
                    code, raw = self.sdk.pay(description=desc, out_trade_no=order_no,
                                             amount={'total': amount, 'currency': 'CNY'}, time_expire=deadline)
                    result = json.loads(raw)
                    code_url = result.get('code_url')
                    if code != 200 or not isinstance(code_url, str) or not code_url.startswith('weixin://') or len(code_url) > 2048:
                        raise ValueError()
                except Exception:
                    # Never expose SDK responses, credentials or payer details to clients.
                    raise HTTPException(502, 'wechat checkout unavailable') from None
                c.execute('UPDATE gateway_orders SET code_url=? WHERE order_no=?', (code_url, order_no))
        return dict(order_no=order_no, amount_minor=amount, currency='CNY', provider='wechat',
                    code_url=code_url, expires_at=row['expires_at'])

    def settle(self, trade, event_id):
        if not isinstance(trade, dict) or trade.get('appid') != self.appid or trade.get('mchid') != self.mchid:
            raise HTTPException(400, 'merchant mismatch')
        if trade.get('trade_state') != 'SUCCESS':
            raise HTTPException(400, 'not a successful payment')
        if trade.get('trade_type') != 'NATIVE':
            raise HTTPException(400, 'trade type mismatch')
        no, txn = trade.get('out_trade_no'), trade.get('transaction_id')
        amount = trade.get('amount')
        if (not isinstance(no, str) or not isinstance(txn, str) or not 1 <= len(txn) <= 128
                or not isinstance(event_id, str) or not 1 <= len(event_id) <= 128
                or not isinstance(amount, dict) or type(amount.get('total')) is not int):
            raise HTTPException(400, 'invalid payment facts')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM gateway_orders WHERE order_no=?', (no,)).fetchone()
            if not row:
                raise HTTPException(400, 'unknown order')
            if (amount['total'], amount.get('currency')) != (row['amount_minor'], row['currency']):
                raise HTTPException(400, 'amount or currency mismatch')
            if row['status'] == 'PAID':
                if row['transaction_id'] != txn:
                    raise HTTPException(409, 'transaction mismatch')
                return
            payload = encode(dict(provider='wechat', event_id=event_id, order_no=no,
                                  transaction_id=txn, amount_minor=row['amount_minor'], currency=row['currency']))
            try:
                c.execute("UPDATE gateway_orders SET status='PAID',transaction_id=?,paid_at=? WHERE order_no=?",
                          (txn, trade.get('success_time'), no))
                c.execute('INSERT INTO gateway_outbox(order_no,event_id,payload) VALUES(?,?,?)', (no, event_id, payload))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'transaction or event already bound') from None

    def notify(self, headers, body):
        try:
            stamp = int(headers.get('Wechatpay-Timestamp', ''))
            if abs(time.time() - stamp) > 300 or headers.get('Wechatpay-Serial') != self.public_key_id:
                raise ValueError()
            # Pass unchanged bytes. SDK performs RSA signature verification and AES-GCM decryption.
            event = self.sdk.callback(headers=headers, body=body)
            if not isinstance(event, dict) or event.get('event_type') != 'TRANSACTION.SUCCESS':
                raise ValueError()
        except Exception:
            raise HTTPException(401, 'invalid wechat notification') from None
        self.settle(event.get('resource'), event.get('id'))

    def query(self, no):
        if not isinstance(no, str) or not re.fullmatch(r'D100[A-Z0-9]{1,28}', no):
            raise HTTPException(400, 'invalid order number')
        with self.connect() as c:
            row = c.execute('SELECT * FROM gateway_orders WHERE order_no=?', (no,)).fetchone()
        if not row:
            raise HTTPException(404, 'unknown order')
        if row['status'] != 'PAID':
            try:
                code, raw = self.sdk.query(out_trade_no=no)
                trade = json.loads(raw)
                if code != 200:
                    raise ValueError()
            except Exception:
                raise HTTPException(502, 'wechat query unavailable') from None
            if trade.get('out_trade_no') != no or trade.get('appid') != self.appid or trade.get('mchid') != self.mchid:
                raise HTTPException(502, 'wechat query identity mismatch')
            if trade.get('trade_state') == 'SUCCESS':
                self.settle(trade, 'query:' + trade.get('transaction_id', ''))
            elif trade.get('trade_state') in ('CLOSED', 'REVOKED'):
                with self.connect() as c:
                    c.execute("UPDATE gateway_orders SET status='CLOSED' WHERE order_no=? AND status='PENDING'", (no,))
        with self.connect() as c:
            row = c.execute('SELECT * FROM gateway_orders WHERE order_no=?', (no,)).fetchone()
        return dict(order_no=no, status=row['status'], amount_minor=row['amount_minor'], currency=row['currency'])

    def reconcile(self):
        with self.connect() as c:
            rows = c.execute("SELECT order_no FROM gateway_orders WHERE status='PENDING' AND next_query<=? LIMIT 20",
                             (int(time.time()),)).fetchall()
        for row in rows:
            no = row['order_no']
            with self.connect() as c:
                c.execute('UPDATE gateway_orders SET next_query=? WHERE order_no=?', (int(time.time()) + 60, no))
            try:
                self.query(no)
            except Exception:
                LOG.warning('Payment query pending; will retry')

    def deliver(self, client=None):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM gateway_outbox WHERE delivered=0 AND next_attempt<=? LIMIT 20',
                             (int(time.time()),)).fetchall()
        owned = client is None
        if owned:
            client = httpx.Client(timeout=10, follow_redirects=False)
        try:
            for row in rows:
                done = False
                try:
                    response = client.post(self.settlement_url, content=row['payload'],
                                           headers=signed_headers(row['payload'], self.secret))
                    done = response.status_code == 204
                except Exception:
                    pass
                attempt = row['attempts'] + 1
                with self.connect() as c:
                    c.execute('UPDATE gateway_outbox SET delivered=?,attempts=?,next_attempt=? WHERE order_no=?',
                              (int(done), attempt, int(time.time()) + min(3600, 2 ** min(attempt, 12)), row['order_no']))
                if not done:
                    LOG.warning('Settlement delivery pending; will retry')
        finally:
            if owned:
                client.close()


def create_app(gateway, run_worker=True):
    async def worker():
        while True:
            try:
                await asyncio.to_thread(gateway.deliver)
                await asyncio.to_thread(gateway.reconcile)
            except Exception:
                LOG.exception('Payment worker failed; will retry')
            await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker()) if run_worker else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title='Pay100', lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get('/')
    def home():
        return {'service': 'pay100', 'status': 'running'}

    @app.get('/health')
    def health():
        return {'ok': True}

    async def bridge_body(request):
        body = await request.body()
        if len(body) > 8192:
            raise HTTPException(413, 'request too large')
        check_signature(body, request.headers, gateway.secret)
        try:
            return json.loads(body)
        except (ValueError, UnicodeError):
            raise HTTPException(400, 'invalid JSON') from None

    def signed_response(value):
        body = encode(value)
        return Response(body, media_type='application/json', headers=signed_headers(body, gateway.secret))

    @app.post('/api/checkout')
    async def checkout(request: Request):
        data = await bridge_body(request)
        return signed_response(await asyncio.to_thread(gateway.checkout, data))

    @app.post('/api/orders/query')
    async def query(request: Request):
        data = await bridge_body(request)
        if not isinstance(data, dict) or set(data) != {'order_no'}:
            raise HTTPException(400, 'invalid query fields')
        return signed_response(await asyncio.to_thread(gateway.query, data['order_no']))

    @app.post('/api/wechat/notify')
    async def notify(request: Request):
        body = await request.body()
        if len(body) > 65536:
            raise HTTPException(413, 'request too large')
        await asyncio.to_thread(gateway.notify, request.headers, body)
        return Response(status_code=204)

    return app
