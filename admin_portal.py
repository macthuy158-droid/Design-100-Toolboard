import hmac

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app_v2 import (
    ADMIN_PASSWORD,
    COOKIE_NAME,
    db,
    esc,
    format_bytes,
    init_db,
    latest_release,
    now_text,
    page,
    session_token,
    valid_session,
)

app = FastAPI(title="Design 100 Admin", docs_url=None, redoc_url=None, openapi_url=None)

ADMIN_CSS = r'''
<style>
.admin-shell{max-width:1180px;margin:auto;padding:34px 22px 70px}
.admin-head{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:26px}
.admin-head h1{margin:7px 0 0;font-size:30px;letter-spacing:-.035em}
.admin-sub{font-size:12px;color:#85878b;margin-top:7px;line-height:1.7}
.admin-tools{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-bottom:24px}
.admin-tool{background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:22px}
.admin-tool-head{display:flex;gap:16px;align-items:center}
.admin-icon{width:58px;height:58px;border-radius:17px;background:#111;color:#fff;display:grid;place-items:center;font-size:12px;font-weight:850;flex:none}
.admin-tool h2{margin:0 0 5px;font-size:22px}
.admin-meta{font-size:11px;color:#888;line-height:1.65}
.admin-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:18px 0}
.admin-stat{background:#f5f5f2;border-radius:13px;padding:12px;min-width:0}
.admin-stat b{display:block;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.admin-stat span{font-size:9px;color:#96989d}
.admin-actions{display:flex;gap:8px;flex-wrap:wrap}
.section-label{margin:28px 0 12px;font-size:13px;color:#76787d;font-weight:720}
.admin-card{background:#fff;border:1px solid #e6e6e3;border-radius:20px;padding:21px}
.admin-card h2{margin:0 0 18px;font-size:19px}
.split{display:grid;grid-template-columns:1.2fr .8fr;gap:16px}
.badge{display:inline-flex;align-items:center;min-height:24px;border-radius:999px;padding:0 9px;background:#f0f0ed;font-size:9px;color:#666}
.badge.current{background:#111;color:#fff}
.badge.off{background:#f3e2e2;color:#8f2929}
.admin-table{width:100%;border-collapse:collapse}
.admin-table th,.admin-table td{text-align:left;border-bottom:1px solid #eee;padding:11px 8px;font-size:11px;vertical-align:middle}
.admin-table th{color:#888;font-weight:650}
.muted{color:#92949a;font-size:11px;line-height:1.7}
.backlink{display:inline-flex;font-size:11px;color:#777;margin-bottom:14px}
.login-note{font-size:11px;color:#999;line-height:1.7;margin-top:14px}
.owner-card{display:grid;gap:12px}
.owner-row{background:#f5f5f2;border-radius:14px;padding:14px}
.owner-row b{display:block;font-size:13px;margin-bottom:3px}
.owner-row span{font-size:10px;color:#8d8f94}
@media(max-width:850px){.admin-tools,.split{grid-template-columns:1fr}.admin-head{align-items:flex-start;flex-direction:column}.admin-stats{grid-template-columns:1fr 1fr}}
</style>
'''


def admin_page(body, title="工具开发板管理"):
    return page(ADMIN_CSS + body, title)


