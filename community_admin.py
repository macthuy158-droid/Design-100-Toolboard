import shutil
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import admin_portal
import coin_core
import community_core as core

app = FastAPI(title="Community Admin", docs_url=None, redoc_url=None, openapi_url=None)

CSS = '''<style>
.wrap{max-width:1100px;margin:34px auto;padding:0 20px 70px}.top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:24px}.top h1{margin:5px 0 0;font-size:30px}.nav{display:flex;gap:8px;flex-wrap:wrap}.card{background:#fff;border:1px solid #e6e6e3;border-radius:22px;padding:22px;margin-bottom:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.badge{display:inline-flex;padding:5px 9px;border-radius:999px;background:#eee;font-size:9px}.pending{background:#fff2c7}.ok{background:#e2f3e5}.off{background:#f3dede}.actions{display:flex;gap:7px;flex-wrap:wrap}.mini{height:32px!important;padding:0 10px!important;font-size:10px!important}.muted{font-size:11px;color:#888;line-height:1.7}.summary{display:flex;gap:10px;margin:16px 0 22px;flex-wrap:wrap}.stat{background:#f5f5f2;border-radius:14px;padding:13px 16px;min-width:120px}.stat b{display:block;font-size:20px}.stat span{font-size:9px;color:#888}.table-wrap{overflow-x:auto}.table{width:100%;min-width:760px}.review-item{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center}.review-main h3{margin:0 0 7px;font-size:18px}.review-meta{font-size:11px;color:#777;line-height:1.8}.review-note{margin-top:10px;padding:11px 13px;border-radius:12px;background:#f6f6f3;font-size:11px;color:#666;white-space:pre-line}.price-change{font-weight:750;color:#111}.empty{padding:40px 20px;text-align:center;color:#888}.section-title{font-size:13px;font-weight:720;color:#777;margin:24px 0 10px}.card h2{margin:0 0 15px;font-size:19px}.coin-adjust{display:flex;gap:6px;align-items:center}.coin-adjust input{height:30px;border:1px solid #d7d7d3;border-radius:8px;padding:0 8px;background:#fff;font-size:11px}.coin-adjust input[name=delta]{width:82px}.coin-adjust input[name=note]{width:118px}@media(max-width:760px){.top{align-items:flex-start;flex-direction:column}.grid{grid-template-columns:1fr}.review-item{grid-template-columns:1fr}.review-actions{justify-self:start}}
</style>'''


def require_admin(request):
    admin_portal.require_admin(request)


def page(body, title="管理后台 · 小飞侠设计100%"):
    return site.page(CSS + body, title)


def admin_nav(active=""):
    return f'''<div class="nav">
    <a class="btn secondary" href="/manage/">后台首页</a>
    <a class="btn {'secondary' if active!='review' else ''}" href="/manage/community/review">投稿审核</a>
    <a class="btn secondary" href="/manage/tools/">工具管理</a>
    <a class="btn {'secondary' if active!='users' else ''}" href="/manage/community/users">用户管理</a>
    <a class="btn {'secondary' if active!='invites' else ''}" href="/manage/community/invites">邀请码</a>
    <a class="btn {'secondary' if active!='coins' else ''}" href="/manage/community/coins">币值管理</a>
    <a class="btn secondary" href="/manage/courses/">课程管理</a>
    </div>'''


@app.get('/')
def dashboard(request: Request):
    require_admin(request)
    return RedirectResponse('/manage/community/review', 303)


