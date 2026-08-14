import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("TOOLBOARD_DATA_DIR", str(APP_ROOT / "data")))
DB_PATH = DATA_DIR / "toolboard.db"
PACKAGE_DIR = DATA_DIR / "packages"
ADMIN_PASSWORD = os.getenv("TOOLBOARD_ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("TOOLBOARD_SESSION_SECRET", "") or secrets.token_hex(32)
COOKIE_NAME = "design100_admin"

app = FastAPI(title="深圳院设计100% 工具开发板", version="1.0")


def now_text():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL,
            tagline TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '效率工具',
            platform TEXT NOT NULL DEFAULT 'Windows',
            icon_text TEXT NOT NULL DEFAULT '100',
            screenshots TEXT NOT NULL DEFAULT '',
            downloads INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            package_name TEXT NOT NULL,
            package_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            published_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_tools_rank ON tools(active, downloads DESC, id ASC);
        CREATE INDEX IF NOT EXISTS idx_releases_tool ON releases(tool_id, active, id DESC);
        """)
        exists = conn.execute("SELECT id FROM tools WHERE slug='cad-100'").fetchone()
        if not exists:
            now = now_text()
            conn.execute("""INSERT INTO tools
                (slug,name,tagline,description,category,platform,icon_text,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", (
                "cad-100", "CAD-100", "面向设计生产流程的 CAD 批量效率工具",
                "围绕日常 CAD 图纸处理流程，将重复操作自动化，降低批量处理工作量。设计文件在本机完成处理，不上传图纸内容。",
                "CAD / 设计效率", "Windows", "CAD", now, now
            ))


@app.on_event("startup")
def startup():
    init_db()


def latest_release(conn, tool_id):
    return conn.execute(
        "SELECT * FROM releases WHERE tool_id=? AND active=1 ORDER BY id DESC LIMIT 1",
        (tool_id,),
    ).fetchone()


def session_token():
    stamp = str(int(datetime.now(timezone.utc).timestamp()) + 8 * 3600)
    sig = hmac.new(SESSION_SECRET.encode(), stamp.encode(), hashlib.sha256).hexdigest()
    return stamp + "." + sig


