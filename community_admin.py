import shutil
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import admin_portal
import community_core as core

app = FastAPI(title="Community Admin",docs_url=None,redoc_url=None,openapi_url=None)

CSS='''<style>.wrap{max-width:1180px;margin:36px auto;padding:0 20px 70px}.card{background:#fff;border:1px solid #e6e6e3;border-radius:22px;padding:22px;margin-bottom:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.badge{padding:4px 8px;border-radius:999px;background:#eee;font-size:9px}.pending{background:#fff3cd}.ok{background:#dff4e3}.actions{display:flex;gap:7px;flex-wrap:wrap}.mini{height:34px!important;padding:0 12px!important;font-size:10px!important}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>'''

def require_admin(request): admin_portal.require_admin(request)
def page(body,title="社区管理 · 小飞侠设计100%"): return site.page(CSS+body,title)

@app.get('/',response_class=HTMLResponse)
def dashboard(request: Request):
    require_admin(request); core.init_db()
    with site.db() as conn:
        users=conn.execute("SELECT * FROM community_users ORDER BY role,id DESC").fetchall()
        subs=conn.execute("SELECT s.*,u.display_name FROM tool_submissions s JOIN community_users u ON u.id=s.user_id ORDER BY CASE s.status WHEN 'pending' THEN 0 ELSE 1 END,s.id DESC").fetchall()
        orders=conn.execute("SELECT o.*,u.display_name,t.name tool_name FROM orders o JOIN community_users u ON u.id=o.user_id JOIN tools t ON t.id=o.tool_id ORDER BY o.id DESC LIMIT 100").fetchall()
    user_rows=''.join(f'<tr><td>{site.esc(u["display_name"])}</td><td>{core.role_label(u["role"])}</td><td>{site.esc(u["email"] or "院内账号")}</td><td>{"启用" if u["active"] else "停用"}</td></tr>' for u in users) or '<tr><td colspan="4">暂无用户</td></tr>'
    sub_rows=''.join(f'''<tr><td>{site.esc(s['display_name'])}</td><td>{site.esc(s['name'] or s['slug'])}</td><td>{site.esc(s['version'])}</td><td><span class="badge {'pending' if s['status']=='pending' else 'ok'}">{site.esc(s['status'])}</span></td><td><div class="actions">{f'<form action="/manage/community/submissions/{s["id"]}/approve" method="post"><button class="btn mini">审核通过</button></form><form action="/manage/community/submissions/{s["id"]}/reject" method="post"><button class="btn secondary mini">驳回</button></form>' if s['status']=='pending' else ''}</div></td></tr>''' for s in subs) or '<tr><td colspan="5">暂无投稿</td></tr>'
    order_rows=''.join(f'''<tr><td>{site.esc(o['order_no'])}</td><td>{site.esc(o['display_name'])}</td><td>{site.esc(o['tool_name'])}</td><td>¥{o['amount_cents']/100:.2f}</td><td>{site.esc(o['status'])}</td><td>{f'<form action="/manage/community/orders/{o["id"]}/grant" method="post"><button class="btn mini">测试确认付款</button></form>' if o['status']=='pending' else ''}</td></tr>''' for o in orders) or '<tr><td colspan="6">暂无订单</td></tr>'
    body=f'''<div class="wrap"><a class="backlink" href="/manage/">← 返回工具管理</a><h1>用户 · 投稿 · 订单</h1><div class="grid"><div class="card"><h2>院内小飞侠</h2><p>直接从现有 CAD-100 授权数据库导入院内人员，用户名和初始密码均为姓名。</p><form action="/manage/community/import-cad-users" method="post"><button class="btn">导入 / 补充院内用户</button></form></div><div class="card"><h2>手工新增小飞侠</h2><form action="/manage/community/users" method="post"><div class="field"><label>姓名</label><input name="name" required></div><button class="btn">添加</button></form></div></div><div class="card"><h2>用户</h2><table class="table"><thead><tr><th>姓名</th><th>身份</th><th>账号</th><th>状态</th></tr></thead><tbody>{user_rows}</tbody></table></div><div class="card"><h2>开发者投稿审核</h2><table class="table"><thead><tr><th>开发者</th><th>工具</th><th>版本</th><th>状态</th><th></th></tr></thead><tbody>{sub_rows}</tbody></table></div><div class="card"><h2>小游侠订单</h2><p style="font-size:11px;color:#888">“测试确认付款”仅用于支付接口上线前测试授权。正式上线后由微信/支付宝回调自动确认。</p><table class="table"><thead><tr><th>订单</th><th>用户</th><th>工具</th><th>金额</th><th>状态</th><th></th></tr></thead><tbody>{order_rows}</tbody></table></div></div>'''
    return HTMLResponse(page(body))

