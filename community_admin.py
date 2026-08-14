import shutil
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import admin_portal
import community_core as core

app = FastAPI(title="Community Admin", docs_url=None, redoc_url=None, openapi_url=None)

CSS = '''<style>
.wrap{max-width:1220px;margin:36px auto;padding:0 20px 70px}.card{background:#fff;border:1px solid #e6e6e3;border-radius:22px;padding:22px;margin-bottom:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.badge{display:inline-flex;padding:4px 8px;border-radius:999px;background:#eee;font-size:9px}.pending{background:#fff3cd}.ok{background:#dff4e3}.off{background:#f3dede}.actions{display:flex;gap:7px;flex-wrap:wrap}.mini{height:32px!important;padding:0 10px!important;font-size:10px!important}.muted{font-size:11px;color:#888;line-height:1.7}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}.stat{background:#f5f5f2;border-radius:14px;padding:14px}.stat b{display:block;font-size:20px}.stat span{font-size:9px;color:#888}.table-wrap{overflow-x:auto}.table{min-width:780px}.review-text{max-width:360px;white-space:normal;line-height:1.6}@media(max-width:800px){.grid,.summary{grid-template-columns:1fr 1fr}}@media(max-width:520px){.summary{grid-template-columns:1fr}}
</style>'''


def require_admin(request):
    admin_portal.require_admin(request)


def page(body, title="用户与开发者管理 · 小飞侠设计100%"):
    return site.page(CSS + body, title)


