"""Exercise live authorization, revenue isolation and annual award transitions."""
import os
import re
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['TOOLBOARD_DATA_DIR']=tempfile.mkdtemp(prefix='admin-management-')
from fastapi.testclient import TestClient
from app import app,public_site as site
import community_core as core
from scripts.check_business_rules import add_user
from scripts.grant_admin import grant

with site.db() as conn:
    primary=add_user(conn,'Primary fixture',core.ROLE_XIAOYOUXIA)
    delegate=add_user(conn,'Delegate fixture',core.ROLE_XIAOYOUXIA)
    ordinary=add_user(conn,'Ordinary fixture',core.ROLE_XIAOYOUXIA)
    conn.execute("INSERT INTO purchase_orders(order_no,user_id,product_type,product_id,product_name,seller_user_id,amount_cents,status,created_at,paid_at) VALUES('REPORT1',?,'tool',1,'=unsafe title',?,1234,'paid',?,?)",(ordinary,delegate,core.now(),'2025-12-31T18:00:00Z'))
    conn.execute("INSERT INTO purchase_orders(order_no,user_id,product_type,product_id,product_name,seller_user_id,amount_cents,status,created_at,paid_at) VALUES('REPORT2',?,'tool',1,'=unsafe title',?,234,'refunded',?,?)",(ordinary,delegate,core.now(),'2026-01-02T00:00:00Z'))
    username=conn.execute('SELECT username FROM community_users WHERE id=?',(primary,)).fetchone()[0]
grant(site.DB_PATH,username,Path(os.environ['TOOLBOARD_DATA_DIR'])/'backup',superadmin=True)

def client(uid):
    c=TestClient(app,base_url='https://testserver'); c.cookies.set(core.USER_COOKIE,core.make_session(uid)); return c

p=client(primary); d=client(delegate); o=client(ordinary)
token=re.search(r'name="csrf" value="([a-f0-9]+)"',p.get('/manage/permissions').text).group(1)
def post(c,path,data): return c.post(path,data=dict(data,csrf=token if c is p else dtoken),follow_redirects=False)
assert o.get('/manage/revenue').status_code==403
assert p.post(f'/manage/permissions/{delegate}',data={'role':'admin'}).status_code==403
assert post(p,f'/manage/permissions/{delegate}',{'role':'admin'}).status_code==303
dtoken=re.search(r'name="csrf" value="([a-f0-9]+)"',d.get('/manage/community/users').text).group(1)
for path in ('/manage/permissions','/manage/revenue','/manage/revenue.csv','/manage/awards','/manage/audit','/manage/community/purchases'):
    assert d.get(path).status_code==403,path
assert post(d,f'/manage/permissions/{ordinary}',{'role':'super'}).status_code==403
assert post(d,f'/manage/community/users/{primary}/toggle',{}).status_code==403
assert post(p,f'/manage/permissions/{primary}',{'role':'user'}).status_code==409
assert post(p,f'/manage/community/users/{primary}/toggle',{}).status_code==409
assert post(p,f'/manage/permissions/{delegate}',{'role':'finance'}).status_code==303
assert d.get('/manage/revenue?year=2026').status_code==200
assert d.get('/manage/community/purchases').status_code==200
csv=d.get('/manage/revenue.csv?year=2026').text
assert '12.34' in csv and '2.34' in csv and "'=unsafe title" in csv
assert '12.34' not in d.get('/manage/revenue.csv?year=2025').text
assert d.get('/manage/awards').status_code==403
with site.db() as conn: beneficiary=conn.execute('SELECT username FROM community_users WHERE id=?',(delegate,)).fetchone()[0]
assert post(p,'/manage/awards',{'year':2026,'username':beneficiary,'amount':'100.001','basis':'maintenance'}).status_code==400
assert post(p,'/manage/awards',{'year':2026,'username':beneficiary,'amount':'100','basis':'maintenance'}).status_code==303
with site.db() as conn: aid=conn.execute('SELECT id FROM annual_awards').fetchone()[0]
assert post(p,f'/manage/awards/{aid}/paid',{'reference':'BANK1'}).status_code==409
assert post(p,f'/manage/awards/{aid}/approve',{}).status_code==303
assert post(p,f'/manage/awards/{aid}/paid',{}).status_code==409
assert post(p,f'/manage/awards/{aid}/paid',{'reference':'BANK1'}).status_code==303
assert post(p,f'/manage/awards/{aid}/paid',{'reference':'BANK1'}).status_code==409
assert post(p,f'/manage/awards/{aid}/cancel',{}).status_code==409
assert post(p,f'/manage/permissions/{delegate}',{'role':'user'}).status_code==303
assert d.get('/manage/revenue').status_code==403
with site.db() as conn:
    assert conn.execute('SELECT status FROM annual_awards WHERE id=?',(aid,)).fetchone()[0]=='paid'
    assert conn.execute("SELECT COUNT(*) FROM admin_audit WHERE action='award.paid'").fetchone()[0]==1
    assert conn.execute("SELECT COUNT(*) FROM admin_audit WHERE action='permission.change'").fetchone()[0]==3
assert p.get('/manage/audit').status_code==200
print('ADMIN_MANAGEMENT_OK')