@app.get('/review', response_class=HTMLResponse)
def review_center(request: Request):
    require_admin(request)
    core.init_db()
    with site.db() as conn:
        pending = conn.execute('''
            SELECT s.*,u.display_name,
                   t.name current_tool_name,t.price_cents current_price,t.owner_user_id
            FROM tool_submissions s
            JOIN community_users u ON u.id=s.user_id
            LEFT JOIN tools t ON t.id=s.tool_id
            WHERE s.status='pending'
            ORDER BY s.id ASC
        ''').fetchall()
        recent = conn.execute('''
            SELECT s.*,u.display_name
            FROM tool_submissions s JOIN community_users u ON u.id=s.user_id
            WHERE s.status!='pending'
            ORDER BY s.id DESC LIMIT 12
        ''').fetchall()

    items=[]
    for s in pending:
        kind='新工具' if s['submission_type']=='new_tool' else '版本更新'
        old_price=int(s['current_price'] or 0)/100 if s['submission_type']=='new_release' else None
        new_price=int(s['price_cents'] or 0)/100
        price_text=f'¥{new_price:.2f}' if old_price is None else f'¥{old_price:.2f} → ¥{new_price:.2f}'
        owner_note=''
        if s['submission_type']=='new_release' and s['owner_user_id'] and int(s['owner_user_id']) != int(s['user_id']):
            owner_note='<div class="review-note">⚠ 该投稿人不是当前工具所有者，不能审核通过。</div>'
        notes=site.esc(s['notes'] or '无更新说明')
        items.append(f'''<div class="card"><div class="review-item"><div class="review-main">
        <span class="badge pending">待审核 · {kind}</span><h3>{site.esc(s['name'] or s['slug'])} · v{site.esc(s['version'])}</h3>
        <div class="review-meta">开发者：<b>{site.esc(s['display_name'])}</b>　·　价格：<span class="price-change">{price_text}</span>　·　安装包：{site.format_bytes(s['size'])}</div>
        <div class="review-note">{notes}</div>{owner_note}</div>
        <div class="actions review-actions"><form action="/manage/community/submissions/{s['id']}/approve" method="post"><button class="btn mini">通过</button></form><form action="/manage/community/submissions/{s['id']}/reject" method="post"><button class="btn secondary mini">驳回</button></form></div></div></div>''')

    recent_rows=''.join(f'''<tr><td>{site.esc(s['display_name'])}</td><td>{site.esc(s['name'] or s['slug'])}</td><td>{'新工具' if s['submission_type']=='new_tool' else '版本更新'}</td><td>v{site.esc(s['version'])}</td><td><span class="badge {'ok' if s['status']=='approved' else 'off'}">{'已通过' if s['status']=='approved' else '已驳回'}</span></td></tr>''' for s in recent) or '<tr><td colspan="5">暂无历史审核记录</td></tr>'

    body=f'''<div class="wrap"><div class="top"><div><div class="eyebrow">ADMIN</div><h1>投稿审核</h1><div class="muted">这里只处理小飞侠提交的新工具和版本更新。</div></div>{admin_nav('review')}</div>
    <div class="summary"><div class="stat"><b>{len(pending)}</b><span>待审核</span></div></div>
    {''.join(items) if items else '<div class="card empty">当前没有待审核投稿。</div>'}
    <div class="section-title">最近审核记录</div><div class="card table-wrap"><table class="table"><thead><tr><th>开发者</th><th>工具</th><th>类型</th><th>版本</th><th>结果</th></tr></thead><tbody>{recent_rows}</tbody></table></div></div>'''
    return HTMLResponse(page(body, '投稿审核 · 小飞侠设计100%'))


@app.get('/users', response_class=HTMLResponse)
def users_page(request: Request):
    require_admin(request)
    core.init_db()
    with site.db() as conn:
        users=conn.execute("SELECT * FROM community_users ORDER BY CASE role WHEN 'xiaofeixia' THEN 0 ELSE 1 END, display_name COLLATE NOCASE").fetchall()
        xfx=conn.execute("SELECT COUNT(*) c FROM community_users WHERE role='xiaofeixia'").fetchone()['c']
        xyx=conn.execute("SELECT COUNT(*) c FROM community_users WHERE role='xiaoyouxia'").fetchone()['c']

    rows=[]
    for u in users:
        state='<span class="badge ok">启用</span>' if u['active'] else '<span class="badge off">停用</span>'
        toggle='停用' if u['active'] else '启用'
        reset=f'<form action="/manage/community/users/{u["id"]}/reset-password" method="post" onsubmit="return confirm(\'确定将密码重置为姓名吗？\')"><button class="btn secondary mini">重置密码</button></form>' if u['role']==core.ROLE_XIAOFEIXIA else ''
        rows.append(f'''<tr><td><b>{site.esc(u['display_name'])}</b><br><span class="muted">{site.esc(u['username'])}</span></td><td>{core.role_label(u['role'])}</td><td>{site.esc(u['email'] or '院内账号')}</td><td>{state}</td><td><div class="actions"><form action="/manage/community/users/{u['id']}/toggle" method="post"><button class="btn secondary mini">{toggle}</button></form>{reset}</div></td></tr>''')

    body=f'''<div class="wrap"><div class="top"><div><div class="eyebrow">ADMIN</div><h1>用户管理</h1><div class="muted">只管理账号，不在这里处理工具和投稿。</div></div>{admin_nav('users')}</div>
    <div class="summary"><div class="stat"><b>{xfx}</b><span>小飞侠</span></div><div class="stat"><b>{xyx}</b><span>小游侠</span></div></div>
    <div class="grid"><div class="card"><h2>导入院内小飞侠</h2><p class="muted">从现有 CAD-100 授权数据库补充院内人员。</p><form action="/manage/community/import-cad-users" method="post"><button class="btn">一键导入</button></form></div>
    <div class="card"><h2>新增小飞侠</h2><form action="/manage/community/users" method="post"><div class="field"><label>姓名</label><input name="name" required></div><button class="btn">添加</button></form></div></div>
    <div class="card table-wrap"><table class="table"><thead><tr><th>姓名 / 账号</th><th>身份</th><th>邮箱</th><th>状态</th><th>操作</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="5">暂无用户</td></tr>'}</tbody></table></div></div>'''
    return HTMLResponse(page(body, '用户管理 · 小飞侠设计100%'))


