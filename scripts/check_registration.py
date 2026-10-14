"""Registration and developer review isolation checks; disposable accounts only."""
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['TOOLBOARD_DATA_DIR']=tempfile.mkdtemp(prefix='registration-check-')
os.environ['TOOLBOARD_GUEST_SIGNUP']='1'
from fastapi.testclient import TestClient
from app import app,public_site as site
import community_core as core
import coin_core
import course_portal as courses
from scripts.check_business_rules import add_user,add_tool

client=TestClient(app,base_url="https://testserver")
public=client.get('/account/register')
assert public.status_code==200 and '创建账号' in public.text
assert 'name="email"' in public.text and 'name="confirm_password"' in public.text
assert 'name="invite_code"' not in public.text and 'name="real_name"' not in public.text
assert 'role-select' not in public.text and '/account/register/internal' in public.text
internal=client.get('/account/register/internal')
assert internal.status_code==200 and 'name="invite_code"' in internal.text
assert 'autocomplete="off"' in internal.text

form=dict(display_name='Public developer',email='public@example.test',password='offline-password',confirm_password='offline-password')
for bad in ({'confirm_password':'different-secret'},{'email':'bad-address'},{'role':'admin'},
            {'role':'xiaofeixia','real_name':'Unauthorized','invite_code':'bad'}):
    response=client.post('/account/register',data=dict(form,**bad),follow_redirects=False)
    assert response.status_code==400 and 'text/html' in response.headers['content-type']
    assert 'offline-password' not in response.text and 'different-secret' not in response.text
with site.db() as c:
    assert c.execute('SELECT COUNT(*) FROM community_users').fetchone()[0]==0
result=client.post('/account/register',data=dict(form,developer_enabled='1',is_admin='1'),follow_redirects=False)
assert result.status_code==303 and result.headers['location']=='/account/me'
assert client.post('/account/register',data=form,follow_redirects=False).status_code==409
with site.db() as c:
    u=c.execute("SELECT * FROM community_users WHERE email='public@example.test'").fetchone()
    uid=u['id']
    assert u['role']==core.ROLE_XIAOYOUXIA and not core.is_developer(u) and not core.is_admin(u)
    assert coin_core.balance(c,uid)==0
assert not client.get('/account/session').json()['can_publish']
assert client.get('/developer/submit').status_code==403
html=client.get('/account/me').text
csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',html).group(1)
assert client.post('/account/developer/apply',data={'proposal':'I will build a CAD workflow tool.'}).status_code==403
for _ in range(2):
    assert client.post('/account/developer/apply',data={'proposal':'I will build a CAD workflow tool.','csrf':csrf},follow_redirects=False).status_code==303
with site.db() as c:
    rows=c.execute('SELECT * FROM developer_applications WHERE user_id=?',(uid,)).fetchall()
    assert len(rows)==1 and rows[0]['status']=='pending'
    aid=rows[0]['id']
assert client.post(f'/manage/community/developer-applications/{aid}/review',data={'decision':'approved','csrf':csrf},follow_redirects=False).status_code in (401,403,303)
with site.db() as c:
    assert not core.is_developer(c.execute('SELECT * FROM community_users WHERE id=?',(uid,)).fetchone())
with site.db() as c:
    admin_uid=add_user(c,'Registration test admin',core.ROLE_XIAOYOUXIA)
    c.execute('UPDATE community_users SET is_admin=1 WHERE id=?',(admin_uid,))
client.cookies.set(core.USER_COOKIE,core.make_session(admin_uid))
admin_page=client.get('/manage/community/developer-applications').text
admin_csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',admin_page).group(1)
assert client.post(f'/manage/community/developer-applications/{aid}/review',data={'decision':'approved'}).status_code==403
assert client.post(f'/manage/community/developer-applications/{aid}/review',data={'decision':'approved','csrf':admin_csrf},follow_redirects=False).status_code==303
assert client.post(f'/manage/community/developer-applications/{aid}/review',data={'decision':'rejected','csrf':admin_csrf}).status_code==409
client.cookies.set(core.USER_COOKIE,core.make_session(uid))
assert client.get('/account/session').json()['can_publish']
assert client.get('/developer/submit').status_code==200
with site.db() as c:
    user=c.execute('SELECT * FROM community_users WHERE id=?',(uid,)).fetchone()
    assert core.is_developer(user) and user['role']==core.ROLE_XIAOYOUXIA
    assert core.user_label(user)=='开发者'
    paid_tool=add_tool(c,'outside-owned',uid,price_cents=100)
    assert core.is_tool_owner(c.execute('SELECT * FROM tools WHERE id=?',(paid_tool,)).fetchone(),user)
    now=core.now()
    cur=c.execute("INSERT INTO courses(title,price_cents,status,created_at,updated_at) VALUES('Paid course',100,'published',?,?)",(now,now))
    course=c.execute('SELECT * FROM courses WHERE id=?',(cur.lastrowid,)).fetchone()
    assert not courses.can_learn(c,user,course), 'Developer approval must not grant internal course benefits'
    staff=add_user(c,'Existing internal',core.ROLE_XIAOFEIXIA)
    staff_user=c.execute('SELECT * FROM community_users WHERE id=?',(staff,)).fetchone()
    assert core.is_developer(staff_user) and courses.can_learn(c,staff_user,course)

# Rejection can be resubmitted; application history remains available.
with site.db() as c:
    other=add_user(c,'applicant-rejected',core.ROLE_XIAOYOUXIA)
client.cookies.set(core.USER_COOKIE,core.make_session(other))
html=client.get('/account/me').text
csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',html).group(1)
client.post('/account/developer/apply',data={'proposal':'I will publish a Rhino automation tool.','csrf':csrf})
with site.db() as c:
    rid=c.execute("SELECT id FROM developer_applications WHERE user_id=? AND status='pending'",(other,)).fetchone()[0]
client.cookies.set(core.USER_COOKIE,core.make_session(admin_uid))
admin_csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',client.get('/manage/community/developer-applications').text).group(1)
assert client.post(f'/manage/community/developer-applications/{rid}/review',data={'decision':'rejected','note':'Please clarify the tool','csrf':admin_csrf},follow_redirects=False).status_code==303
client.cookies.set(core.USER_COOKIE,core.make_session(other))
assert 'Please clarify the tool' in client.get('/account/me').text
assert client.post('/account/developer/apply',data={'proposal':'A clarified Rhino automation tool plan.','csrf':csrf},follow_redirects=False).status_code==303
with site.db() as c:
    assert c.execute('SELECT COUNT(*) FROM developer_applications WHERE user_id=?',(other,)).fetchone()[0]==2

# Concurrent use of one invitation can create only one internal account.
invite,_=core.create_invite('Single Invite User')
data=dict(real_name='Single Invite User',display_name='Staff',role='xiaofeixia',invite_code=invite,
          password='offline-password',confirm_password='offline-password')
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(lambda _: TestClient(app).post('/account/register',data=data,follow_redirects=False).status_code,range(2)))
assert sorted(results)==[303,400], results
with site.db() as c:
    assert c.execute("SELECT COUNT(*) FROM community_users WHERE username='Single Invite User'").fetchone()[0]==1
    assert c.execute('SELECT used FROM xiaofeixia_invites WHERE code=?',(invite,)).fetchone()[0]==1
print('Registration passed: clear entry points, inline errors, single-use invites, reviewed developer access, internal benefits isolated')