def require_admin(request: Request):
    if not valid_session(request):
        raise HTTPException(status_code=401, detail="请先登录后台。")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    init_db()
    if not valid_session(request):
        login = '''<div class="loginwrap"><div class="login"><div class="eyebrow">DESIGN 100</div><h1>管理后台</h1>
        <form id="f"><div class="field"><label>管理密码</label><input id="p" type="password" autofocus></div>
        <button class="btn" type="submit">进入后台</button><div id="m" class="msg"></div></form>
        <div class="login-note">管理员负责用户、投稿审核、订单与产品状态管理。工具上传和版本更新由小飞侠开发者提交。</div></div></div>
        <script>document.getElementById("f").addEventListener("submit",async e=>{e.preventDefault();const r=await fetch("/manage/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:document.getElementById("p").value})});const j=await r.json().catch(()=>({}));if(r.ok)location.href="/manage/";else document.getElementById("m").textContent=j.detail||"登录失败"})</script>'''
        return HTMLResponse(admin_page(login))

    with db() as conn:
        tools = conn.execute("SELECT * FROM tools ORDER BY downloads DESC,id DESC").fetchall()
        cards = []
        for t in tools:
            current = latest_release(conn, t["id"])
            version = current["version"] if current else "未发布"
            developer = t["developer_name"] or "未绑定"
            price = int(t["price_cents"] or 0) / 100
            status = "已上架" if t["active"] else "已下架"
            status_badge = '<span class="badge current">已上架</span>' if t["active"] else '<span class="badge off">已下架</span>'
            cards.append(f'''<div class="admin-tool"><div class="admin-tool-head"><div class="admin-icon">{esc(t["icon_text"])}</div>
            <div><h2>{esc(t["name"])}</h2><div class="admin-meta">{esc(t["category"])} · {esc(t["platform"])} · /{esc(t["slug"])} · {status_badge}</div></div></div>
            <div class="admin-stats"><div class="admin-stat"><b>v{esc(version)}</b><span>当前版本</span></div><div class="admin-stat"><b>¥{price:.2f}</b><span>小游侠价格</span></div><div class="admin-stat"><b>{esc(developer)}</b><span>开发者</span></div><div class="admin-stat"><b>{int(t["downloads"]):,}</b><span>累计下载</span></div></div>
            <div class="admin-actions"><a class="btn" href="/manage/tools/{esc(t["slug"])}">管理资料</a><a class="btn secondary" href="/tools/{esc(t["slug"])}" target="_blank">查看前台</a></div></div>''')

    body = f'''<div class="admin-shell"><div class="admin-head"><div><div class="eyebrow">DESIGN 100 · ADMIN</div><h1>工具总览</h1>
    <div class="admin-sub">管理员只维护产品资料、价格和上下架状态。新工具与版本更新由小飞侠在个人中心提交，再进入审核流程。</div></div>
    <div class="admin-actions"><a class="btn" href="/manage/community/">用户 / 投稿 / 订单</a><button class="btn secondary" onclick="fetch('/manage/logout',{{method:'POST'}}).then(()=>location.href='/manage/')">退出</button></div></div>
    <div class="admin-tools">{''.join(cards) if cards else '<div class="admin-card muted">暂无工具。请由小飞侠提交新工具并审核通过后发布。</div>'}</div></div>'''
    return HTMLResponse(admin_page(body))