@app.get('/coins', response_class=HTMLResponse)
def coins_page(request: Request):
    require_admin(request)
    core.init_db(); coin_core.init_db()
    with site.db() as conn:
        users=conn.execute("SELECT * FROM community_users WHERE active=1 ORDER BY CASE role WHEN 'xiaofeixia' THEN 0 ELSE 1 END, display_name COLLATE NOCASE").fetchall()
        rows=[]; total=0
        for u in users:
            bal=coin_core.balance(conn,u['id'])
            total+=bal
            rows.append(f'''<tr><td><b>{site.esc(u['display_name'])}</b><br><span class="muted">{site.esc(u['username'])}</span></td>
            <td>{core.role_label(u['role'])}</td><td><b>{bal}</b> {coin_core.COIN_NAME}</td>
            <td><form class="coin-adjust" action="/manage/community/coins/{u['id']}/adjust" method="post">
            <input name="delta" type="number" step="1" placeholder="+10 / -5" required>
            <input name="note" placeholder="备注（可选）">
            <button class="btn secondary mini">调整</button></form></td></tr>''')
        recent=conn.execute("SELECT l.*,u.display_name FROM coin_ledger l JOIN community_users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT 30").fetchall()
    led=''.join(f'''<tr><td>{site.esc(r['display_name'])}</td><td>{site.esc(coin_core.REASON_LABELS.get(r['reason'],r['reason']))}</td>
    <td>{site.esc(r['note'] or '—')}</td><td>{'+' if int(r['delta'])>0 else ''}{int(r['delta'])}</td>
    <td class="muted">{site.esc((r['created_at'] or '')[:16].replace('T',' '))}</td></tr>''' for r in recent) or '<tr><td colspan="5">暂无流水</td></tr>'
    body=f'''<div class="wrap"><div class="top"><div><div class="eyebrow">ADMIN</div><h1>币值管理</h1><div class="muted">注册赠送 {coin_core.REGISTER_BONUS} 个，发布工具审核通过再得 {coin_core.PUBLISH_REWARD} 个。这里可人工充值或扣减：正数为充值，负数为扣减。</div></div>{admin_nav('coins')}</div>
    <div class="summary"><div class="stat"><b>{total}</b><span>流通中{coin_core.COIN_NAME}</span></div><div class="stat"><b>{len(rows)}</b><span>启用账号</span></div></div>
    <div class="card table-wrap"><h2>用户余额</h2><table class="table"><thead><tr><th>姓名 / 账号</th><th>身份</th><th>余额</th><th>充值 / 扣减</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="4">暂无用户</td></tr>'}</tbody></table></div>
    <div class="card table-wrap"><h2>最近流水</h2><table class="table"><thead><tr><th>用户</th><th>类型</th><th>说明</th><th>变动</th><th>时间</th></tr></thead><tbody>{led}</tbody></table></div></div>'''
    return HTMLResponse(page(body, '币值管理 · 小飞侠设计100%'))


@app.post('/coins/{user_id}/adjust')
def adjust_coins(request: Request, user_id: int, delta: int = Form(...), note: str = Form("")):
    require_admin(request)
    coin_core.init_db()
    if delta == 0:
        raise HTTPException(400, "调整数量不能为 0。")
    if abs(delta) > 100000:
        raise HTTPException(400, "单次调整不能超过 100000。")
    with site.db() as conn:
        u=conn.execute("SELECT * FROM community_users WHERE id=?", (user_id,)).fetchone()
        if not u: raise HTTPException(404, "用户不存在。")
        if delta < 0 and coin_core.balance(conn,user_id) + delta < 0:
            raise HTTPException(409, "扣减后余额会变成负数。")
        coin_core.adjust(conn, user_id, delta, note.strip()[:120] or "管理员调整")
    return RedirectResponse('/manage/community/coins', 303)


