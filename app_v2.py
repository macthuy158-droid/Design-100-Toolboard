import hashlib
import hmac
import html
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

app = FastAPI(title="深圳院设计100% 工具开发板", version="1.1")


def now_text():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def esc(value):
    return html.escape(str(value or ""), quote=True)


def format_bytes(value):
    size = int(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


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
        conn.executescript('''
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
        ''')
        exists = conn.execute("SELECT id FROM tools WHERE slug='cad-100'").fetchone()
        if not exists:
            now = now_text()
            conn.execute('''INSERT INTO tools
                (slug,name,tagline,description,category,platform,icon_text,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)''', (
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
:root{--bg:#f6f6f4;--paper:#fff;--ink:#0b0c0d;--muted:#6f7278;--muted2:#97999e;--line:#e6e6e3;--soft:#efefec;--black:#0a0b0c;--shadow:0 24px 70px rgba(0,0,0,.08)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:inherit}button,input,textarea{font:inherit}.shell{width:min(1280px,calc(100% - 48px));margin:auto}
.nav-wrap{position:sticky;top:0;z-index:20;background:rgba(246,246,244,.88);backdrop-filter:blur(18px);border-bottom:1px solid rgba(230,230,227,.75)}
.nav{height:76px;display:flex;align-items:center;justify-content:space-between;gap:24px}.brand{display:flex;gap:13px;align-items:center;font-weight:760;letter-spacing:-.02em}
.mark{width:42px;height:42px;border-radius:13px;background:var(--black);color:#fff;display:grid;place-items:center;font-size:11px;font-weight:850;letter-spacing:-.02em}
.brand-title{font-size:15px;line-height:1.2}.brand small{display:block;font-size:9px;color:#8b8d91;letter-spacing:.14em;margin-top:4px;font-weight:650}
.navlinks{display:flex;align-items:center;gap:22px;font-size:12px;color:#64666b}.navlinks a:hover{color:#111}.admin-link{padding:9px 13px;border:1px solid #dededb;border-radius:999px;background:#fff}
.hero{padding:52px 0 30px}.hero-card{position:relative;overflow:hidden;background:#0a0b0c;color:#fff;border-radius:38px;min-height:520px;padding:64px 64px 52px}
.hero-card:before{content:"100%";position:absolute;right:-40px;top:-74px;font-size:250px;font-weight:900;letter-spacing:-.1em;color:rgba(255,255,255,.045);line-height:1}
.hero-kicker{font-size:11px;font-weight:750;letter-spacing:.16em;color:#a8aaae;text-transform:uppercase}
.hero h1{position:relative;z-index:1;font-size:clamp(46px,7vw,92px);line-height:.98;letter-spacing:-.065em;margin:22px 0 26px;max-width:880px}
.hero-copy{position:relative;z-index:1;font-size:17px;line-height:1.8;color:#b8babf;max-width:720px}.hero-bottom{position:absolute;left:64px;right:64px;bottom:50px;display:flex;justify-content:space-between;align-items:flex-end;gap:32px;z-index:2}
.stats{display:flex;gap:38px}.stat b{font-size:28px;letter-spacing:-.04em;display:block}.stat span{font-size:10px;color:#8f9196;letter-spacing:.05em}
.searchbox{width:min(430px,42vw);height:52px;background:#fff;border-radius:16px;display:flex;align-items:center;padding:0 16px;color:#111}.searchbox svg{width:18px;height:18px;opacity:.55;flex:none}
.searchbox input{border:0;outline:0;width:100%;height:100%;padding:0 11px;background:transparent;font-size:13px}
.toolbar{padding:34px 0 16px;display:flex;align-items:end;justify-content:space-between;gap:20px}.toolbar h2{font-size:28px;letter-spacing:-.035em;margin:0 0 5px}.toolbar p{font-size:12px;color:#8b8d92;margin:0}
.filters{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.filter{border:1px solid #dededb;background:#fff;border-radius:999px;padding:9px 13px;font-size:11px;color:#666;cursor:pointer;transition:.15s}
.filter:hover,.filter.active{background:#111;color:#fff;border-color:#111}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;padding:0 0 86px}
.tool{position:relative;background:#fff;border:1px solid var(--line);border-radius:27px;padding:22px;min-height:332px;display:flex;flex-direction:column;transition:transform .2s,box-shadow .2s,border-color .2s;overflow:hidden}
.tool:hover{transform:translateY(-4px);box-shadow:var(--shadow);border-color:#dadad6}.tool.hide{display:none}.rank{display:flex;align-items:center;justify-content:space-between;font-size:10px;color:#9b9da1;font-weight:750;letter-spacing:.08em}
.rank-num{font-size:13px;color:#111;letter-spacing:0}.icon{width:68px;height:68px;border-radius:20px;background:#0b0c0d;color:#fff;display:grid;place-items:center;font-size:14px;font-weight:850;margin:28px 0 22px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}
.tool h3{font-size:25px;letter-spacing:-.035em;margin:0 0 9px}.tagline{font-size:13px;line-height:1.7;color:#74767b;min-height:44px}.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:15px}
.chip{background:#f2f2ef;border-radius:999px;padding:6px 9px;font-size:10px;color:#6d6f73}.footrow{display:flex;justify-content:space-between;align-items:end;margin-top:auto;padding-top:22px;border-top:1px solid #efefec}
.downloads b{font-size:19px;letter-spacing:-.02em}.downloads span{font-size:9px;color:#9a9ca0;display:block;margin-top:2px}.arrow{width:38px;height:38px;border-radius:50%;background:#111;color:#fff;display:grid;place-items:center;font-size:16px;transition:.15s}
.tool:hover .arrow{transform:rotate(45deg)}.empty{display:none;background:#fff;border:1px dashed #d6d6d2;border-radius:24px;padding:52px;text-align:center;color:#888;grid-column:1/-1}
.footer{border-top:1px solid #dfdfdc;padding:30px 0 46px;font-size:10px;color:#989a9f;display:flex;justify-content:space-between;gap:20px}.footer strong{color:#666}
.detail-hero{padding:56px 0 34px}.back{display:inline-flex;align-items:center;gap:7px;font-size:11px;color:#777;margin-bottom:30px}
.product{display:grid;grid-template-columns:1fr 330px;gap:64px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:36px;padding:58px}
.product-icon{width:260px;height:260px;border-radius:58px;background:#0b0c0d;color:#fff;display:grid;place-items:center;font-size:44px;font-weight:850;justify-self:end;box-shadow:0 32px 70px rgba(0,0,0,.14)}
.eyebrow{font-size:10px;font-weight:760;letter-spacing:.14em;color:#8c8e93;text-transform:uppercase}.product h1{font-size:clamp(48px,6vw,76px);letter-spacing:-.06em;margin:12px 0 14px;line-height:1}
.lead{font-size:18px;line-height:1.7;color:#6e7075;max-width:690px}.facts{display:flex;gap:28px;margin:28px 0}.fact b{display:block;font-size:18px}.fact span{font-size:9px;color:#999}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.btn{display:inline-flex;align-items:center;justify-content:center;height:47px;padding:0 20px;border-radius:12px;background:#111;color:#fff;border:0;font-weight:720;font-size:12px;cursor:pointer}
.btn.secondary{background:#fff;color:#111;border:1px solid #d6d6d2}.detail-grid{display:grid;grid-template-columns:1.35fr .65fr;gap:16px;padding-bottom:80px}
.panel{background:#fff;border:1px solid var(--line);border-radius:25px;padding:28px}.panel h2{margin:0 0 16px;font-size:20px;letter-spacing:-.025em}.panel p{font-size:13px;line-height:1.9;color:#62646a;white-space:pre-line;margin:0}
.release-meta{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:20px}.meta-item{background:#f5f5f2;border-radius:14px;padding:13px}.meta-item b{font-size:12px;display:block}.meta-item span{font-size:9px;color:#94969b}
.screenshots{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:16px}.screenshots img{width:100%;border-radius:16px;border:1px solid #e5e5e2;display:block}
.loginwrap{min-height:100vh;display:grid;place-items:center;padding:24px}.login{width:min(420px,100%);background:#fff;border:1px solid var(--line);border-radius:26px;padding:34px}.login h1{margin:8px 0 22px;letter-spacing:-.035em}
.field{margin-bottom:12px}.field label{display:block;font-size:11px;color:#777;margin-bottom:6px}.field input,.field textarea{width:100%;border:1px solid #d7d7d3;border-radius:10px;padding:0 11px;background:#fff}.field input{height:42px}.field textarea{height:105px;padding-top:10px;resize:vertical}
.admin{max-width:1180px;margin:auto;padding:34px 22px 70px}.adminhead{display:flex;justify-content:space-between;align-items:end;margin-bottom:24px}.cards{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:#fff;border:1px solid var(--line);border-radius:20px;padding:21px}.card h2{margin-top:0}
.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;border-bottom:1px solid #eee;padding:10px 8px;font-size:11px}.msg{font-size:11px;min-height:18px;margin-top:8px}.ok{color:#287a37}.bad{color:#b42318}
@media(max-width:950px){.grid{grid-template-columns:1fr 1fr}.product{grid-template-columns:1fr 240px;padding:38px}.product-icon{width:220px;height:220px}.detail-grid{grid-template-columns:1fr}.cards{grid-template-columns:1fr}.hero-card{padding:50px 42px 44px}.hero-bottom{left:42px;right:42px}.searchbox{width:45vw}}
@media(max-width:680px){.shell{width:min(100% - 28px,1280px)}.navlinks a:not(.admin-link){display:none}.hero{padding-top:24px}.hero-card{min-height:560px;border-radius:28px;padding:38px 26px}.hero-card:before{font-size:150px;top:-28px}.hero-bottom{left:26px;right:26px;bottom:28px;display:block}.stats{margin-bottom:20px}.searchbox{width:100%}.toolbar{display:block}.filters{justify-content:flex-start;margin-top:16px}.grid{grid-template-columns:1fr}.product{grid-template-columns:1fr;padding:28px;border-radius:28px}.product-icon{justify-self:start;width:130px;height:130px;border-radius:32px;font-size:24px;grid-row:1}.product>div:first-child{grid-row:2}.facts{flex-wrap:wrap}.footer{flex-direction:column}}
'''

JS = r'''
<script>
(() => {
  const input = document.getElementById('tool-search');
  const buttons = [...document.querySelectorAll('.filter')];
  const cards = [...document.querySelectorAll('.tool')];
  const empty = document.getElementById('empty-state');
  let category = 'all';
  function apply() {
    const q = (input?.value || '').trim().toLowerCase();
    let visible = 0;
    cards.forEach(card => {
      const matchesText = !q || (card.dataset.search || '').includes(q);
      const matchesCategory = category === 'all' || card.dataset.category === category;
      const show = matchesText && matchesCategory;
      card.classList.toggle('hide', !show);
      if (show) visible++;
    });
    if (empty) empty.style.display = visible ? 'none' : 'block';
  }
  input?.addEventListener('input', apply);
  buttons.forEach(btn => btn.addEventListener('click', () => {
    category = btn.dataset.category;
    buttons.forEach(b => b.classList.toggle('active', b === btn));
    apply();
  }));
})();
</script>
'''


def page(body, title="深圳院设计100% · 工具开发板", extra=""):
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0b0c">
<title>{esc(title)}</title><style>{CSS}</style></head><body>{body}{extra}</body></html>'''


def nav():
    return '''<div class="nav-wrap"><div class="shell"><nav class="nav">
<a class="brand" href="/"><div class="mark">100%</div><div class="brand-title">深圳院设计100%<small>TOOL DEVELOPMENT BOARD</small></div></a>
<div class="navlinks"><a href="/#tools">工具</a><a href="/#about">关于</a><a class="admin-link" href="/manage">管理</a></div>
</nav></div></div>'''


@app.get("/", response_class=HTMLResponse)
def home():
    init_db()
    with db() as conn:
        tools = conn.execute("SELECT * FROM tools WHERE active=1 ORDER BY downloads DESC,id ASC").fetchall()
        total = sum(int(t["downloads"] or 0) for t in tools)
        categories = []
        for t in tools:
            c = t["category"] or "效率工具"
            if c not in categories:
                categories.append(c)
        cards = []
        for i, t in enumerate(tools, 1):
            rel = latest_release(conn, t["id"])
            version = rel["version"] if rel else "待发布"
            search_text = f"{t['name']} {t['tagline']} {t['category']} {t['platform']}".lower()
            cards.append(f'''<a class="tool" href="/tools/{esc(t['slug'])}" data-category="{esc(t['category'])}" data-search="{esc(search_text)}">
<div class="rank"><span>DOWNLOAD RANK</span><span class="rank-num">#{i:02d}</span></div>
<div class="icon">{esc(t['icon_text'])}</div><h3>{esc(t['name'])}</h3><div class="tagline">{esc(t['tagline'])}</div>
<div class="chips"><span class="chip">{esc(t['category'])}</span><span class="chip">{esc(t['platform'])}</span><span class="chip">v{esc(version)}</span></div>
<div class="footrow"><div class="downloads"><b>{int(t['downloads']):,}</b><span>累计下载</span></div><div class="arrow">↗</div></div></a>''')
    filters = ['<button class="filter active" data-category="all">全部</button>']
    filters += [f'<button class="filter" data-category="{esc(c)}">{esc(c)}</button>' for c in categories]
    body = nav() + f'''<div class="shell"><section class="hero"><div class="hero-card">
<div class="hero-kicker">DESIGN × TECHNOLOGY × PRODUCTIVITY</div><h1>100% 工具开发板</h1>
<div class="hero-copy">把设计生产中的重复劳动，沉淀成每个人都能直接使用的工具。<br>让设计师把更多时间留给判断、创意与设计本身。</div>
<div class="hero-bottom"><div class="stats"><div class="stat"><b>{len(tools)}</b><span>已发布工具</span></div><div class="stat"><b>{total:,}</b><span>累计下载</span></div></div>
<label class="searchbox" aria-label="搜索工具"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4.2-4.2"></path></svg><input id="tool-search" placeholder="搜索工具、分类或关键词"></label></div>
</div></section><section id="tools"><div class="toolbar"><div><h2>工具排行</h2><p>按累计下载量自动排序 · 点击进入工具详情</p></div><div class="filters">{''.join(filters)}</div></div>
<main class="grid">{''.join(cards)}<div id="empty-state" class="empty">没有找到匹配的工具。</div></main></section>
<footer id="about" class="footer"><span><strong>深圳院设计100%</strong> · 工具开发板</span><span>面向真实设计生产流程持续迭代 · Internal Design Tools</span></footer></div>'''
    return HTMLResponse(page(body, extra=JS), headers={"Cache-Control": "no-cache"})


@app.get("/tools/{slug}", response_class=HTMLResponse)
def detail(slug: str):
    with db() as conn:
        t = conn.execute("SELECT * FROM tools WHERE slug=? AND active=1", (slug,)).fetchone()
        if not t: raise HTTPException(status_code=404, detail="工具不存在。")
        rel = latest_release(conn, t["id"])
    version = rel["version"] if rel else "待发布"
    notes = rel["notes"] if rel else "暂无版本说明。"
    size = format_bytes(rel["size"]) if rel else "—"
    published = rel["published_at"][:10] if rel and rel["published_at"] else "—"
    download = f'<a class="btn" href="/tools/{esc(slug)}/download">下载 Windows 版 · v{esc(version)}</a>' if rel else '<span class="btn" style="background:#b4b4b0">安装包待发布</span>'
    shots=[]
    for raw in (t["screenshots"] or "").replace(",", "\n").splitlines():
        url=raw.strip()
        if url.startswith("https://") or url.startswith("http://"): shots.append(f'<img src="{esc(url)}" alt="{esc(t["name"])} 软件截图" loading="lazy">')
    screenshots=f'<div class="screenshots">{"".join(shots)}</div>' if shots else ""
    body = nav() + f'''<div class="shell"><section class="detail-hero"><a class="back" href="/">← 返回工具开发板</a><div class="product"><div>
<div class="eyebrow">{esc(t['category'])} · {esc(t['platform'])}</div><h1>{esc(t['name'])}</h1><div class="lead">{esc(t['tagline'])}</div>
<div class="facts"><div class="fact"><b>v{esc(version)}</b><span>当前版本</span></div><div class="fact"><b>{int(t['downloads']):,}</b><span>累计下载</span></div><div class="fact"><b>{esc(t['platform'])}</b><span>运行平台</span></div></div><div class="actions">{download}</div></div>
<div class="product-icon">{esc(t['icon_text'])}</div></div></section><section class="detail-grid"><div class="panel"><h2>工具介绍</h2><p>{esc(t['description'])}</p>{screenshots}</div>
<div class="panel"><h2>当前版本</h2><p><b>v{esc(version)}</b>\n\n{esc(notes)}</p><div class="release-meta"><div class="meta-item"><b>{esc(published)}</b><span>发布日期</span></div><div class="meta-item"><b>{esc(size)}</b><span>安装包大小</span></div></div></div></section>
<footer class="footer"><span><strong>深圳院设计100%</strong> · 工具开发板</span><span>{esc(t['name'])}</span></footer></div>'''
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
        body='''<div class="loginwrap"><div class="login"><div class="eyebrow">DESIGN 100</div><h1>工具开发板管理</h1><form id="f"><div class="field"><label>管理密码</label><input id="p" type="password" autofocus></div><button class="btn" type="submit">进入后台</button><div id="m" class="msg"></div></form></div></div><script>document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();const r=await fetch('/manage/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('p').value})});const j=await r.json().catch(()=>({}));if(r.ok)location.href='/manage';else document.getElementById('m').textContent=j.detail||'登录失败';});</script>'''
        return HTMLResponse(page(body,"工具开发板管理"))
    with db() as conn:
        tools=conn.execute("SELECT * FROM tools ORDER BY downloads DESC,id DESC").fetchall()
        rows=''.join([f"<tr><td>{esc(t['name'])}</td><td>{esc(t['slug'])}</td><td>{esc(t['category'])}</td><td>{int(t['downloads']):,}</td><td><a href='/tools/{esc(t['slug'])}'>查看</a></td></tr>" for t in tools])
    body=f'''<div class="admin"><div class="adminhead"><div><div class="eyebrow">DESIGN 100</div><h1 style="margin:6px 0 0">工具开发板管理</h1></div><button class="btn secondary" onclick="fetch('/manage/logout',{{method:'POST'}}).then(()=>location.href='/manage')">退出</button></div>
<div class="cards"><div class="card"><h2>新增工具</h2><form action="/manage/tools" method="post"><div class="field"><label>工具名称</label><input name="name" required></div><div class="field"><label>URL 标识</label><input name="slug" placeholder="例如 pdf-tool" required></div><div class="field"><label>一句话介绍</label><input name="tagline"></div><div class="field"><label>分类</label><input name="category" value="效率工具"></div><div class="field"><label>平台</label><input name="platform" value="Windows"></div><div class="field"><label>图标文字</label><input name="icon_text" value="100"></div><div class="field"><label>完整介绍</label><textarea name="description"></textarea></div><button class="btn">新增工具</button></form></div>
<div class="card"><h2>发布版本</h2><form action="/manage/releases" method="post" enctype="multipart/form-data"><div class="field"><label>工具 slug</label><input name="slug" placeholder="cad-100" required></div><div class="field"><label>版本号</label><input name="version" placeholder="2.1.0" required></div><div class="field"><label>更新说明</label><textarea name="notes"></textarea></div><div class="field"><label>安装包</label><input name="package" type="file" required></div><button class="btn">发布版本</button></form></div></div>
<div class="card" style="margin-top:16px"><h2>已发布工具</h2><table class="table"><thead><tr><th>名称</th><th>Slug</th><th>分类</th><th>下载量</th><th></th></tr></thead><tbody>{rows}</tbody></table></div></div>'''
    return HTMLResponse(page(body,"工具开发板管理"))


@app.post("/manage/login")
async def manage_login(request: Request):
    if not ADMIN_PASSWORD: raise HTTPException(status_code=503,detail="后台密码未配置。")
    data=await request.json()
    if not hmac.compare_digest(str(data.get("password","")),ADMIN_PASSWORD): raise HTTPException(status_code=401,detail="密码不正确。")
    resp=JSONResponse({"success":True}); resp.set_cookie(COOKIE_NAME,session_token(),httponly=True,secure=True,samesite="strict",max_age=8*3600); return resp


@app.post("/manage/logout")
def manage_logout():
    resp=JSONResponse({"success":True}); resp.delete_cookie(COOKIE_NAME); return resp


@app.post("/manage/tools")
def create_tool(request: Request,name: str=Form(...),slug: str=Form(...),tagline: str=Form(""),description: str=Form(""),category: str=Form("效率工具"),platform: str=Form("Windows"),icon_text: str=Form("100")):
    require_admin(request); now=now_text()
    try:
        with db() as conn: conn.execute('''INSERT INTO tools(slug,name,tagline,description,category,platform,icon_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)''',(slug.strip(),name.strip(),tagline.strip(),description.strip(),category.strip(),platform.strip(),icon_text.strip(),now,now))
    except sqlite3.IntegrityError: raise HTTPException(status_code=409,detail="slug 已存在。")
    return RedirectResponse('/manage',status_code=303)


@app.post("/manage/releases")
async def create_release(request: Request,slug: str=Form(...),version: str=Form(...),notes: str=Form(""),package: UploadFile=File(...)):
    require_admin(request); content=await package.read()
    if not content: raise HTTPException(status_code=400,detail="安装包不能为空。")
    with db() as conn:
        t=conn.execute("SELECT * FROM tools WHERE slug=?",(slug.strip(),)).fetchone()
        if not t: raise HTTPException(status_code=404,detail="工具不存在。")
        safe_name=(package.filename or f"{slug}-{version}.zip").replace('/','_').replace('\\','_'); tool_dir=PACKAGE_DIR / slug.strip(); tool_dir.mkdir(parents=True,exist_ok=True); path=tool_dir / safe_name; path.write_bytes(content); digest=hashlib.sha256(content).hexdigest(); conn.execute("UPDATE releases SET active=0 WHERE tool_id=?",(t['id'],)); conn.execute('''INSERT INTO releases(tool_id,version,notes,package_name,package_path,sha256,size,published_at,active) VALUES(?,?,?,?,?,?,?,?,1)''',(t['id'],version.strip(),notes.strip(),safe_name,str(path),digest,len(content),now_text()))
    return RedirectResponse('/manage',status_code=303)
