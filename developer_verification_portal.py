from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import community_core as core


def init_db():
    core.init_db()
    with site.db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS developer_verification_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            real_name TEXT NOT NULL,
            organization TEXT NOT NULL,
            department TEXT NOT NULL DEFAULT '',
            profession TEXT NOT NULL DEFAULT '',
            contact TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            admin_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        );
        ''')


def _form(row=None):
    def val(key):
        return site.esc(row[key]) if row else ''
    return f'''<form action="/account/developer-verification" method="post">
    <div class="field"><label>真实姓名</label><input name="real_name" value="{val('real_name')}" required></div>
    <div class="field"><label>所在设计院 / 单位</label><input name="organization" value="{val('organization')}" placeholder="例如：中建西北院" required></div>
    <div class="field"><label>部门</label><input name="department" value="{val('department')}"></div>
    <div class="field"><label>专业</label><input name="profession" value="{val('profession')}" placeholder="建筑 / 景观 / 结构 / BIM / 数字化"></div>
    <div class="field"><label>工作邮箱或联系电话</label><input name="contact" value="{val('contact')}" placeholder="仅用于审核"></div>
    <div class="field"><label>补充说明</label><textarea name="note">{val('note')}</textarea></div>
    <button class="btn">提交认证申请</button></form>'''


def install_account_routes(app, community_portal):
    init_db()
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', None) != '/account/register']

    @app.get('/account/register', response_class=HTMLResponse)
    def register_page():
        body = '''<div class="loginwrap"><div class="login"><div class="eyebrow">DESIGN 100%</div><h1>加入社区</h1>
        <div class="notice">普通用户可直接注册并参与 BBS。需要发布软件时，可在个人中心申请「小飞侠开发者认证」。</div>
        <form action="/account/register" method="post"><div class="field"><label>昵称</label><input name="display_name" required autofocus></div><div class="field"><label>邮箱</label><input name="email" type="email" required></div><div class="field"><label>设置密码</label><input name="password" type="password" minlength="6" required></div><button class="btn">注册</button> <a class="btn secondary" href="/account/login">已有账号</a></form></div></div>'''
        return HTMLResponse(community_portal.page(body, '注册 · 小飞侠设计100%'))

    @app.post('/account/register')
    def register(display_name: str = Form(...), email: str = Form(...), password: str = Form(...)):
        name = display_name.strip(); mail = email.strip().lower()
        if not name or not mail or '@' not in mail: raise HTTPException(400, '请填写昵称和有效邮箱。')
        if len(password) < 6: raise HTTPException(400, '密码至少 6 位。')
        salt, digest = core.hash_password(password); stamp = core.now()
        try:
            with site.db() as conn:
                cur = conn.execute('INSERT INTO community_users(username,display_name,email,password_salt,password_hash,role,active,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?)', (mail,name,mail,salt,digest,core.ROLE_XIAOYOUXIA,stamp,stamp))
                uid = cur.lastrowid
        except Exception:
            raise HTTPException(409, '这个邮箱已经注册。')
        resp = RedirectResponse('/account/me',303)
        resp.set_cookie(core.USER_COOKIE,core.make_session(uid),httponly=True,secure=True,samesite='lax',max_age=7*86400)
        return resp

    @app.get('/account/developer-verification', response_class=HTMLResponse)
    def verification_page(request: Request):
        user = core.current_user(request)
        if not user: return RedirectResponse('/account/login?next=/account/developer-verification',303)
        with site.db() as conn:
            row = conn.execute('SELECT * FROM developer_verification_applications WHERE user_id=?',(user['id'],)).fetchone()
        if user['role'] == core.ROLE_XIAOFEIXIA:
            content = '<div class="notice">✓ 你已经是小飞侠开发者，可以发布和维护软件工具。</div><a class="btn" href="/developer/submit">进入开发者中心</a>'
        elif row and row['status'] == 'pending':
            content = '<div class="notice">你的开发者认证申请正在审核中。</div>'
        else:
            content = _form(row)
        body = f'''<div class="community-wrap"><div class="community-card"><a class="small-link" href="/account/me">← 返回个人中心</a><h1>小飞侠开发者认证</h1><p class="muted">仅用于确认软件发布者是否为中建设计系统相关单位员工本人。认证通过后开放软件发布权限。</p>{content}</div></div>'''
        return HTMLResponse(community_portal.page(body,'小飞侠开发者认证'))

    @app.post('/account/developer-verification')
    def submit(request: Request, real_name: str = Form(...), organization: str = Form(...), department: str = Form(''), profession: str = Form(''), contact: str = Form(''), note: str = Form('')):
        user = core.current_user(request)
        if not user: raise HTTPException(401,'请先登录。')
        if user['role'] == core.ROLE_XIAOFEIXIA: return RedirectResponse('/account/developer-verification',303)
        rn=' '.join(real_name.strip().split()); org=organization.strip()
        if not rn or not org: raise HTTPException(400,'请填写真实姓名和所在单位。')
        with site.db() as conn:
            conn.execute('''INSERT INTO developer_verification_applications(user_id,real_name,organization,department,profession,contact,note,status,admin_note,created_at,reviewed_at) VALUES(?,?,?,?,?,?,?,'pending','',?,NULL) ON CONFLICT(user_id) DO UPDATE SET real_name=excluded.real_name,organization=excluded.organization,department=excluded.department,profession=excluded.profession,contact=excluded.contact,note=excluded.note,status='pending',admin_note='',created_at=excluded.created_at,reviewed_at=NULL''',(user['id'],rn,org,department.strip(),profession.strip(),contact.strip(),note.strip(),core.now()))
        return RedirectResponse('/account/developer-verification',303)