@app.get('/invites', response_class=HTMLResponse)
def invites_page(request: Request):
    require_admin(request)
    core.init_db()
    with site.db() as conn:
        invites = conn.execute("SELECT * FROM xiaofeixia_invites ORDER BY used ASC, real_name COLLATE NOCASE").fetchall()
    total = len(invites)
    unused = sum(1 for i in invites if not i['used'])

    rows = []
    for inv in invites:
        status = '<span class="badge ok">已使用</span>' if inv['used'] else '<span class="badge pending">未使用</span>'
        used_info = site.esc(inv['used_at'][:10]) if inv['used_at'] else '—'
        rows.append(f'<tr><td><b>{site.esc(inv["real_name"])}</b></td><td><code>{site.esc(inv["code"])}</code></td><td>{status}</td><td>{used_info}</td></tr>')

    body = f'''<div class="wrap"><div class="top"><div><div class="eyebrow">ADMIN</div><h1>邀请码管理</h1><div class="muted">小飞侠注册需要邀请码，一人一码，与真实姓名绑定。</div></div>{admin_nav('invites')}</div>
    <div class="summary"><div class="stat"><b>{total}</b><span>总计</span></div><div class="stat"><b>{unused}</b><span>未使用</span></div></div>
    <div class="grid"><div class="card"><h2>从 CAD 名单批量生成</h2><p class="muted">为 CAD-100 授权库中所有尚未有邀请码的员工生成邀请码。</p><form action="/manage/community/invites/batch" method="post"><button class="btn">批量生成</button></form></div>
    <div class="card"><h2>单独生成邀请码</h2><form action="/manage/community/invites" method="post"><div class="field"><label>真实姓名</label><input name="real_name" required></div><button class="btn">生成</button></form></div></div>
    <div class="card table-wrap"><table class="table"><thead><tr><th>姓名</th><th>邀请码</th><th>状态</th><th>使用日期</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="4">暂无邀请码，请先生成。</td></tr>'}</tbody></table></div></div>'''
    return HTMLResponse(page(body, '邀请码管理 · 小飞侠设计100%'))