def valid_session(request: Request):
    value = request.cookies.get(COOKIE_NAME, "")
    try:
        stamp, sig = value.split(".", 1)
        if int(stamp) < int(datetime.now(timezone.utc).timestamp()):
            return False
        expected = hmac.new(SESSION_SECRET.encode(), stamp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def require_admin(request: Request):
    if not valid_session(request):
        raise HTTPException(status_code=401, detail="请先登录后台。")


CSS = r'''
:root{--bg:#f5f5f7;--card:#fff;--ink:#111216;--muted:#777980;--line:#e5e5e8;--soft:#f1f1f3}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}a{text-decoration:none;color:inherit}.shell{max-width:1220px;margin:auto;padding:0 26px}.nav{height:72px;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;gap:12px;align-items:center;font-weight:750}.mark{width:36px;height:36px;border-radius:10px;background:#111;color:#fff;display:grid;place-items:center;font-size:10px;font-weight:800}.brand small{display:block;font-size:10px;color:#888;letter-spacing:.08em;margin-top:2px}.hero{padding:76px 0 58px}.eyebrow{font-size:12px;font-weight:700;letter-spacing:.14em;color:#777}.hero h1{font-size:clamp(44px,7vw,84px);line-height:1.02;letter-spacing:-.05em;margin:14px 0 22px}.hero p{font-size:18px;line-height:1.75;color:#6f7076;max-width:780px}.summary{display:flex;gap:34px;margin-top:30px}.summary b{font-size:26px;display:block}.summary span{font-size:11px;color:#999}.sectionhead{display:flex;justify-content:space-between;align-items:end;margin:30px 0 16px}.sectionhead h2{margin:0;font-size:25px}.sectionhead span{font-size:12px;color:#888}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding-bottom:80px}.tool{background:#fff;border:1px solid var(--line);border-radius:24px;padding:22px;min-height:286px;display:flex;flex-direction:column;transition:.18s}.tool:hover{transform:translateY(-3px);box-shadow:0 18px 45px rgba(0,0,0,.07)}.rank{font-size:11px;color:#999;font-weight:700;letter-spacing:.08em}.icon{width:58px;height:58px;border-radius:17px;background:#111;color:#fff;display:grid;place-items:center;font-size:13px;font-weight:800;margin:20px 0}.tool h3{font-size:23px;margin:0 0 8px}.tagline{font-size:13px;line-height:1.65;color:#777}.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}.chip{background:var(--soft);border-radius:999px;padding:6px 9px;font-size:10px;color:#666}.footrow{display:flex;justify-content:space-between;align-items:end;margin-top:auto;padding-top:22px;border-top:1px solid #f0f0f1}.downloads b{font-size:18px}.downloads span{font-size:10px;color:#999;display:block}.arrow{width:34px;height:34px;border-radius:50%;background:#111;color:#fff;display:grid;place-items:center}.footer{border-top:1px solid #dddde1;padding:28px 0 44px;font-size:11px;color:#999;display:flex;justify-content:space-between}.detail{padding:70px 0 45px;display:grid;grid-template-columns:1fr 320px;gap:60px;align-items:center}.bigicon{width:240px;height:240px;border-radius:56px;background:#111;color:#fff;display:grid;place-items:center;font-size:44px;font-weight:800}.detail h1{font-size:60px;letter-spacing:-.05em;margin:12px 0}.lead{font-size:19px;line-height:1.65;color:#707178}.facts{display:flex;gap:26px;margin:26px 0}.fact b{display:block;font-size:17px}.fact span{font-size:10px;color:#999}.btn{display:inline-flex;align-items:center;justify-content:center;height:46px;padding:0 22px;border-radius:11px;background:#111;color:#fff;border:0;font-weight:700;cursor:pointer}.btn.secondary{background:#fff;color:#111;border:1px solid #d6d6da}.content{display:grid;grid-template-columns:1.3fr .7fr;gap:18px;padding-bottom:80px}.panel{background:#fff;border:1px solid var(--line);border-radius:24px;padding:26px}.panel h2{margin:0 0 14px;font-size:20px}.panel p{font-size:14px;line-height:1.9;color:#62636a;white-space:pre-line}.loginwrap{min-height:100vh;display:grid;place-items:center;padding:24px}.login{width:min(420px,100%);background:#fff;border:1px solid var(--line);border-radius:24px;padding:32px}.login h1{margin:8px 0 20px}.field{margin-bottom:12px}.field label{display:block;font-size:12px;color:#777;margin-bottom:6px}.field input,.field textarea{width:100%;border:1px solid #d7d7db;border-radius:10px;padding:0 11px;font:inherit}.field input{height:42px}.field textarea{height:100px;padding-top:10px}.admin{max-width:1180px;margin:auto;padding:32px 22px 70px}.adminhead{display:flex;justify-content:space-between;align-items:end;margin-bottom:24px}.cards{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:20px}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;border-bottom:1px solid #eee;padding:10px 8px;font-size:12px}.msg{font-size:12px;min-height:18px;margin-top:8px}.ok{color:#287a37}.bad{color:#b42318}@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.detail,.content{grid-template-columns:1fr}.cards{grid-template-columns:1fr}}@media(max-width:600px){.grid{grid-template-columns:1fr}.shell{padding:0 16px}.detail h1{font-size:44px}.footer{flex-direction:column;gap:8px}}
'''


def page(body, title="深圳院设计100% · 工具开发板"):
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>'


@app.get("/", response_class=HTMLResponse)
def home():
    init_db()
    with db() as conn:
        tools = conn.execute("SELECT * FROM tools WHERE active=1 ORDER BY downloads DESC,id ASC").fetchall()
        total = sum(int(t["downloads"] or 0) for t in tools)
        cards = []
        for i, t in enumerate(tools, 1):
            rel = latest_release(conn, t["id"])
            version = rel["version"] if rel else "待发布"
            cards.append(f'''<a class="tool" href="/tools/{t['slug']}"><div class="rank">#{i:02d} · DOWNLOAD RANK</div><div class="icon">{t['icon_text']}</div><h3>{t['name']}</h3><div class="tagline">{t['tagline']}</div><div class="chips"><span class="chip">{t['category']}</span><span class="chip">{t['platform']}</span><span class="chip">v{version}</span></div><div class="footrow"><div class="downloads"><b>{int(t['downloads']):,}</b><span>累计下载</span></div><div class="arrow">↗</div></div></a>''')
    body=f'''<div class="shell"><nav class="nav"><a class="brand" href="/"><div class="mark">100%</div><div>深圳院设计100%<small>TOOL DEVELOPMENT BOARD</small></div></a><a href="/manage" style="font-size:12px;color:#888">管理</a></nav><section class="hero"><div class="eyebrow">DESIGN × TECHNOLOGY × PRODUCTIVITY</div><h1>把重复工作，<br>交给工具。</h1><p>深圳院设计100% · 工具开发板，持续发布面向真实设计生产流程的小工具。让设计师把更多时间留给判断、创意和设计本身。</p><div class="summary"><div><b>{len(tools)}</b><span>已发布工具</span></div><div><b>{total:,}</b><span>累计下载</span></div></div></section><div class="sectionhead"><h2>工具排行</h2><span>按累计下载量排序</span></div><main class="grid">{''.join(cards)}</main><footer class="footer"><span>深圳院设计100% · 工具开发板</span><span>Internal Design Tools</span></footer></div>'''
    return HTMLResponse(page(body), headers={"Cache-Control":"no-cache"})


@app.get("/tools/{slug}", response_class=HTMLResponse)
def detail(slug: str):
    with db() as conn:
        t=conn.execute("SELECT * FROM tools WHERE slug=? AND active=1",(slug,)).fetchone()
        if not t: raise HTTPException(status_code=404, detail="工具不存在。")
        rel=latest_release(conn,t["id"])
    version=rel["version"] if rel else "待发布"
    notes=rel["notes"] if rel else "暂无版本说明。"
    download=f'<a class="btn" href="/tools/{slug}/download">下载 v{version}</a>' if rel else '<span class="btn" style="background:#bbb">安装包待发布</span>'
    body=f'''<div class="shell"><nav class="nav"><a class="brand" href="/"><div class="mark">100%</div><div>深圳院设计100%<small>TOOL DEVELOPMENT BOARD</small></div></a></nav><section class="detail"><div><a href="/" style="font-size:12px;color:#777">← 返回工具开发板</a><div class="eyebrow" style="margin-top:28px">{t['category']} · {t['platform']}</div><h1>{t['name']}</h1><div class="lead">{t['tagline']}</div><div class="facts"><div class="fact"><b>v{version}</b><span>当前版本</span></div><div class="fact"><b>{int(t['downloads']):,}</b><span>累计下载</span></div><div class="fact"><b>{t['platform']}</b><span>运行平台</span></div></div>{download}</div><div class="bigicon">{t['icon_text']}</div></section><section class="content"><div class="panel"><h2>工具介绍</h2><p>{t['description']}</p></div><div class="panel"><h2>当前版本</h2><p><b>v{version}</b>\n\n{notes}</p></div></section></div>'''
    return HTMLResponse(page(body, f"{t['name']} · 深圳院设计100%"))


@app.get("/tools/{slug}/download")
def download(slug: str):
    with db() as conn:
        t=conn.execute("SELECT * FROM tools WHERE slug=? AND active=1",(slug,)).fetchone()
        if not t: raise HTTPException(status_code=404,detail="工具不存在。")
        rel=latest_release(conn,t["id"])
        if not rel: raise HTTPException(status_code=404,detail="安装包尚未发布。")
        path=Path(rel["package_path"])
        if not path.exists(): raise HTTPException(status_code=404,detail="安装包文件不存在。")
        conn.execute("UPDATE tools SET downloads=downloads+1,updated_at=? WHERE id=?",(now_text(),t["id"]))
    return FileResponse(path=str(path),filename=rel["package_name"],media_type="application/octet-stream")


@app.get("/manage", response_class=HTMLResponse)
def manage(request: Request):
    if not valid_session(request):
        body='''<div class="loginwrap"><div class="login"><div class="eyebrow">DESIGN 100</div><h1>工具开发板管理</h1><form id="f"><div class="field"><label>管理密码</label><input id="p" type="password" autofocus></div><button class="btn" type="submit">进入后台</button><div id="m" class="msg"></div></form></div></div><script>f.onsubmit=async e=>{e.preventDefault();let r=await fetch('/manage/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p.value})});let j=await r.json().catch(()=>({}));if(r.ok)location.href='/manage';else m.textContent=j.detail||'登录失败';}</script>'''
        return HTMLResponse(page(body,"工具开发板管理"))
    with db() as conn:
        tools=conn.execute("SELECT * FROM tools ORDER BY id DESC").fetchall()
        rows=''.join([f"<tr><td>{t['name']}</td><td>{t['slug']}</td><td>{t['category']}</td><td>{t['downloads']}</td><td><a href='/tools/{t['slug']}'>查看</a></td></tr>" for t in tools])
    body=f'''<div class="admin"><div class="adminhead"><div><div class="eyebrow">DESIGN 100</div><h1 style="margin:6px 0 0">工具开发板管理</h1></div><button class="btn secondary" onclick="fetch('/manage/logout',{{method:'POST'}}).then(()=>location.href='/manage')">退出</button></div><div class="cards"><div class="card"><h2>新增工具</h2><form action="/manage/tools" method="post"><div class="field"><label>工具名称</label><input name="name" required></div><div class="field"><label>URL 标识</label><input name="slug" placeholder="例如 pdf-tool" required></div><div class="field"><label>一句话介绍</label><input name="tagline"></div><div class="field"><label>分类</label><input name="category" value="效率工具"></div><div class="field"><label>平台</label><input name="platform" value="Windows"></div><div class="field"><label>图标文字</label><input name="icon_text" value="100"></div><div class="field"><label>完整介绍</label><textarea name="description"></textarea></div><button class="btn">新增工具</button></form></div><div class="card"><h2>发布版本</h2><form action="/manage/releases" method="post" enctype="multipart/form-data"><div class="field"><label>工具 slug</label><input name="slug" placeholder="cad-100" required></div><div class="field"><label>版本号</label><input name="version" placeholder="2.1.0" required></div><div class="field"><label>更新说明</label><textarea name="notes"></textarea></div><div class="field"><label>安装包</label><input name="package" type="file" required></div><button class="btn">发布版本</button></form></div></div><div class="card" style="margin-top:16px"><h2>已发布工具</h2><table class="table"><thead><tr><th>名称</th><th>Slug</th><th>分类</th><th>下载量</th><th></th></tr></thead><tbody>{rows}</tbody></table></div></div>'''
    return HTMLResponse(page(body,"工具开发板管理"))


@app.post("/manage/login")
async def manage_login(request: Request):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503,detail="后台密码未配置。")
    data=await request.json()
    if not hmac.compare_digest(str(data.get("password","")),ADMIN_PASSWORD):
        raise HTTPException(status_code=401,detail="密码不正确。")
    resp=JSONResponse({"success":True})
    resp.set_cookie(COOKIE_NAME,session_token(),httponly=True,secure=True,samesite="strict",max_age=8*3600)
    return resp


