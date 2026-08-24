import hmac
import os

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import coin_core
from app_v2 import ADMIN_PASSWORD, COOKIE_NAME, db, esc, format_bytes, init_db, latest_release, now_text, page, session_token, valid_session
from community_core import DEFAULT_TOOL_CATEGORY, TOOL_CATEGORIES

ADMIN_USERNAME = os.getenv("TOOLBOARD_ADMIN_USERNAME", "admin").strip() or "admin"

app = FastAPI(title="Design 100 Admin", docs_url=None, redoc_url=None, openapi_url=None)

ADMIN_CSS = r'''
<style>
.admin-shell{max-width:1080px;margin:auto;padding:36px 22px 70px}.admin-head{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:26px}.admin-head h1{margin:6px 0 0;font-size:30px}.admin-sub{font-size:12px;color:#85878b;line-height:1.7;margin-top:7px}.admin-actions{display:flex;gap:8px;flex-wrap:wrap}.admin-home{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.entry{display:block;background:#fff;border:1px solid #e6e6e3;border-radius:22px;padding:24px;color:#111}.entry h2{margin:0 0 8px;font-size:21px}.entry p{margin:0;color:#888;font-size:11px;line-height:1.7}.entry b{display:block;font-size:28px;margin-bottom:16px}.admin-tools{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.admin-tool{background:#fff;border:1px solid #e6e6e3;border-radius:22px;padding:20px}.admin-tool h2{margin:0 0 5px;font-size:20px}.meta{font-size:10px;color:#888}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:16px 0}.stat{background:#f5f5f2;border-radius:12px;padding:10px}.stat b{display:block;font-size:13px}.stat span{font-size:8px;color:#92949a}.admin-card{background:#fff;border:1px solid #e6e6e3;border-radius:20px;padding:21px}.split{display:grid;grid-template-columns:1.2fr .8fr;gap:16px}.badge{display:inline-flex;padding:5px 8px;border-radius:999px;background:#eee;font-size:9px}.badge.current{background:#111;color:#fff}.badge.off{background:#f3e2e2;color:#8f2929}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;border-bottom:1px solid #eee;padding:10px 8px;font-size:11px}.table th{color:#888}.backlink{display:inline-flex;font-size:11px;color:#777;margin-bottom:14px}.muted{font-size:11px;color:#888;line-height:1.7}.owner-row{background:#f5f5f2;border-radius:13px;padding:13px;margin-bottom:9px}.owner-row b{display:block;font-size:13px}.owner-row span{font-size:9px;color:#888}@media(max-width:800px){.admin-home{grid-template-columns:1fr}.admin-tools,.split{grid-template-columns:1fr}.admin-head{align-items:flex-start;flex-direction:column}.stats{grid-template-columns:1fr 1fr}}
</style>
'''


def admin_page(body, title="管理后台"):
    return page(ADMIN_CSS + body, title)


def require_admin(request: Request):
    if not valid_session(request):
        raise HTTPException(status_code=401, detail="请先登录后台。")


@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request):
    init_db()
    if not valid_session(request):
        login='''<div class="loginwrap"><div class="login"><div class="eyebrow">DESIGN 100</div><h1>管理员登录</h1><form id="f"><div class="field"><label>管理员用户名</label><input id="u" autocomplete="username" autofocus></div><div class="field"><label>管理员密码</label><input id="p" type="password" autocomplete="current-password"></div><button class="btn">进入后台</button><div id="m" class="msg"></div></form></div></div><script>document.getElementById("f").addEventListener("submit",async e=>{e.preventDefault();const r=await fetch("/manage/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:document.getElementById("u").value,password:document.getElementById("p").value})});const j=await r.json().catch(()=>({}));if(r.ok)location.href="/manage/";else document.getElementById("m").textContent=j.detail||"登录失败"})</script>'''
        return HTMLResponse(admin_page(login))
    with db() as conn:
        pending=conn.execute("SELECT COUNT(*) c FROM tool_submissions WHERE status='pending'").fetchone()['c'] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool_submissions'").fetchone() else 0
        tools=conn.execute("SELECT COUNT(*) c FROM tools").fetchone()['c']
        users=conn.execute("SELECT COUNT(*) c FROM community_users").fetchone()['c'] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='community_users'").fetchone() else 0
        courses=conn.execute("SELECT COUNT(*) c FROM courses").fetchone()['c'] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='courses'").fetchone() else 0
    body=f'''<div class="admin-shell"><div class="admin-head"><div><div class="eyebrow">DESIGN 100 · ADMIN</div><h1>管理后台</h1><div class="admin-sub">工具、用户与官方课程的维护入口。</div></div><button class="btn secondary" onclick="fetch('/manage/logout',{{method:'POST'}}).then(()=>location.href='/manage/')">退出</button></div><div class="admin-home">
    <a class="entry" href="/manage/community/review"><b>{pending}</b><h2>投稿审核</h2><p>审核新工具和版本更新。</p></a>
    <a class="entry" href="/manage/tools/"><b>{tools}</b><h2>工具管理</h2><p>修改资料、价格、上下架，查看版本历史。</p></a>
    <a class="entry" href="/manage/community/users"><b>{users}</b><h2>用户管理</h2><p>管理小飞侠与小游侠账号。</p></a>
    <a class="entry" href="/manage/courses/"><b>{courses}</b><h2>课程管理</h2><p>创建官方设计课程，维护课时与上下架。</p></a>
    <a class="entry" href="/manage/community/coins"><b>币</b><h2>币值管理</h2><p>查看飞侠币 / 游侠币余额，为小游侠充值。</p></a>
    </div></div>'''
    return HTMLResponse(admin_page(body))


