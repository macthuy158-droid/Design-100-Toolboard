"""Offline gateway security tests; no real merchant credentials or charges."""
import base64
import concurrent.futures
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from fastapi.testclient import TestClient
from wechatpayv3 import WeChatPay, WeChatPayType
from pay100_gateway.service import Gateway, check_signature, create_app, encode, signed_headers


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sdk = Mock()
        self.sdk.pay.return_value = (200, '{"code_url":"weixin://test"}')
        self.secret = 'offline-test-bridge-secret-32-bytes-plus'
        self.g = Gateway(Path(self.tmp.name) / 'pay100.db', self.sdk, 'app', 'merchant', 'PUB_KEY_ID_TEST',
                         self.secret, 'https://website.example/api/payments/settled')
        self.client = TestClient(create_app(self.g, run_worker=False))
        self.order = dict(order_no='D100ABC123', amount_minor=99, currency='CNY', description='工具', provider='wechat')

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def post(self, url, data):
        body = encode(data)
        return self.client.post(url, content=body, headers=signed_headers(body, self.secret))

    def trade(self, no='D100ABC123', txn='wx-txn-1'):
        return dict(appid='app', mchid='merchant', trade_state='SUCCESS', trade_type='NATIVE',
                    out_trade_no=no, transaction_id=txn, amount={'total': 99, 'currency': 'CNY'},
                    success_time='2026-10-14T09:00:00+08:00')

    def count(self, table):
        with self.g.connect() as c:
            return c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]

    def test_signed_checkout_and_immutable_duplicate(self):
        a = self.post('/api/checkout', self.order)
        self.assertEqual(a.status_code, 200)
        check_signature(a.content, a.headers, self.secret)
        b = self.post('/api/checkout', self.order)
        self.assertEqual(a.json(), b.json())
        self.sdk.pay.assert_called_once()
        changed = dict(self.order, amount_minor=100)
        self.assertEqual(self.post('/api/checkout', changed).status_code, 409)
        self.assertEqual(self.client.post('/api/checkout', json=self.order).status_code, 401)
        body = encode(self.order)
        headers = signed_headers(body, self.secret)
        self.assertEqual(self.client.post('/api/checkout', content=body+b' ', headers=headers).status_code, 401)
        headers['X-Pay100-Timestamp'] = str(int(time.time()) - 1000)
        self.assertEqual(self.client.post('/api/checkout', content=body, headers=headers).status_code, 401)

    def test_input_validation(self):
        for change in ({'amount_minor': True}, {'amount_minor': 0}, {'currency': 'USD'},
                       {'provider': 'stripe'}, {'order_no': '../secret'}, {'description': '中' * 80}):
            self.assertEqual(self.post('/api/checkout', dict(self.order, **change)).status_code, 400)
        self.assertEqual(self.count('gateway_orders'), 0)

    def test_ambiguous_network_retry_keeps_order_binding(self):
        self.sdk.pay.side_effect = TimeoutError()
        self.assertEqual(self.post('/api/checkout', self.order).status_code, 502)
        self.assertEqual(self.count('gateway_orders'), 1)
        with self.g.connect() as c:
            deadline = c.execute('SELECT expires_at FROM gateway_orders').fetchone()[0]
        self.sdk.pay.side_effect = None
        self.assertEqual(self.post('/api/checkout', self.order).json()['expires_at'], deadline)
        self.assertEqual(self.sdk.pay.call_args_list[0], self.sdk.pay.call_args_list[1])
        with self.g.connect() as c:
            c.execute('UPDATE gateway_orders SET expires_at=0')
        self.assertEqual(self.post('/api/checkout', self.order).status_code, 409)

    def test_concurrent_checkout_and_settlement(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.g.checkout(self.order), range(4)))
        self.assertTrue(all(x == results[0] for x in results))
        self.sdk.pay.assert_called_once()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.g.settle(self.trade(), 'evt-1'), range(4)))
        self.assertEqual(self.count('gateway_outbox'), 1)
        self.assertEqual(self.post('/api/checkout', self.order).status_code, 409)

    def test_settlement_rejects_invalid_facts(self):
        self.g.checkout(self.order)
        for change in ({'appid': 'wrong'}, {'mchid': 'wrong'}, {'trade_type': 'JSAPI'},
                       {'out_trade_no': 'UNKNOWN'}, {'amount': {'total': 98, 'currency': 'CNY'}},
                       {'amount': {'total': 99, 'currency': 'USD'}}, {'trade_state': 'NOTPAY'}):
            with self.assertRaises(HTTPException):
                self.g.settle(dict(self.trade(), **change), 'evt-1')
        self.assertEqual(self.count('gateway_outbox'), 0)
        self.g.settle(self.trade(), 'evt-1')
        with self.assertRaises(HTTPException):
            self.g.settle(self.trade(txn='another'), 'evt-2')
        self.g.checkout(dict(self.order, order_no='D100OTHER'))
        with self.assertRaises(HTTPException):
            self.g.settle(self.trade(no='D100OTHER'), 'evt-2')
        with self.g.connect() as c:
            self.assertEqual(c.execute("SELECT status FROM gateway_orders WHERE order_no='D100OTHER'").fetchone()[0], 'PENDING')

    def test_outbox_survives_restart_and_retries_same_event(self):
        self.g.checkout(self.order)
        self.g.settle(self.trade(), 'evt-1')
        client = Mock()
        client.post.return_value.status_code = 500
        self.g.deliver(client)
        original = client.post.call_args.kwargs['content']
        check_signature(original, client.post.call_args.kwargs['headers'], self.secret)
        with self.g.connect() as c:
            self.assertEqual(c.execute('SELECT delivered FROM gateway_outbox').fetchone()[0], 0)
            c.execute('UPDATE gateway_outbox SET next_attempt=0')
        restarted = Gateway(self.g.db_path, self.sdk, 'app', 'merchant', 'PUB_KEY_ID_TEST', self.secret, self.g.settlement_url)
        client.post.return_value.status_code = 204
        restarted.deliver(client)
        self.assertEqual(client.post.call_args.kwargs['content'], original)
        restarted.deliver(client)
        self.assertEqual(client.post.call_count, 2)

    def test_missing_callback_recovered_by_signed_query(self):
        self.g.checkout(self.order)
        self.sdk.query.return_value = (200, json.dumps(self.trade()))
        response = self.post('/api/orders/query', {'order_no': self.order['order_no']})
        self.assertEqual(response.status_code, 200)
        check_signature(response.content, response.headers, self.secret)
        self.assertEqual(response.json()['status'], 'PAID')
        self.g.settle(self.trade(), 'later-callback-id')
        self.assertEqual(self.count('gateway_outbox'), 1)

    def test_existing_database_kept(self):
        with self.g.connect() as c:
            c.execute('CREATE TABLE payment_orders(out_trade_no TEXT PRIMARY KEY)')
            c.execute("INSERT INTO payment_orders VALUES('TEST123')")
        Gateway(self.g.db_path, self.sdk, 'app', 'merchant', 'PUB_KEY_ID_TEST', self.secret, self.g.settlement_url)
        self.assertEqual(self.count('payment_orders'), 1)

    def test_real_sdk_signature_decryption_and_tamper(self):
        # Exercise the actual pinned SDK's cryptography, not a callback mock.
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
        pub = private.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        key = 'K' * 32
        sdk = WeChatPay(WeChatPayType.NATIVE, 'merchant', pem, 'CERT', 'app', key,
                        public_key=pub, public_key_id='PUB_KEY_ID_TEST', notify_url='https://pay.example/notify')
        self.g.sdk = sdk
        with self.g.connect() as c:
            c.execute('INSERT INTO gateway_orders(order_no,amount_minor,currency,description,expires_at) VALUES(?,?,?,?,?)',
                      ('D100ABC123', 99, 'CNY', '工具', int(time.time())+900))
        nonce = '123456789012'
        ciphertext = AESGCM(key.encode()).encrypt(nonce.encode(), encode(self.trade()), b'transaction')
        body = encode(dict(id='evt-real', event_type='TRANSACTION.SUCCESS', resource_type='encrypt-resource',
                           resource=dict(algorithm='AEAD_AES_256_GCM', nonce=nonce, associated_data='transaction',
                                         ciphertext=base64.b64encode(ciphertext).decode())))
        stamp = str(int(time.time()))
        signature = private.sign(stamp.encode()+b'\nnonce\n'+body+b'\n', padding.PKCS1v15(), hashes.SHA256())
        headers = {'Wechatpay-Timestamp': stamp, 'Wechatpay-Nonce': 'nonce', 'Wechatpay-Serial': 'PUB_KEY_ID_TEST',
                   'Wechatpay-Signature': base64.b64encode(signature).decode(),
                   'Wechatpay-Signature-Type': 'WECHATPAY2-SHA256-RSA2048'}
        self.assertEqual(self.client.post('/api/wechat/notify', content=body+b' ', headers=headers).status_code, 401)
        self.assertEqual(self.client.post('/api/wechat/notify', content=body, headers=headers).status_code, 204)
        self.assertEqual(self.client.post('/api/wechat/notify', content=body, headers=headers).status_code, 204)
        self.assertEqual(self.count('gateway_outbox'), 1)
        headers['Wechatpay-Timestamp'] = str(int(time.time())-1000)
        self.assertEqual(self.client.post('/api/wechat/notify', content=body, headers=headers).status_code, 401)


if __name__ == '__main__':
    unittest.main()