@app.post("/manage/logout")
def manage_logout():
    resp=JSONResponse({"success":True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.post("/manage/tools")
def create_tool(request: Request,name: str=Form(...),slug: str=Form(...),tagline: str=Form(""),description: str=Form(""),category: str=Form("效率工具"),platform: str=Form("Windows"),icon_text: str=Form("100")):
    require_admin(request)
    now=now_text()
    try:
        with db() as conn:
            conn.execute("""INSERT INTO tools(slug,name,tagline,description,category,platform,icon_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",(slug.strip(),name.strip(),tagline.strip(),description.strip(),category.strip(),platform.strip(),icon_text.strip(),now,now))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409,detail="slug 已存在。")
    return RedirectResponse('/manage',status_code=303)


@app.post("/manage/releases")
async def create_release(request: Request,slug: str=Form(...),version: str=Form(...),notes: str=Form(""),package: UploadFile=File(...)):
    require_admin(request)
    content=await package.read()
    if not content: raise HTTPException(status_code=400,detail="安装包不能为空。")
    with db() as conn:
        t=conn.execute("SELECT * FROM tools WHERE slug=?",(slug.strip(),)).fetchone()
        if not t: raise HTTPException(status_code=404,detail="工具不存在。")
        safe_name=(package.filename or f"{slug}-{version}.zip").replace('/','_').replace('\\','_')
        tool_dir=PACKAGE_DIR / slug.strip()
        tool_dir.mkdir(parents=True,exist_ok=True)
        path=tool_dir / safe_name
        path.write_bytes(content)
        digest=hashlib.sha256(content).hexdigest()
        conn.execute("UPDATE releases SET active=0 WHERE tool_id=?",(t['id'],))
        conn.execute("""INSERT INTO releases(tool_id,version,notes,package_name,package_path,sha256,size,published_at,active) VALUES(?,?,?,?,?,?,?,?,1)""",(t['id'],version.strip(),notes.strip(),safe_name,str(path),digest,len(content),now_text()))
    return RedirectResponse('/manage',status_code=303)
