from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import community_core as core

ACADEMIES = {
    "panda": "🐼 熊猫院",
    "rabbit": "🐇 兔院",
    "eagle": "🦅 鹰院",
    "other": "其他院",
}


def init_db():
    core.init_db()
    with site.db() as conn:
        user_cols = {r['name'] for r in conn.execute("PRAGMA table_info(community_users)").fetchall()}
        if 'academy' not in user_cols:
            conn.execute("ALTER TABLE community_users ADD COLUMN academy TEXT NOT NULL DEFAULT 'other'")
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
        academy_options = ''.join(f'<option value="{site.esc(code)}">{site.esc(label)}</option>' for code, label in ACADEMIES.items())
        body = f'''<div class="loginwrap"><div class="login"><div class="eyebrow">DESIGN 100%</div><h1>加入社区</h1>
        <div class="notice">选择你的社区院籍后即可直接注册并参与 BBS。需要发布软件时，可在个人中心申请「小飞侠开发者认证」。动物院籍为社区身份标签，不代表所在单位官方认证。</div>
        <form action="/account/register" method="post"><div class="field"><label>选择院系</label><select name="academy" required>{academy_options}</select></div><div class="field"><label>昵称</label><input name="display_name" required autofocus></div><div class="field"><label>邮箱</label><input name="email" type="email" required></div><div class="field"><label>设置密码</label><input name="password" type="password" minlength="6" required></div><button class="btn">注册</button> <a class="btn secondary" href="/account/login">已有账号</a></form></div></div>'''
        return HTMLResponse(community_portal.page(body, '注册 · 小飞侠设计100%'))

    @app.post('/account/register')
    def register(academy: str = Form(...), display_name: str = Form(...), email: str = Form(...), password: str = Form(...)):
        name = display_name.strip(); mail = email.strip().lower(); academy = academy.strip().lower()
        if academy not in ACADEMIES: raise HTTPException(400, '请选择有效院系。')
        if not name or not mail or '@' not in mail: raise HTTPException(400, '请填写昵称和有效邮箱。')
        if len(password) < 6: raise HTTPException(400, '密码至少 6 位。')
        salt, digest = core.hash_password(password); stamp = core.now()
        try:
            with site.db() as conn:
                cur = conn.execute('INSERT INTO community_users(username,display_name,email,password_salt,password_hash,role,active,created_at,updated_at,academy) VALUES(?,?,?,?,?,?,1,?,?,?)', (mail,name,mail,salt,digest,core.ROLE_XIAOYOUXIA,stamp,stamp,academy))
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
        academy_label = ACADEMIES.get(user['academy'] if 'academy' in user.keys() else 'other', '其他院')
        if user['role'] == core.ROLE_XIAOFEIXIA:
            content = '<div class="notice">✓ 你已经是小飞侠开发者，可以发布和维护软件工具。</div><a class="btn" href="/developer/submit">进入开发者中心</a>'
        elif row and row['status'] == 'pending':
            content = '<div class="notice">你的开发者认证申请正在审核中。</div>'
        else:
            content = _form(row)
        body = f'''<div class="community-wrap"><div class="community-card"><a class="small-link" href="/account/me">← 返回个人中心</a><h1>小飞侠开发者认证</h1><div class="notice">当前社区院籍：{site.esc(academy_label)}</div><p class="muted">这里的认证仅用于确认软件发布者是否为中建设计系统相关单位员工本人。认证通过后开放软件发布权限。</p>{content}</div></div>'''
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


def install_admin_routes(admin_app, admin_portal):
    init_db()

    @admin_app.get('/developer-verification', response_class=HTMLResponse)
    def review_list(request: Request):
        admin_portal.require_admin(request)
        with site.db() as conn:
            rows = conn.execute('''SELECT a.*,u.display_name,u.email,u.academy FROM developer_verification_applications a JOIN community_users u ON u.id=a.user_id ORDER BY CASE a.status WHEN 'pending' THEN 0 WHEN 'rejected' THEN 1 ELSE 2 END,a.id DESC''').fetchall()
        cards=[]
        for a in rows:
            actions=''
            if a['status']=='pending':
                actions=f'''<form action="/manage/developer-verification/{a['id']}/approve" method="post" style="display:inline"><button class="btn">通过</button></form> <form action="/manage/developer-verification/{a['id']}/reject" method="post" style="display:inline"><input name="admin_note" placeholder="拒绝原因"><button class="btn secondary">拒绝</button></form>'''
            academy_label = ACADEMIES.get(a['academy'] or 'other', '其他院')
            cards.append(f'''<div class="admin-card" style="margin-bottom:12px"><span class="badge">{site.esc(a['status'])}</span><h2>{site.esc(a['real_name'])}</h2><div class="admin-sub">{site.esc(academy_label)} · {site.esc(a['organization'])} · {site.esc(a['department'] or '未填部门')} · {site.esc(a['profession'] or '未填专业')}</div><p class="muted">账号：{site.esc(a['display_name'])} · {site.esc(a['email'] or '')}<br>联系方式：{site.esc(a['contact'] or '未填')}<br>{site.esc(a['note'] or '')}</p><div class="admin-actions">{actions}</div></div>''')
        body=f'''<div class="admin-shell"><a class="backlink" href="/manage/">← 返回后台</a><div class="admin-head"><div><h1>小飞侠开发者认证</h1><div class="admin-sub">审核是否为中建设计系统相关单位员工本人。通过后自动开放软件发布权限。</div></div></div>{''.join(cards) if cards else '<div class="admin-card muted">暂无认证申请</div>'}</div>'''
        return HTMLResponse(admin_portal.admin_page(body,'小飞侠开发者认证'))

    @admin_app.post('/developer-verification/{application_id}/approve')
    def approve(request: Request, application_id: int):
        admin_portal.require_admin(request)
        with site.db() as conn:
            row=conn.execute('SELECT * FROM developer_verification_applications WHERE id=?',(application_id,)).fetchone()
            if not row: raise HTTPException(404,'申请不存在。')
            conn.execute("UPDATE developer_verification_applications SET status='approved',admin_note='',reviewed_at=? WHERE id=?",(core.now(),application_id))
            conn.execute('UPDATE community_users SET role=?,updated_at=? WHERE id=?',(core.ROLE_XIAOFEIXIA,core.now(),row['user_id']))
        return RedirectResponse('/manage/developer-verification',303)

    @admin_app.post('/developer-verification/{application_id}/reject')
    def reject(request: Request, application_id: int, admin_note: str = Form('')):
        admin_portal.require_admin(request)
        with site.db() as conn:
            if not conn.execute('SELECT id FROM developer_verification_applications WHERE id=?',(application_id,)).fetchone(): raise HTTPException(404,'申请不存在。')
            conn.execute("UPDATE developer_verification_applications SET status='rejected',admin_note=?,reviewed_at=? WHERE id=?",(admin_note.strip(),core.now(),application_id))
        return RedirectResponse('/manage/developer-verification',303)