@app.get('/tools/', response_class=HTMLResponse)
def tools_page(request: Request):
    require_admin(request)
    with db() as conn:
        tools=conn.execute("SELECT * FROM tools ORDER BY active DESC,downloads DESC,id DESC").fetchall()
        cards=[]
        for t in tools:
            current=latest_release(conn,t['id']); version=current['version'] if current else '未发布'; developer=t['developer_name'] or '未绑定'; fx=coin_core.coin_price(t,coin_core.FEIXIA); yx=coin_core.coin_price(t,coin_core.YOUXIA)
            status='<span class="badge current">已上架</span>' if t['active'] else '<span class="badge off">已下架</span>'
            cards.append(f'''<div class="admin-tool"><h2>{esc(t['name'])}</h2><div class="meta">{esc(t['category'])} · {esc(t['platform'])} · {status}</div><div class="stats"><div class="stat"><b>v{esc(version)}</b><span>版本</span></div><div class="stat"><b>{fx}</b><span>院内飞侠币</span></div><div class="stat"><b>{yx}</b><span>院外游侠币</span></div><div class="stat"><b>{esc(developer)}</b><span>开发者</span></div><div class="stat"><b>{int(t['downloads']):,}</b><span>下载</span></div></div><div class="admin-actions"><a class="btn" href="/manage/tools/{esc(t['slug'])}">管理</a><a class="btn secondary" href="/tools/{esc(t['slug'])}" target="_blank">前台</a></div></div>''')
    body=f'''<div class="admin-shell"><div class="admin-head"><div><a class="backlink" href="/manage/">← 返回后台</a><h1>工具管理</h1><div class="admin-sub">这里只管理工具资料，不负责上传和发布。</div></div></div><div class="admin-tools">{''.join(cards) if cards else '<div class="admin-card muted">暂无工具</div>'}</div></div>'''
    return HTMLResponse(admin_page(body,'工具管理'))