@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request):
    require_admin(request)
    core.init_db()
    with site.db() as conn:
        users = conn.execute("SELECT * FROM community_users ORDER BY CASE role WHEN 'xiaofeixia' THEN 0 ELSE 1 END, display_name COLLATE NOCASE").fetchall()
        subs = conn.execute("SELECT s.*,u.display_name FROM tool_submissions s JOIN community_users u ON u.id=s.user_id ORDER BY CASE s.status WHEN 'pending' THEN 0 ELSE 1 END,s.id DESC").fetchall()
        orders = conn.execute("SELECT o.*,u.display_name,t.name tool_name FROM orders o JOIN community_users u ON u.id=o.user_id JOIN tools t ON t.id=o.tool_id ORDER BY o.id DESC LIMIT 100").fetchall()
        reviews = conn.execute("SELECT r.*,u.display_name,u.role,t.name tool_name,t.slug FROM reviews r JOIN community_users u ON u.id=r.user_id JOIN tools t ON t.id=r.tool_id ORDER BY r.id DESC LIMIT 100").fetchall()
        xiaofeixia_count = conn.execute("SELECT COUNT(*) c FROM community_users WHERE role='xiaofeixia'").fetchone()['c']
        xiaoyouxia_count = conn.execute("SELECT COUNT(*) c FROM community_users WHERE role='xiaoyouxia'").fetchone()['c']
        pending_count = conn.execute("SELECT COUNT(*) c FROM tool_submissions WHERE status='pending'").fetchone()['c']
        review_count = conn.execute("SELECT COUNT(*) c FROM reviews").fetchone()['c']

    user_rows = []
    for u in users:
        state = '<span class="badge ok">启用</span>' if u['active'] else '<span class="badge off">停用</span>'
        toggle_label = '停用' if u['active'] else '启用'
        user_rows.append(f'''<tr><td><b>{site.esc(u['display_name'])}</b><br><span class="muted">{site.esc(u['username'])}</span></td><td>{core.role_label(u['role'])}</td><td>{site.esc(u['email'] or '院内账号')}</td><td>{state}</td><td><div class="actions">
        <form action="/manage/community/users/{u['id']}/toggle" method="post"><button class="btn secondary mini">{toggle_label}</button></form>
        {f'<form action="/manage/community/users/{u["id"]}/reset-password" method="post" onsubmit="return confirm(\'确定将密码重置为姓名吗？\')"><button class="btn secondary mini">密码重置为姓名</button></form>' if u['role']==core.ROLE_XIAOFEIXIA else ''}
        </div></td></tr>''')
    user_rows = ''.join(user_rows) or '<tr><td colspan="5">暂无用户</td></tr>'

    sub_rows = ''.join(f'''<tr><td>{site.esc(s['display_name'])}</td><td><b>{site.esc(s['name'] or s['slug'])}</b><br><span class="muted">{site.esc(s['submission_type'])}</span></td><td>v{site.esc(s['version'])}</td><td><span class="badge {'pending' if s['status']=='pending' else 'ok'}">{site.esc(s['status'])}</span></td><td><div class="actions">{f'<form action="/manage/community/submissions/{s["id"]}/approve" method="post"><button class="btn mini">审核通过</button></form><form action="/manage/community/submissions/{s["id"]}/reject" method="post"><button class="btn secondary mini">驳回</button></form>' if s['status']=='pending' else ''}</div></td></tr>''' for s in subs) or '<tr><td colspan="5">暂无投稿</td></tr>'

    order_rows = ''.join(f'''<tr><td>{site.esc(o['order_no'])}</td><td>{site.esc(o['display_name'])}</td><td>{site.esc(o['tool_name'])}</td><td>¥{o['amount_cents']/100:.2f}</td><td>{site.esc(o['status'])}</td><td>{f'<form action="/manage/community/orders/{o["id"]}/grant" method="post"><button class="btn mini">测试确认付款</button></form>' if o['status']=='pending' else ''}</td></tr>''' for o in orders) or '<tr><td colspan="6">暂无订单</td></tr>'

    review_rows = ''.join(f'''<tr><td><a href="/tools/{site.esc(r['slug'])}#reviews" target="_blank"><b>{site.esc(r['tool_name'])}</b></a></td><td>{site.esc(r['display_name'])}<br><span class="muted">{core.role_label(r['role'])}</span></td><td>{'★'*int(r['rating'])}{'☆'*(5-int(r['rating']))}</td><td class="review-text">{site.esc(r['content'])}</td><td>{site.esc(r['updated_at'][:10])}</td><td><form action="/manage/community/reviews/{r['id']}/delete" method="post" onsubmit="return confirm('确定删除这条评价吗？')"><button class="btn secondary mini">删除</button></form></td></tr>''' for r in reviews) or '<tr><td colspan="6">暂无评价</td></tr>'

    body = f'''<div class="wrap"><a class="backlink" href="/manage/">← 返回工具管理</a><h1>用户 · 投稿 · 评价</h1>
    <div class="summary"><div class="stat"><b>{xiaofeixia_count}</b><span>小飞侠开发者</span></div><div class="stat"><b>{xiaoyouxia_count}</b><span>小游侠用户</span></div><div class="stat"><b>{pending_count}</b><span>待审核投稿</span></div><div class="stat"><b>{review_count}</b><span>产品评价</span></div></div>
    <div class="grid"><div class="card"><h2>导入院内小飞侠</h2><p class="muted">读取现有 CAD-100 授权数据库中的启用用户。不会修改原 CAD 数据库。新导入账号的用户名和初始密码均为姓名。</p><form action="/manage/community/import-cad-users" method="post"><button class="btn">一键导入 / 补充院内用户</button></form></div>
    <div class="card"><h2>手工新增小飞侠</h2><form action="/manage/community/users" method="post"><div class="field"><label>姓名</label><input name="name" required></div><button class="btn">添加小飞侠</button></form></div></div>
    <div class="card"><h2>用户管理</h2><div class="table-wrap"><table class="table"><thead><tr><th>姓名 / 账号</th><th>身份</th><th>邮箱</th><th>状态</th><th>操作</th></tr></thead><tbody>{user_rows}</tbody></table></div></div>
    <div class="card"><h2>开发者投稿审核</h2><p class="muted">小飞侠提交的新工具或新版本只有审核通过后才进入公开工具库。</p><div class="table-wrap"><table class="table"><thead><tr><th>开发者</th><th>工具</th><th>版本</th><th>状态</th><th>操作</th></tr></thead><tbody>{sub_rows}</tbody></table></div></div>
    <div class="card"><h2>产品评价与留言</h2><p class="muted">评价会直接显示在对应产品详情页。管理员可删除明显错误或不适当的评价。</p><div class="table-wrap"><table class="table"><thead><tr><th>工具</th><th>用户</th><th>评分</th><th>留言</th><th>更新日期</th><th></th></tr></thead><tbody>{review_rows}</tbody></table></div></div>
    <div class="card"><h2>小游侠订单（支付预留）</h2><p class="muted">支付暂未正式接入。“测试确认付款”只用于验证购买后下载权限，不会伪造真实支付交易。</p><div class="table-wrap"><table class="table"><thead><tr><th>订单</th><th>用户</th><th>工具</th><th>金额</th><th>状态</th><th></th></tr></thead><tbody>{order_rows}</tbody></table></div></div></div>'''
    return HTMLResponse(page(body))


@app.post('/import-cad-users')
def import_users(request: Request):
    require_admin(request)
    try:
        core.import_cad_users()
    except FileNotFoundError:
        raise HTTPException(404, "没有找到 CAD-100 用户数据库，请检查 CAD100_LICENSE_DB 配置。")
    return RedirectResponse('/manage/community/', 303)


@app.post('/users')
def add_user(request: Request, name: str = Form(...)):
    require_admin(request)
    try:
        core.add_xiaofeixia(name)
    except Exception:
        raise HTTPException(409, "用户已存在。")
    return RedirectResponse('/manage/community/', 303)