@app.post('/import-cad-users')
def import_users(request: Request):
    require_admin(request)
    try: core.import_cad_users()
    except FileNotFoundError: raise HTTPException(404,"没有找到 CAD-100 用户数据库，请检查 CAD100_LICENSE_DB 配置。")
    return RedirectResponse('/manage/community/',303)

@app.post('/users')
def add_user(request: Request,name: str=Form(...)):
    require_admin(request)
    try: core.add_xiaofeixia(name)
    except Exception: raise HTTPException(409,"用户已存在。")
    return RedirectResponse('/manage/community/',303)

@app.post('/orders/{order_id}/grant')
def grant(request: Request,order_id: int):
    require_admin(request)
    if not core.grant_order(order_id): raise HTTPException(404,"订单不存在。")
    return RedirectResponse('/manage/community/',303)

@app.post('/submissions/{submission_id}/reject')
def reject(request: Request,submission_id: int):
    require_admin(request)
    with site.db() as conn:
        cur=conn.execute("UPDATE tool_submissions SET status='rejected',reviewed_at=? WHERE id=? AND status='pending'",(core.now(),submission_id))
        if not cur.rowcount: raise HTTPException(404,"待审核投稿不存在。")
    return RedirectResponse('/manage/community/',303)

@app.post('/submissions/{submission_id}/approve')
def approve(request: Request,submission_id: int):
    require_admin(request)
    with site.db() as conn:
        s=conn.execute("SELECT s.*,u.display_name FROM tool_submissions s JOIN community_users u ON u.id=s.user_id WHERE s.id=? AND s.status='pending'",(submission_id,)).fetchone()
        if not s: raise HTTPException(404,"待审核投稿不存在。")
        stamp=core.now()
        if s['submission_type']=='new_tool':
            if conn.execute("SELECT id FROM tools WHERE slug=?",(s['slug'],)).fetchone(): raise HTTPException(409,"Slug 已存在。")
            cur=conn.execute("INSERT INTO tools(slug,name,tagline,description,category,platform,icon_text,screenshots,downloads,active,created_at,updated_at,owner_user_id,price_cents,developer_name) VALUES(?,?,?,?,?,?,?,'',0,1,?,?,?,?,?)",(s['slug'],s['name'],s['tagline'],s['description'],s['category'],s['platform'],s['icon_text'],stamp,stamp,s['user_id'],s['price_cents'],s['display_name']))
            tool_id=cur.lastrowid
        else:
            tool_id=s['tool_id']; tool=conn.execute("SELECT * FROM tools WHERE id=?",(tool_id,)).fetchone()
            if not tool: raise HTTPException(404,"目标工具不存在。")
        target_dir=site.PACKAGE_DIR/s['slug']; target_dir.mkdir(parents=True,exist_ok=True); source=Path(s['package_path']); target=target_dir/s['package_name']
        if target.exists(): target=target_dir/f"{submission_id}-{s['package_name']}"
        shutil.copy2(source,target)
        conn.execute("UPDATE releases SET active=0 WHERE tool_id=?",(tool_id,))
        conn.execute("INSERT INTO releases(tool_id,version,notes,package_name,package_path,sha256,size,published_at,active) VALUES(?,?,?,?,?,?,?,?,1)",(tool_id,s['version'],s['notes'],target.name,str(target),s['sha256'],s['size'],stamp))
        conn.execute("UPDATE tool_submissions SET status='approved',reviewed_at=? WHERE id=?",(stamp,submission_id))
    return RedirectResponse('/manage/community/',303)