@app.get("/tools/{slug}", response_class=HTMLResponse)
def tool_admin(request: Request, slug: str):
    require_admin(request)
    with db() as conn:
        t = conn.execute("SELECT * FROM tools WHERE slug=?", (slug,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="工具不存在。")
        releases = conn.execute("SELECT * FROM releases WHERE tool_id=? ORDER BY id DESC", (t["id"],)).fetchall()
        current = latest_release(conn, t["id"])

    rows = []
    for r in releases:
        status = '<span class="badge current">当前版本</span>' if r["active"] else '<span class="badge">历史版本</span>'
        rows.append(
            f'<tr><td><b>v{esc(r["version"])}</b><br>{status}</td>'
            f'<td>{esc(r["published_at"][:10])}</td>'
            f'<td>{esc(format_bytes(r["size"]))}</td>'
            f'<td>{esc(r["package_name"])}</td>'
            f'<td>{esc(r["notes"] or "—")}</td></tr>'
        )

    current_version = current["version"] if current else "未发布"
    developer = t["developer_name"] or "未绑定开发者"
    price = int(t["price_cents"] or 0) / 100
    active_value = 1 if t["active"] else 0
    body = f'''<div class="admin-shell"><div class="admin-head"><div><a class="backlink" href="/manage/">← 返回工具总览</a><div class="eyebrow">DESIGN 100 · PRODUCT ADMIN</div>
    <h1>{esc(t["name"])}</h1><div class="admin-sub">当前版本 v{esc(current_version)} · 累计下载 {int(t["downloads"]):,} · slug: {esc(t["slug"])}</div></div>
    <a class="btn secondary" href="/tools/{esc(t["slug"])}" target="_blank">查看前台</a></div>
    <div class="split"><div class="admin-card"><h2>产品资料</h2><form action="/manage/tools/{esc(t["slug"])}/update" method="post">
    <div class="field"><label>工具名称</label><input name="name" value="{esc(t["name"])}" required></div>
    <div class="field"><label>一句话介绍</label><input name="tagline" value="{esc(t["tagline"])}"></div>
    <div class="field"><label>分类</label><input name="category" value="{esc(t["category"])}"></div>
    <div class="field"><label>平台</label><input name="platform" value="{esc(t["platform"])}"></div>
    <div class="field"><label>图标文字</label><input name="icon_text" value="{esc(t["icon_text"])}"></div>
    <div class="field"><label>小游侠价格（元）</label><input name="price_yuan" type="number" min="0" step="0.01" value="{price:.2f}"></div>
    <div class="field"><label>上架状态</label><select name="active"><option value="1" {'selected' if active_value == 1 else ''}>上架</option><option value="0" {'selected' if active_value == 0 else ''}>下架</option></select></div>
    <div class="field"><label>完整介绍</label><textarea name="description">{esc(t["description"])}</textarea></div>
    <div class="field"><label>截图 URL（每行一张）</label><textarea name="screenshots">{esc(t["screenshots"])}</textarea></div>
    <button class="btn">保存资料</button></form></div>
    <div class="admin-card"><h2>产品归属</h2><div class="owner-card">
      <div class="owner-row"><b>{esc(developer)}</b><span>原开发者 / 版本更新权限所有者</span></div>
      <div class="owner-row"><b>v{esc(current_version)}</b><span>当前审核通过版本</span></div>
      <div class="owner-row"><b>¥{price:.2f}</b><span>当前小游侠售价</span></div>
    </div><p class="muted" style="margin-top:18px">版本上传、更新和发布不在管理员工具页操作。原开发者从小飞侠个人中心提交新版本，管理员在“用户 / 投稿 / 订单”中审核。</p></div></div>
    <div class="section-label">版本历史 · 只读</div><div class="admin-card"><table class="admin-table"><thead><tr><th>版本</th><th>发布日期</th><th>大小</th><th>文件</th><th>更新说明</th></tr></thead>
    <tbody>{''.join(rows) if rows else '<tr><td colspan="5" class="muted">暂未发布任何版本。</td></tr>'}</tbody></table></div></div>'''
    return HTMLResponse(admin_page(body, f'{t["name"]} · 工具管理'))


@app.post("/login")
async def login(request: Request):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="后台密码未配置。")
    data = await request.json()
    if not hmac.compare_digest(str(data.get("password", "")), ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="密码不正确。")
    resp = JSONResponse({"success": True})
    resp.set_cookie(COOKIE_NAME, session_token(), httponly=True, secure=True, samesite="strict", max_age=8 * 3600)
    return resp


@app.post("/logout")
def logout():
    resp = JSONResponse({"success": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.post("/tools/{slug}/update")
def update_tool(
    request: Request,
    slug: str,
    name: str = Form(...),
    tagline: str = Form(""),
    description: str = Form(""),
    category: str = Form("效率工具"),
    platform: str = Form("Windows"),
    icon_text: str = Form("100"),
    screenshots: str = Form(""),
    price_yuan: float = Form(0),
    active: int = Form(1),
):
    require_admin(request)
    if price_yuan < 0:
        raise HTTPException(status_code=400, detail="价格不能小于 0。")
    if active not in (0, 1):
        raise HTTPException(status_code=400, detail="上架状态不正确。")
    with db() as conn:
        t = conn.execute("SELECT id FROM tools WHERE slug=?", (slug,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="工具不存在。")
        conn.execute(
            "UPDATE tools SET name=?,tagline=?,description=?,category=?,platform=?,icon_text=?,screenshots=?,price_cents=?,active=?,updated_at=? WHERE id=?",
            (
                name.strip(),
                tagline.strip(),
                description.strip(),
                category.strip(),
                platform.strip(),
                icon_text.strip(),
                screenshots.strip(),
                int(round(price_yuan * 100)),
                active,
                now_text(),
                t["id"],
            ),
        )
    return RedirectResponse(f"/manage/tools/{slug}", status_code=303)
