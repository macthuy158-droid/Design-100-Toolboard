"""Verify one login, exact admin binding and server-side administrative authorization."""
import os
import re
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['TOOLBOARD_DATA_DIR']=tempfile.mkdtemp(prefix='unified-admin-')
from fastapi.testclient import TestClient
from app import app,public_site as site
import community_core as core
from scripts.check_business_rules import add_user
from scripts.grant_admin import grant

with site.db() as c:
    uid=add_user(c,'Unified Admin Fixture',core.ROLE_XIAOYOUXIA)
    c.execute("UPDATE community_users SET username='Unified Admin Fixture' WHERE id=?",(uid,))
    salt,digest=core.hash_password('offline-admin-password')
    c.execute('UPDATE community_users SET password_salt=?,password_hash=? WHERE id=?',(salt,digest,uid))
    other=add_user(c,'ordinary-account',core.ROLE_XIAOYOUXIA)
    c.execute("UPDATE community_users SET display_name='Unified Admin Fixture' WHERE id=?",(other,))
try:
    grant(site.DB_PATH,'unknown username',Path(os.environ['TOOLBOARD_DATA_DIR'])/'backups')
    raise AssertionError('Unknown login username must not be bound')
except ValueError:
    pass
bound,username,_=grant(site.DB_PATH,'Unified Admin Fixture',Path(os.environ['TOOLBOARD_DATA_DIR'])/'backups')
assert bound==uid and username=='Unified Admin Fixture'
grant(site.DB_PATH,'Unified Admin Fixture',Path(os.environ['TOOLBOARD_DATA_DIR'])/'backups')
with site.db() as c:
    user=c.execute('SELECT * FROM community_users WHERE id=?',(uid,)).fetchone()
    assert core.is_admin(user) and user['password_hash']==digest
    assert not core.is_admin(c.execute('SELECT * FROM community_users WHERE id=?',(other,)).fetchone())
    assert c.execute('SELECT COUNT(*) FROM admin_access_events WHERE user_id=?',(uid,)).fetchone()[0]==1

anonymous=TestClient(app,base_url='https://testserver')
assert anonymous.get('/manage/',follow_redirects=False).headers['location'].startswith('/account/login')
assert anonymous.get('/manage/tools/',follow_redirects=False).status_code==303
anonymous.cookies.set(site.COOKIE_NAME,site.session_token())
assert anonymous.get('/manage/',follow_redirects=False).status_code==303, 'Legacy admin cookie must not authorize'
assert anonymous.post('/manage/login',json={'username':'admin','password':os.getenv('TOOLBOARD_ADMIN_PASSWORD')}).status_code==410
ordinary=TestClient(app,base_url='https://testserver')
ordinary.cookies.set(core.USER_COOKIE,core.make_session(other))
assert ordinary.get('/manage/',follow_redirects=False).status_code==403
assert ordinary.get('/manage/community/users').status_code==403
assert ordinary.post('/manage/community/users',data={'name':'Should not exist','csrf':'fake'}).status_code==403
assert not ordinary.get('/account/session').json()['is_admin']
assert '进入管理控制台' not in ordinary.get('/account/me').text

admin=TestClient(app,base_url='https://testserver')
login=admin.post('/account/login',data={'account':'Unified Admin Fixture','password':'offline-admin-password','next':'/manage/'},follow_redirects=False)
assert login.status_code==303 and login.headers['location']=='/manage/'
assert 'design100_admin=' not in login.headers.get('set-cookie','')
assert admin.get('/account/session').json()['is_admin']
assert '进入管理控制台' in admin.get('/account/me').text
assert admin.get('/manage/').status_code==200
users=admin.get('/manage/community/users').text
# Every administrative POST form receives the same session-bound admin CSRF token.
forms=re.findall(r'<form\b[^>]*method="post"[^>]*>(.*?)</form>',users,re.S)
assert forms and all('name="csrf"' in form for form in forms)
admin_csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',users).group(1)
assert admin.post('/manage/community/users',data={'name':'Added by admin'}).status_code==403
assert admin.post('/manage/community/users',data={'name':'Added by admin','csrf':admin_csrf},follow_redirects=False).status_code==303
assert admin.post(f'/manage/community/users/{uid}/toggle',data={'csrf':admin_csrf}).status_code==409, 'Last administrator must remain active'
with site.db() as c:
    assert c.execute("SELECT COUNT(*) FROM community_users WHERE username='Should not exist'").fetchone()[0]==0
    assert c.execute("SELECT COUNT(*) FROM community_users WHERE username='Added by admin'").fetchone()[0]==1
    c.execute('UPDATE community_users SET is_admin=0 WHERE id=?',(uid,))
assert admin.get('/manage/').status_code==403, 'Revocation must apply to an existing login session'
with site.db() as c:
    c.execute('UPDATE community_users SET is_admin=1 WHERE id=?',(uid,))
page=admin.get('/account/me').text
csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page).group(1)
assert admin.post('/account/logout').status_code==403
assert admin.post('/account/logout',data={'csrf':csrf},follow_redirects=False).status_code==303
assert admin.get('/manage/',follow_redirects=False).status_code==303

# Login targets cannot redirect externally, including for already authenticated users.
assert admin.post('/account/login',data={'account':'Unified Admin Fixture','password':'offline-admin-password','next':'//example.test'},follow_redirects=False).headers['location']=='/account/me'
assert admin.get('/account/login?next=https://example.test',follow_redirects=False).headers['location']=='/account/me'
from community_portal import safe_next
assert safe_next('/' + chr(92) + 'example.test')=='/account/me'
print('Unified admin passed: exact account binding, one login/logout, old-cookie rejection, CSRF, ordinary-user denial, revocation and last-admin guard')
