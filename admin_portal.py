import hashlib
import sqlite3
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app_v2 import (
    ADMIN_PASSWORD,
    COOKIE_NAME,
    PACKAGE_DIR,
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
.admin-shell{max-width:1180px;margin:auto;padding:34px 22px 70px}.admin-head{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:26px}.admin-head h1{margin:7px 0 0;font-size:30px;letter-spacing:-.035em}.admin-sub{font-size:12px;color:#85878b;margin-top:7px}.admin-tools{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-bottom:24px}.admin-tool{background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:22px}.admin-tool-head{display:flex;gap:16px;align-items:center}.admin-icon{width:58px;height:58px;border-radius:17px;background:#111;color:#fff;display:grid;place-items:center;font-size:12px;font-weight:850;flex:none}.admin-tool h2{margin:0 0 5px;font-size:22px}.admin-meta{font-size:11px;color:#888}.admin-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:18px 0}.admin-stat{background:#f5f5f2;border-radius:13px;padding:12px}.admin-stat b{display:block;font-size:14px}.admin-stat span{font-size:9px;color:#96989d}.admin-actions{display:flex;gap:8px;flex-wrap:wrap}.section-label{margin:28px 0 12px;font-size:13px;color:#76787d;font-weight:720}.admin-card{background:#fff;border:1px solid #e6e6e3;border-radius:20px;padding:21px}.admin-card h2{margin:0 0 18px;font-size:19px}.split{display:grid;grid-template-columns:1fr 1fr;gap:16px}.badge{display:inline-flex;align-items:center;min-height:24px;border-radius:999px;padding:0 9px;background:#f0f0ed;font-size:9px;color:#666}.badge.current{background:#111;color:#fff}.mini{min-height:34px!important;padding:0 12px!important;font-size:10px!important}.danger{background:#fff!important;color:#a62626!important;border:1px solid #edcece!important}.admin-table{width:100%;border-collapse:collapse}.admin-table th,.admin-table td{text-align:left;border-bottom:1px solid #eee;padding:11px 8px;font-size:11px;vertical-align:middle}.admin-table th{color:#888;font-weight:650}.admin-table form{display:inline}.muted{color:#92949a;font-size:11px}.backlink{display:inline-flex;font-size:11px;color:#777;margin-bottom:14px}.login-note{font-size:11px;color:#999;line-height:1.7;margin-top:14px}@media(max-width:850px){.admin-tools,.split{grid-template-columns:1fr}.admin-head{align-items:flex-start;flex-direction:column}}
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
        login = '''<div class="loginwrap"><div class="login"><div class="eyebrow">DESIGN 100</div><h1>工具开发板管理</h1>
        <form id="f"><div class="field"><label>管理密码</label><input id="p" type="password" autofocus></div>
        <button class="btn" type="submit">进入后台</button><div id="m" class="msg"></div></form>
        <div class="login-note">登录后先选择具体工具，再管理该工具的资料、安装包和版本历史。</div></div></div>
        <script>document.getElementById("f").addEventListener("submit",async e=>{e.preventDefault();const r=await fetch("/manage/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:document.getElementById("p").value})});const j=await r.json().catch(()=>({}));if(r.ok)location.href="/manage/";else document.getElementById("m").textContent=j.detail||"登录失败"})</script>'''
        return HTMLResponse(admin_page(login))

    with db() as conn:
        tools = conn.execute("SELECT * FROM tools ORDER BY downloads DESC,id DESC").fetchall()
        cards = []
        for t in tools:
            current = latest_release(conn, t["id"])
            version = current["version"] if current else "未发布"
            release_count = conn.execute("SELECT COUNT(*) c FROM releases WHERE tool_id=?", (t["id"],)).fetchone()["c"]
            cards.append(f'''<div class="admin-tool"><div class="admin-tool-head"><div class="admin-icon">{esc(t["icon_text"])}</div>
            <div><h2>{esc(t["name"])}</h2><div class="admin-meta">{esc(t["category"])} · {esc(t["platform"])} · /{esc(t["slug"])}</div></div></div>
            <div class="admin-stats"><div class="admin-stat"><b>v{esc(version)}</b><span>当前版本</span></div><div class="admin-stat"><b>{int(release_count)}</b><span>历史版本</span></div><div class="admin-stat"><b>{int(t["downloads"]):,}</b><span>累计下载</span></div></div>
            <div class="admin-actions"><a class="btn" href="/manage/tools/{esc(t["slug"])}">管理工具</a><a class="btn secondary" href="/tools/{esc(t["slug"])}" target="_blank">查看前台</a></div></div>''')

    body = f'''<div class="admin-shell"><div class="admin-head"><div><div class="eyebrow">DESIGN 100 · ADMIN</div><h1>工具管理</h1>
    <div class="admin-sub">CAD-100、文本100% 等工具分别管理。选择工具后上传对应版本，不再手工填写 slug。</div></div>
    <button class="btn secondary" onclick="fetch('/manage/logout',{{method:'POST'}}).then(()=>location.href='/manage/')">退出</button></div>
    <div class="admin-tools">{''.join(cards)}</div><div class="section-label">新增工具</div>
    <div class="admin-card"><form action="/manage/tools/create" method="post"><div class="split"><div>
    <div class="field"><label>工具名称</label><input name="name" required></div><div class="field"><label>URL 标识（slug）</label><input name="slug" placeholder="例如 text-100" required></div>
    <div class="field"><label>一句话介绍</label><input name="tagline"></div><div class="field"><label>分类</label><input name="category" value="效率工具"></div></div><div>
    <div class="field"><label>平台</label><input name="platform" value="Windows"></div><div class="field"><label>图标文字</label><input name="icon_text" value="100"></div><div class="field"><label>完整介绍</label><textarea name="description"></textarea></div></div></div>
    <button class="btn">新增工具</button></form></div></div>'''
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
        actions = ""
        if not r["active"]:
            actions += f'<form action="/manage/releases/{r["id"]}/activate" method="post"><button class="btn secondary mini" type="submit">设为当前</button></form> '
        actions += f'<form action="/manage/releases/{r["id"]}/delete" method="post" onsubmit="return confirm(\'确定删除这个版本吗？\')"><button class="btn danger mini" type="submit">删除</button></form>'
        rows.append(f'<tr><td><b>v{esc(r["version"])}</b><br>{status}</td><td>{esc(r["published_at"][:10])}</td><td>{esc(format_bytes(r["size"]))}</td><td>{esc(r["package_name"])}</td><td>{actions}</td></tr>')

    current_version = current["version"] if current else "未发布"
    body = f'''<div class="admin-shell"><div class="admin-head"><div><a class="backlink" href="/manage/">← 返回工具管理</a><div class="eyebrow">DESIGN 100 · TOOL ADMIN</div>
    <h1>{esc(t["name"])}</h1><div class="admin-sub">当前版本 v{esc(current_version)} · 累计下载 {int(t["downloads"]):,} · slug: {esc(t["slug"])}</div></div>
    <a class="btn secondary" href="/tools/{esc(t["slug"])}" target="_blank">查看前台</a></div>
    <div class="split"><div class="admin-card"><h2>工具资料</h2><form action="/manage/tools/{esc(t["slug"])}/update" method="post">
    <div class="field"><label>工具名称</label><input name="name" value="{esc(t["name"])}" required></div><div class="field"><label>一句话介绍</label><input name="tagline" value="{esc(t["tagline"])}"></div>
    <div class="field"><label>分类</label><input name="category" value="{esc(t["category"])}"></div><div class="field"><label>平台</label><input name="platform" value="{esc(t["platform"])}"></div>
    <div class="field"><label>图标文字</label><input name="icon_text" value="{esc(t["icon_text"])}"></div><div class="field"><label>完整介绍</label><textarea name="description">{esc(t["description"])}</textarea></div>
    <div class="field"><label>截图 URL（每行一张，可暂不填）</label><textarea name="screenshots">{esc(t["screenshots"])}</textarea></div><button class="btn">保存资料</button></form></div>
    <div class="admin-card"><h2>发布新版本</h2><div class="muted" style="margin-bottom:16px">这里上传的安装包只属于 <b>{esc(t["name"])}</b>。新版本发布后自动成为当前下载版本。</div>
    <form action="/manage/releases/create" method="post" enctype="multipart/form-data"><input type="hidden" name="slug" value="{esc(t["slug"])}">
    <div class="field"><label>版本号</label><input name="version" placeholder="例如 1.0.1" required></div><div class="field"><label>更新说明</label><textarea name="notes" placeholder="本次更新了什么"></textarea></div>
    <div class="field"><label>安装包</label><input name="package" type="file" required></div><button class="btn">上传并发布</button></form></div></div>
    <div class="section-label">版本历史</div><div class="admin-card"><table class="admin-table"><thead><tr><th>版本</th><th>发布日期</th><th>大小</th><th>文件</th><th>操作</th></tr></thead>
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


@app.post("/tools/create")
def create_tool(request: Request, name: str = Form(...), slug: str = Form(...), tagline: str = Form(""), description: str = Form(""), category: str = Form("效率工具"), platform: str = Form("Windows"), icon_text: str = Form("100")):
    require_admin(request)
    clean_slug = slug.strip().lower()
    now = now_text()
    try:
        with db() as conn:
            conn.execute("INSERT INTO tools(slug,name,tagline,description,category,platform,icon_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (clean_slug, name.strip(), tagline.strip(), description.strip(), category.strip(), platform.strip(), icon_text.strip(), now, now))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="slug 已存在。")
    return RedirectResponse("/manage/", status_code=303)


@app.post("/tools/{slug}/update")
def update_tool(request: Request, slug: str, name: str = Form(...), tagline: str = Form(""), description: str = Form(""), category: str = Form("效率工具"), platform: str = Form("Windows"), icon_text: str = Form("100"), screenshots: str = Form("")):
    require_admin(request)
    with db() as conn:
        t = conn.execute("SELECT id FROM tools WHERE slug=?", (slug,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="工具不存在。")
        conn.execute("UPDATE tools SET name=?,tagline=?,description=?,category=?,platform=?,icon_text=?,screenshots=?,updated_at=? WHERE id=?", (name.strip(), tagline.strip(), description.strip(), category.strip(), platform.strip(), icon_text.strip(), screenshots.strip(), now_text(), t["id"]))
    return RedirectResponse(f"/manage/tools/{slug}", status_code=303)


@app.post("/releases/create")
async def create_release(request: Request, slug: str = Form(...), version: str = Form(...), notes: str = Form(""), package: UploadFile = File(...)):
    require_admin(request)
    content = await package.read()
    if not content:
        raise HTTPException(status_code=400, detail="安装包不能为空。")
    clean_slug = slug.strip()
    with db() as conn:
        t = conn.execute("SELECT * FROM tools WHERE slug=?", (clean_slug,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="工具不存在。")
        safe_name = (package.filename or f"{clean_slug}-{version}.zip").replace("/", "_").replace("\\", "_")
        tool_dir = PACKAGE_DIR / clean_slug
        tool_dir.mkdir(parents=True, exist_ok=True)
        path = tool_dir / safe_name
        path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        conn.execute("UPDATE releases SET active=0 WHERE tool_id=?", (t["id"],))
        conn.execute("INSERT INTO releases(tool_id,version,notes,package_name,package_path,sha256,size,published_at,active) VALUES(?,?,?,?,?,?,?,?,1)", (t["id"], version.strip(), notes.strip(), safe_name, str(path), digest, len(content), now_text()))
    return RedirectResponse(f"/manage/tools/{clean_slug}", status_code=303)


@app.post("/releases/{release_id}/activate")
def activate_release(request: Request, release_id: int):
    require_admin(request)
    with db() as conn:
        rel = conn.execute("SELECT r.*,t.slug FROM releases r JOIN tools t ON t.id=r.tool_id WHERE r.id=?", (release_id,)).fetchone()
        if not rel:
            raise HTTPException(status_code=404, detail="版本不存在。")
        conn.execute("UPDATE releases SET active=0 WHERE tool_id=?", (rel["tool_id"],))
        conn.execute("UPDATE releases SET active=1 WHERE id=?", (release_id,))
        slug = rel["slug"]
    return RedirectResponse(f"/manage/tools/{slug}", status_code=303)


@app.post("/releases/{release_id}/delete")
def delete_release(request: Request, release_id: int):
    require_admin(request)
    with db() as conn:
        rel = conn.execute("SELECT r.*,t.slug FROM releases r JOIN tools t ON t.id=r.tool_id WHERE r.id=?", (release_id,)).fetchone()
        if not rel:
            raise HTTPException(status_code=404, detail="版本不存在。")
        tool_id = rel["tool_id"]
        was_active = bool(rel["active"])
        slug = rel["slug"]
        package_path = Path(rel["package_path"])
        conn.execute("DELETE FROM releases WHERE id=?", (release_id,))
        if was_active:
            fallback = conn.execute("SELECT id FROM releases WHERE tool_id=? ORDER BY id DESC LIMIT 1", (tool_id,)).fetchone()
            if fallback:
                conn.execute("UPDATE releases SET active=1 WHERE id=?", (fallback["id"],))
    try:
        resolved = package_path.resolve()
        root = PACKAGE_DIR.resolve()
        if root in resolved.parents and resolved.exists():
            resolved.unlink()
    except Exception:
        pass
    return RedirectResponse(f"/manage/tools/{slug}", status_code=303)
