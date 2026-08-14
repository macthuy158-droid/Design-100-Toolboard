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
ADMIN_USERNAME = os.getenv("TOOLBOARD_ADMIN_USERNAME", "admin").strip() or "admin"
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


def nav():
    return '''<header class="topbar"><div class="brand"><a href="/">100%</a></div><div class="navlinks"><a href="/#tools">工具</a><a href="/#about">关于</a><a class="admin-link" href="/manage">管理</a></div></header>'''


def page(body, title="深圳院设计100%", extra=""):
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f4f4f1;color:#111;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}a{{color:inherit;text-decoration:none}}.topbar{{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:rgba(244,244,241,.94);position:sticky;top:0;z-index:30;border-bottom:1px solid #e8e8e4;backdrop-filter:blur(16px)}}.brand a{{font-size:18px;font-weight:900;letter-spacing:-.05em}}.navlinks{{display:flex;gap:18px;font-size:11px;align-items:center}}.admin-link{{border:1px solid #d8d8d4;border-radius:999px;padding:7px 11px}}.shell{{max-width:1180px;margin:auto;padding:0 26px}}.hero{{padding:82px 0 52px}}.eyebrow{{font-size:10px;letter-spacing:.14em;font-weight:750;color:#8b8d92;text-transform:uppercase}}.hero h1{{font-size:70px;letter-spacing:-.065em;margin:13px 0 22px;line-height:.96}}.hero p{{max-width:720px;font-size:17px;line-height:1.8;color:#5d6065}}.btn{{display:inline-flex;align-items:center;justify-content:center;min-height:40px;border:0;border-radius:11px;background:#111;color:#fff;padding:0 16px;font-size:11px;font-weight:700;cursor:pointer}}.btn.secondary{{background:#fff;color:#111;border:1px solid #ddd}}.field{{margin-bottom:14px}}.field label{{display:block;font-size:10px;color:#777;margin-bottom:6px}}.field input,.field textarea,.field select{{width:100%;padding:11px 12px;border:1px solid #ddd;border-radius:10px;background:#fff;font:inherit;font-size:12px}}.field textarea{{min-height:105px;resize:vertical}}.loginwrap{{min-height:76vh;display:grid;place-items:center;padding:30px}}.login{{width:min(410px,100%);background:#fff;border:1px solid #e1e1dd;border-radius:24px;padding:28px}}.login h1{{margin:7px 0 22px;font-size:28px}}.msg{{font-size:11px;color:#b12e2e;margin-top:12px}}
    </style>{extra}</head><body>{body}</body></html>'''


def home_card(tool, release):
    version = release["version"] if release else "待发布"
    return f'''<a class="tool-card" href="/tools/{esc(tool['slug'])}"><div class="tool-icon">{esc(tool['icon_text'])}</div><div class="tool-info"><div class="tool-top"><span>{esc(tool['category'])}</span><span>{esc(tool['platform'])}</span></div><h3>{esc(tool['name'])}</h3><p>{esc(tool['tagline'])}</p><div class="tool-bottom"><span>v{esc(version)}</span><span>{int(tool['downloads']):,} downloads</span></div></div></a>'''


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    init_db()
    with db() as conn:
        tools = conn.execute("SELECT * FROM tools WHERE active=1 ORDER BY downloads DESC,id ASC").fetchall()
        releases = {t["id"]: latest_release(conn, t["id"]) for t in tools}
        total_downloads = sum(int(t["downloads"]) for t in tools)
        categories = sorted({str(t["category"]) for t in tools if t["category"]})

    cards = ''.join(home_card(t, releases[t["id"]]) for t in tools)
    filters = ''.join(f'<button class="filter" data-cat="{esc(c)}">{esc(c)}</button>' for c in categories)
    body = f'''{nav()}<main class="shell"><section class="hero"><div class="eyebrow">DESIGN × TECHNOLOGY × PRODUCTIVITY</div><h1>深圳院设计100%</h1><p>把设计生产中的重复劳动，沉淀成每个人都能直接使用的工具。让设计师把更多时间留给判断、创意与设计本身。</p></section><section id="tools"><div class="stats-row"><div><b>{len(tools)}</b><span>已发布工具</span></div><div><b>{total_downloads:,}</b><span>累计下载</span></div></div><div class="toolbar"><input id="search" placeholder="搜索工具"><div class="filters"><button class="filter active" data-cat="all">全部</button>{filters}</div></div><div id="grid" class="tool-grid">{cards}</div></section></main><style>
    .stats-row{{display:flex;gap:12px;margin-bottom:26px}}.stats-row div{{background:#fff;border-radius:16px;padding:16px 18px;min-width:132px}}.stats-row b{{display:block;font-size:21px}}.stats-row span{{font-size:9px;color:#888}}.toolbar{{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:20px}}.toolbar input{{width:min(320px,100%);border:1px solid #ddd;border-radius:999px;padding:10px 14px;background:#fff}}.filters{{display:flex;gap:7px;flex-wrap:wrap}}.filter{{border:1px solid #ddd;border-radius:999px;background:#fff;padding:8px 11px;font-size:10px;cursor:pointer}}.filter.active{{background:#111;color:#fff;border-color:#111}}.tool-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;padding-bottom:70px}}.tool-card{{background:#fff;border:1px solid #e4e4e0;border-radius:23px;padding:19px;display:flex;gap:16px;min-height:180px}}.tool-icon{{width:55px;height:55px;border-radius:16px;background:#111;color:#fff;display:grid;place-items:center;font-size:11px;font-weight:800;flex:none}}.tool-info{{min-width:0;display:flex;flex-direction:column;flex:1}}.tool-top,.tool-bottom{{display:flex;justify-content:space-between;gap:8px;color:#96989d;font-size:9px}}.tool-info h3{{font-size:20px;margin:15px 0 7px}}.tool-info p{{font-size:11px;color:#777;line-height:1.6;margin:0;flex:1}}.tool-bottom{{margin-top:16px}}@media(max-width:900px){{.tool-grid{{grid-template-columns:1fr 1fr}}.hero h1{{font-size:54px}}}}@media(max-width:620px){{.tool-grid{{grid-template-columns:1fr}}.toolbar{{align-items:flex-start;flex-direction:column}}.hero h1{{font-size:44px}}}}
    </style><script>
    const q=document.getElementById('search'),buttons=[...document.querySelectorAll('.filter')],cardsEls=[...document.querySelectorAll('.tool-card')];let cat='all';function run(){{const x=(q.value||'').toLowerCase();cardsEls.forEach(c=>{{const text=c.innerText.toLowerCase();const category=c.querySelector('.tool-top span')?.innerText||'';c.style.display=(text.includes(x)&&(cat==='all'||category===cat))?'flex':'none'}})}}q.addEventListener('input',run);buttons.forEach(b=>b.onclick=()=>{{buttons.forEach(x=>x.classList.remove('active'));b.classList.add('active');cat=b.dataset.cat;run()}})
    </script>'''
    return HTMLResponse(page(body))