@app.post('/invites')
def create_invite(request: Request, real_name: str = Form(...)):
    require_admin(request)
    try:
        core.create_invite(real_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse('/manage/community/invites', 303)


@app.post('/invites/batch')
def batch_invites(request: Request):
    require_admin(request)
    try:
        core.batch_create_invites()
    except FileNotFoundError:
        raise HTTPException(404, "没有找到 CAD-100 用户数据库，请检查 CAD100_LICENSE_DB 配置。")
    return RedirectResponse('/manage/community/invites', 303)


@app.post('/import-cad-users')
def import_users(request: Request):
    require_admin(request)
    try:
        core.import_cad_users()
    except FileNotFoundError:
        raise HTTPException(404, "没有找到 CAD-100 用户数据库，请检查 CAD100_LICENSE_DB 配置。")
    return RedirectResponse('/manage/community/users', 303)


@app.post('/users')
def add_user(request: Request, name: str = Form(...)):
    require_admin(request)
    try:
        core.add_xiaofeixia(name)
    except Exception:
        raise HTTPException(409, "用户已存在。")
    return RedirectResponse('/manage/community/users', 303)


@app.post('/users/{user_id}/toggle')
def toggle_user(request: Request, user_id: int):
    require_admin(request)
    with site.db() as conn:
        u=conn.execute("SELECT * FROM community_users WHERE id=?", (user_id,)).fetchone()
        if not u: raise HTTPException(404, "用户不存在。")
        conn.execute("UPDATE community_users SET active=?,updated_at=? WHERE id=?", (0 if u['active'] else 1, core.now(), user_id))
    return RedirectResponse('/manage/community/users', 303)


@app.post('/users/{user_id}/reset-password')
def reset_password(request: Request, user_id: int):
    require_admin(request)
    with site.db() as conn:
        u=conn.execute("SELECT * FROM community_users WHERE id=? AND role=?", (user_id, core.ROLE_XIAOFEIXIA)).fetchone()
        if not u: raise HTTPException(404, "小飞侠用户不存在。")
        salt,digest=core.hash_password(u['display_name'])
        conn.execute("UPDATE community_users SET password_salt=?,password_hash=?,updated_at=? WHERE id=?", (salt,digest,core.now(),user_id))
    return RedirectResponse('/manage/community/users', 303)


@app.post('/submissions/{submission_id}/reject')
def reject(request: Request, submission_id: int):
    require_admin(request)
    with site.db() as conn:
        cur=conn.execute("UPDATE tool_submissions SET status='rejected',reviewed_at=? WHERE id=? AND status='pending'", (core.now(),submission_id))
        if not cur.rowcount: raise HTTPException(404, "待审核投稿不存在。")
    return RedirectResponse('/manage/community/review', 303)


@app.post('/submissions/{submission_id}/approve')
def approve(request: Request, submission_id: int):
    require_admin(request)
    core.init_db()
    with site.db() as conn:
        s=conn.execute("SELECT s.*,u.display_name FROM tool_submissions s JOIN community_users u ON u.id=s.user_id WHERE s.id=? AND s.status='pending'", (submission_id,)).fetchone()
        if not s: raise HTTPException(404, "待审核投稿不存在。")
        stamp=core.now()
        sub_tool_type=s['tool_type'] if 'tool_type' in s.keys() else 'desktop'
        sub_app_url=s['app_url'] if 'app_url' in s.keys() else ''
        is_web=sub_tool_type=='web_app'
        if s['submission_type'] in ('new_tool','new_web_app'):
            if conn.execute("SELECT id FROM tools WHERE slug=?", (s['slug'],)).fetchone(): raise HTTPException(409, "Slug 已存在。")
            cur=conn.execute("INSERT INTO tools(slug,name,tagline,description,category,platform,icon_text,screenshots,downloads,active,created_at,updated_at,owner_user_id,price_cents,developer_name,tool_type,app_url) VALUES(?,?,?,?,?,?,?,'',0,1,?,?,?,?,?,?,?)", (s['slug'],s['name'],s['tagline'],s['description'],s['category'],s['platform'],s['icon_text'],stamp,stamp,s['user_id'],s['price_cents'],s['display_name'],sub_tool_type,sub_app_url))
            tool_id=cur.lastrowid
        elif s['submission_type']=='new_release':
            tool_id=s['tool_id']
            tool=conn.execute("SELECT * FROM tools WHERE id=?", (tool_id,)).fetchone()
            if not tool: raise HTTPException(404, "目标工具不存在。")
            if not tool['owner_user_id'] or int(tool['owner_user_id'])!=int(s['user_id']): raise HTTPException(403, "只有该工具原开发者的版本投稿可以审核通过。")
            conn.execute("UPDATE tools SET price_cents=?,developer_name=?,updated_at=? WHERE id=?", (s['price_cents'],s['display_name'],stamp,tool_id))
        else:
            raise HTTPException(400, "投稿类型无效。")

        sub_price=int((s['feixia_coin_price'] if 'feixia_coin_price' in s.keys() else 0) or 0)
        conn.execute("UPDATE tools SET feixia_coin_price=? WHERE id=?",(sub_price,tool_id))
        coin_core.grant_publish_reward(conn, s['user_id'], submission_id, tool_id, note=s['name'] or s['slug'])

        if is_web:
            conn.execute("UPDATE releases SET active=0 WHERE tool_id=?", (tool_id,))
            conn.execute("INSERT INTO releases(tool_id,version,notes,package_name,package_path,sha256,size,published_at,active) VALUES(?,?,?,?,?,?,?,?,1)", (tool_id,s['version'],s['notes'],'','','',0,stamp))
        else:
            target_dir=site.PACKAGE_DIR/s['slug']; target_dir.mkdir(parents=True,exist_ok=True)
            source=Path(s['package_path'])
            if not source.exists(): raise HTTPException(404, "投稿安装包不存在。")
            target=target_dir/s['package_name']
            if target.exists(): target=target_dir/f"{submission_id}-{s['package_name']}"
            shutil.copy2(source,target)
            conn.execute("UPDATE releases SET active=0 WHERE tool_id=?", (tool_id,))
            conn.execute("INSERT INTO releases(tool_id,version,notes,package_name,package_path,sha256,size,published_at,active) VALUES(?,?,?,?,?,?,?,?,1)", (tool_id,s['version'],s['notes'],target.name,str(target),s['sha256'],s['size'],stamp))
        conn.execute("UPDATE tool_submissions SET status='approved',reviewed_at=? WHERE id=?", (stamp,submission_id))
    return RedirectResponse('/manage/community/review', 303)


# Compatibility-only actions kept out of the main admin UI until real payment/moderation is added.
@app.post('/orders/{order_id}/grant')
def grant(request: Request, order_id: int):
    require_admin(request)
    if not core.grant_order(order_id): raise HTTPException(404, "订单不存在或金额无效。")
    return RedirectResponse('/manage/', 303)


@app.post('/reviews/{review_id}/delete')
def delete_review(request: Request, review_id: int):
    require_admin(request)
    with site.db() as conn:
        cur=conn.execute("DELETE FROM reviews WHERE id=?", (review_id,))
        if not cur.rowcount: raise HTTPException(404, "评价不存在。")
    return RedirectResponse('/manage/', 303)