@app.get('/tools/{slug}', response_class=HTMLResponse)
def tool_admin(request: Request, slug: str):
    require_admin(request)
    with db() as conn:
        t=conn.execute("SELECT * FROM tools WHERE slug=?",(slug,)).fetchone()
        if not t: raise HTTPException(404,"工具不存在。")
        releases=conn.execute("SELECT * FROM releases WHERE tool_id=? ORDER BY id DESC",(t['id'],)).fetchall(); current=latest_release(conn,t['id'])
    rows=''.join(f'<tr><td>v{esc(r["version"])}</td><td>{"当前" if r["active"] else "历史"}</td><td>{esc(r["published_at"][:10])}</td><td>{esc(format_bytes(r["size"]))}</td><td>{esc(r["notes"] or "—")}</td></tr>' for r in releases) or '<tr><td colspan="5">暂无版本</td></tr>'
    version=current['version'] if current else '未发布'; developer=t['developer_name'] or '未绑定开发者'; fx=coin_core.coin_price(t,coin_core.FEIXIA); yx=coin_core.coin_price(t,coin_core.YOUXIA)
    category_choices=TOOL_CATEGORIES if t['category'] in TOOL_CATEGORIES else [t['category']]+TOOL_CATEGORIES
    category_opts=''.join(f'<option value="{esc(c)}" {"selected" if c==t["category"] else ""}>{esc(c)}</option>' for c in category_choices)
    body=f'''<div class="admin-shell"><a class="backlink" href="/manage/tools/">← 返回工具管理</a><div class="admin-head"><div><h1>{esc(t['name'])}</h1><div class="admin-sub">v{esc(version)} · {int(t['downloads']):,} 次下载</div></div><a class="btn secondary" href="/tools/{esc(t['slug'])}" target="_blank">查看前台</a></div><div class="split"><div class="admin-card"><h2>产品资料</h2><form action="/manage/tools/{esc(t['slug'])}/update" method="post"><div class="field"><label>工具名称</label><input name="name" value="{esc(t['name'])}" required></div><div class="field"><label>一句话介绍</label><input name="tagline" value="{esc(t['tagline'])}"></div><div class="field"><label>分类</label><select name="category">{category_opts}</select></div><div class="field"><label>平台</label><input name="platform" value="{esc(t['platform'])}"></div><div class="field"><label>图标文字</label><input name="icon_text" value="{esc(t['icon_text'])}"></div><div class="field"><label>院内价格 · 小飞侠支付的飞侠币（0 = 院内免费）</label><input name="feixia_coin_price" type="number" min="0" max="{coin_core.MAX_PRICE}" step="1" value="{fx}"></div><div class="field"><label>院外价格 · 小游侠支付的游侠币（0 = 不可下载）</label><input name="youxia_coin_price" type="number" min="0" max="{coin_core.MAX_PRICE}" step="1" value="{yx}"></div><div class="field"><label>上架状态</label><select name="active"><option value="1" {'selected' if t['active'] else ''}>上架</option><option value="0" {'selected' if not t['active'] else ''}>下架</option></select></div><div class="field"><label>完整介绍</label><textarea name="description">{esc(t['description'])}</textarea></div><div class="field"><label>截图 URL</label><textarea name="screenshots">{esc(t['screenshots'])}</textarea></div><button class="btn">保存</button></form></div><div class="admin-card"><h2>归属</h2><div class="owner-row"><b>{esc(developer)}</b><span>原开发者</span></div><div class="owner-row"><b>v{esc(version)}</b><span>当前版本</span></div><div class="owner-row"><b>{fx} 飞侠币</b><span>院内价格</span></div><div class="owner-row"><b>{yx} 游侠币</b><span>院外价格</span></div><p class="muted">新版本由原开发者在个人中心提交，管理员在投稿审核中通过。</p></div></div><div style="height:16px"></div><div class="admin-card"><h2>版本历史</h2><table class="table"><thead><tr><th>版本</th><th>状态</th><th>日期</th><th>大小</th><th>说明</th></tr></thead><tbody>{rows}</tbody></table></div></div>'''
    return HTMLResponse(admin_page(body,f'{t["name"]} · 工具管理'))


@app.post('/login')
async def login(request: Request):
    if not ADMIN_PASSWORD:
        raise HTTPException(503,"后台账号未配置。")
    data=await request.json()
    username=str(data.get('username','')).strip()
    password=str(data.get('password',''))
    if not hmac.compare_digest(username,ADMIN_USERNAME) or not hmac.compare_digest(password,ADMIN_PASSWORD):
        raise HTTPException(401,"管理员用户名或密码不正确。")
    resp=JSONResponse({'success':True}); resp.set_cookie(COOKIE_NAME,session_token(),httponly=True,secure=True,samesite='strict',max_age=8*3600); return resp


@app.post('/logout')
def logout():
    resp=JSONResponse({'success':True}); resp.delete_cookie(COOKIE_NAME); return resp


@app.post('/tools/{slug}/update')
def update_tool(request: Request, slug: str, name: str=Form(...), tagline: str=Form(''), description: str=Form(''), category: str=Form(DEFAULT_TOOL_CATEGORY), platform: str=Form('Windows'), icon_text: str=Form('100'), screenshots: str=Form(''), feixia_coin_price: int=Form(0), youxia_coin_price: int=Form(0), active: int=Form(1)):
    require_admin(request)
    if active not in (0,1): raise HTTPException(400,"参数不正确。")
    for value in (feixia_coin_price, youxia_coin_price):
        if value<0 or value>coin_core.MAX_PRICE: raise HTTPException(400,f"币值价格需在 0—{coin_core.MAX_PRICE} 之间。")
    with db() as conn:
        t=conn.execute("SELECT id FROM tools WHERE slug=?",(slug,)).fetchone()
        if not t: raise HTTPException(404,"工具不存在。")
        conn.execute("UPDATE tools SET name=?,tagline=?,description=?,category=?,platform=?,icon_text=?,screenshots=?,feixia_coin_price=?,youxia_coin_price=?,active=?,updated_at=? WHERE id=?",(name.strip(),tagline.strip(),description.strip(),category.strip(),platform.strip(),icon_text.strip(),screenshots.strip(),feixia_coin_price,youxia_coin_price,active,now_text(),t['id']))
    return RedirectResponse(f'/manage/tools/{slug}',303)
