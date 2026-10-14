"""Retirement checks against a disposable DB; no real accounts or payments."""
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TOOLBOARD_DATA_DIR'] = tempfile.mkdtemp(prefix='points-retirement-')
from fastapi.testclient import TestClient
from app import app, public_site as site
import coin_core
import community_core as core
import community_portal as portal
from scripts.check_business_rules import add_user, add_tool

client = TestClient(app)
with site.db() as c:
    owner_id=add_user(c,'retire-owner',core.ROLE_XIAOFEIXIA)
    buyer_id=add_user(c,'retire-buyer',core.ROLE_XIAOYOUXIA)
    other_id=add_user(c,'retire-other',core.ROLE_XIAOYOUXIA)
    paid_id=add_tool(c,'retire-paid',owner_id,coin_price=50,price_cents=2500)
    legacy_id=add_tool(c,'retire-legacy',owner_id,coin_price=50)
    c.execute('UPDATE tools SET legacy_coin_only=1 WHERE id=?',(legacy_id,))
    coin_core._record(c,buyer_id,100,'register_bonus',note='historical fixture')
    coin_core._record(c,buyer_id,-50,'download_spend',tool_id=legacy_id)
    balance=coin_core.balance(c,buyer_id)
client.cookies.set(core.USER_COOKIE,core.make_session(buyer_id))
page=client.get('/tools/retire-paid').text
assert '¥25.00' in page and '/coin-unlock' not in page and '社区兑换' not in page
assert '/download' in client.get('/tools/retire-legacy').text
assert '历史积分记录' in client.get('/account/me').text
assert client.post('/account/tools/retire-paid/coin-unlock').status_code == 410
client.cookies.set(core.USER_COOKIE,core.make_session(other_id))
legacy=client.get('/tools/retire-legacy').text
assert '待定价' in legacy and '/coin-unlock' not in legacy
denied=client.get('/tools/retire-legacy/download',follow_redirects=False)
assert denied.status_code==303 and denied.headers['location']=='/tools/retire-legacy'
client.cookies.set(core.USER_COOKIE,core.make_session(owner_id))
assert client.post('/account/tools/retire-paid/coin-price',data={'feixia_coin_price':1}).status_code == 410
assert 'name="feixia_coin_price"' not in client.get('/account/me').text
assert 'name="feixia_coin_price"' not in client.get('/developer/submit').text
with patch('community_admin.require_admin',return_value=None):
    assert client.post(f'/manage/community/coins/{buyer_id}/adjust',data={'delta':5}).status_code == 410
    archive=client.get('/manage/community/coins').text
    assert '只读存档' in archive and '/adjust"' not in archive
with site.db() as c:
    assert coin_core.balance(c,buyer_id)==balance
    assert coin_core.balance(c,owner_id)==0
    assert not coin_core.grant_register_bonus(c,other_id)
    assert not coin_core.grant_publish_reward(c,owner_id,100,paid_id)

# Both actual registration flows create users without minting points.
with patch('community_portal.GUEST_SIGNUP_OPEN',True):
    r=client.post('/account/register',data={'role':'xiaoyouxia','email':'retire-new@example.test',
                  'display_name':'New member','password':'offline-test-password'},follow_redirects=False)
    assert r.status_code==303
invite,_=core.create_invite('Retirement Invite')
r=client.post('/account/register',data={'role':'xiaofeixia','real_name':'Retirement Invite',
              'invite_code':invite,'password':'offline-test-password'},follow_redirects=False)
assert r.status_code==303
with site.db() as c:
    ids=[r[0] for r in c.execute("SELECT id FROM community_users WHERE username IN ('retire-new@example.test','Retirement Invite')")]
    assert len(ids)==2
    assert all(coin_core.balance(c,i)==0 for i in ids)

# Old escrow is still returned/paid exactly once, including concurrent cancellation.
with site.db() as c:
    now=core.now()
    cur=c.execute("INSERT INTO bounties(user_id,title,description,status,reward,escrowed,created_at,updated_at) VALUES(?,?,?,'open',20,1,?,?)",
                  (buyer_id,'Legacy escrow','Existing contract',now,now))
    cancel_id=cur.lastrowid
    coin_core._record(c,buyer_id,-20,'bounty_escrow',ref='historical-cancel')
    cur=c.execute("INSERT INTO bounties(user_id,title,description,status,reward,escrowed,created_at,updated_at) VALUES(?,?,?,'in_progress',30,1,?,?)",
                  (buyer_id,'Legacy completion','Existing contract',now,now))
    finish_id=cur.lastrowid
    coin_core._record(c,buyer_id,-30,'bounty_escrow',ref='historical-complete')
    cur=c.execute("INSERT INTO bounty_responses(bounty_id,developer_user_id,proposal,status,created_at,updated_at) VALUES(?,?,?,'accepted',?,?)",
                  (finish_id,owner_id,'Historical accepted proposal',now,now))
    c.execute('UPDATE bounties SET accepted_response_id=? WHERE id=?',(cur.lastrowid,finish_id))
client.cookies.set(core.USER_COOKIE,core.make_session(buyer_id))
assert client.post('/bounties/new',data={'title':'New','description':'No','reward':1}).status_code==410
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(lambda _: client.post(f'/bounties/{cancel_id}/status',data={'status':'cancelled'},follow_redirects=False).status_code,range(2)))
assert sorted(results)==[303,409], results
assert client.post(f'/bounties/{cancel_id}/status',data={'status':'open'}).status_code==410
assert client.post(f'/bounties/{finish_id}/status',data={'status':'completed'},follow_redirects=False).status_code==303
assert client.post(f'/bounties/{finish_id}/status',data={'status':'completed'}).status_code==409
with site.db() as c:
    assert coin_core.balance(c,buyer_id)==balance-30
    assert coin_core.balance(c,owner_id)==30
    assert c.execute("SELECT COUNT(*) FROM coin_ledger WHERE reason='bounty_refund'").fetchone()[0]==1
    assert c.execute("SELECT COUNT(*) FROM coin_ledger WHERE reason='bounty_payout'").fetchone()[0]==1
print('Points retirement passed: old rights, read-only archives, no rewards/redemption, old escrow settled once')