@app.post('/users/{user_id}/toggle')
def toggle_user(request: Request, user_id: int):
    require_admin(request)
    with site.db() as conn:
        u = conn.execute("SELECT * FROM community_users WHERE id=?", (user_id,)).fetchone()
        if not u:
            raise HTTPException(404, "用户不存在。")
        conn.execute("UPDATE community_users SET active=?,updated_at=? WHERE id=?", (0 if u['active'] else 1, core.now(), user_id))
    return RedirectResponse('/manage/community/', 303)


@app.post('/users/{user_id}/reset-password')
def reset_password(request: Request, user_id: int):
    require_admin(request)
    with site.db() as conn:
        u = conn.execute("SELECT * FROM community_users WHERE id=? AND role=?", (user_id, core.ROLE_XIAOFEIXIA)).fetchone()
        if not u:
            raise HTTPException(404, "小飞侠用户不存在。")
        salt, digest = core.hash_password(u['display_name'])
        conn.execute("UPDATE community_users SET password_salt=?,password_hash=?,updated_at=? WHERE id=?", (salt, digest, core.now(), user_id))
    return RedirectResponse('/manage/community/', 303)


@app.post('/reviews/{review_id}/delete')
def delete_review(request: Request, review_id: int):
    require_admin(request)
    with site.db() as conn:
        cur = conn.execute("DELETE FROM reviews WHERE id=?", (review_id,))
        if not cur.rowcount:
            raise HTTPException(404, "评价不存在。")
    return RedirectResponse('/manage/community/', 303)


@app.post('/orders/{order_id}/grant')
def grant(request: Request, order_id: int):
    require_admin(request)
    if not core.grant_order(order_id):
        raise HTTPException(404, "订单不存在。")
    return RedirectResponse('/manage/community/', 303)


@app.post('/submissions/{submission_id}/reject')
def reject(request: Request, submission_id: int):
    require_admin(request)
    with site.db() as conn:
        cur = conn.execute("UPDATE tool_submissions SET status='rejected',reviewed_at=? WHERE id=? AND status='pending'", (core.now(), submission_id))
        if not cur.rowcount:
            raise HTTPException(404, "待审核投稿不存在。")
    return RedirectResponse('/manage/community/', 303)


@app.post('/submissions/{submission_id}/approve')
def approve(request: Request, submission_id: int):
    require_admin(request)
    with site.db() as conn:
        s = conn.execute("SELECT s.*,u.display_name FROM tool_submissions s JOIN community_users u ON u.id=s.user_id WHERE s.id=? AND s.status='pending'", (submission_id,)).fetchone()
        if not s:
            raise HTTPException(404, "待审核投稿不存在。")
        stamp = core.now()
        if s['submission_type'] == 'new_tool':
            if conn.execute("SELECT id FROM tools WHERE slug=?", (s['slug'],)).fetchone():
                raise HTTPException(409, "Slug 已存在。")
            cur = conn.execute("INSERT INTO tools(slug,name,tagline,description,category,platform,icon_text,screenshots,downloads,active,created_at,updated_at,owner_user_id,price_cents,developer_name) VALUES(?,?,?,?,?,?,?,'',0,1,?,?,?,?,?)", (s['slug'], s['name'], s['tagline'], s['description'], s['category'], s['platform'], s['icon_text'], stamp, stamp, s['user_id'], s['price_cents'], s['display_name']))
            tool_id = cur.lastrowid
        else:
            tool_id = s['tool_id']
            tool = conn.execute("SELECT * FROM tools WHERE id=?", (tool_id,)).fetchone()
            if not tool:
                raise HTTPException(404, "目标工具不存在。")
            # Only the tool owner can publish an update after ownership is established.
            if tool['owner_user_id'] and int(tool['owner_user_id']) != int(s['user_id']):
                raise HTTPException(403, "该开发者不是此工具的所有者。")

        target_dir = site.PACKAGE_DIR / s['slug']
        target_dir.mkdir(parents=True, exist_ok=True)
        source = Path(s['package_path'])
        if not source.exists():
            raise HTTPException(404, "投稿安装包不存在。")
        target = target_dir / s['package_name']
        if target.exists():
            target = target_dir / f"{submission_id}-{s['package_name']}"
        shutil.copy2(source, target)
        conn.execute("UPDATE releases SET active=0 WHERE tool_id=?", (tool_id,))
        conn.execute("INSERT INTO releases(tool_id,version,notes,package_name,package_path,sha256,size,published_at,active) VALUES(?,?,?,?,?,?,?,?,1)", (tool_id, s['version'], s['notes'], target.name, str(target), s['sha256'], s['size'], stamp))
        conn.execute("UPDATE tool_submissions SET status='approved',reviewed_at=? WHERE id=?", (stamp, submission_id))
    return RedirectResponse('/manage/community/', 303)
