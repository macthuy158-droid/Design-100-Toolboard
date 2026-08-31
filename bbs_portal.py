import html
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import coin_core
import community_core

router = APIRouter()

BOARDS = {
    "lab": {
        "name": "黑科技实验室",
        "icon": "🧪",
        "desc": "AI Coding、Agent、CAD/BIM 自动化与各种技术实验。",
    },
    "bounty": {
        "name": "悬赏墙",
        "icon": "💰",
        "desc": "把真实设计需求变成可交易、可交付的开发任务。",
    },
    "tree": {
        "name": "设计院树洞",
        "icon": "🌳",
        "desc": "聊工作、行业、AI 和设计院里的真实日常，可匿名。",
    },
}

CSS = r'''<style>
.bbs-shell{padding:42px 0 82px}.bbs-hero{background:#0a0b0c;color:#fff;border-radius:32px;padding:38px 42px;margin-bottom:24px}.bbs-kicker{font-size:10px;letter-spacing:.15em;color:#8f9196;font-weight:800}.bbs-hero h1{font-size:44px;letter-spacing:-.05em;margin:12px 0 8px}.bbs-hero p{margin:0;color:#a9abb0;font-size:13px;line-height:1.8}.bbs-board-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0}.bbs-board{background:#fff;border:1px solid var(--line);border-radius:22px;padding:20px;transition:.15s}.bbs-board:hover{transform:translateY(-2px);box-shadow:var(--shadow)}.bbs-board .ico{font-size:22px}.bbs-board h3{font-size:18px;margin:15px 0 6px;letter-spacing:-.03em}.bbs-board p{font-size:11px;line-height:1.65;color:#777;margin:0}.bbs-board.active{background:#111;color:#fff;border-color:#111}.bbs-board.active p{color:#aaa}.bbs-head{display:flex;align-items:end;justify-content:space-between;gap:18px;margin:30px 0 14px}.bbs-head h2{font-size:27px;margin:0 0 4px;letter-spacing:-.04em}.bbs-head p{font-size:11px;color:#888;margin:0}.bbs-list{background:#fff;border:1px solid var(--line);border-radius:23px;overflow:hidden}.bbs-row{display:grid;grid-template-columns:minmax(0,1fr) 140px 70px;gap:18px;align-items:center;padding:18px 20px;border-bottom:1px solid #eeeeeb}.bbs-row:last-child{border-bottom:0}.bbs-row:hover{background:#fafaf8}.bbs-title{font-size:14px;font-weight:720}.bbs-meta{font-size:10px;color:#999;margin-top:5px}.bbs-author{font-size:11px;color:#777;text-align:right}.bbs-count{font-size:10px;color:#999;text-align:right}.bbs-empty{padding:36px;text-align:center;color:#888;font-size:11px}.bbs-form,.bbs-post{background:#fff;border:1px solid var(--line);border-radius:25px;padding:28px}.bbs-form h1,.bbs-post h1{margin:0 0 20px;font-size:30px;letter-spacing:-.04em}.bbs-form label{font-size:11px;color:#777;display:block;margin:14px 0 7px}.bbs-form input[type=text],.bbs-form textarea{width:100%;border:1px solid #d8d8d5;border-radius:12px;padding:12px;background:#fff}.bbs-form textarea{min-height:180px;resize:vertical}.bbs-check{display:flex;gap:9px;align-items:center;margin:14px 0;font-size:11px;color:#666}.bbs-post-content{font-size:14px;line-height:1.9;color:#444;white-space:pre-wrap}.bbs-replies{margin-top:18px}.bbs-reply{background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;margin-bottom:10px}.bbs-reply-head{font-size:10px;color:#999;margin-bottom:8px}.bbs-reply-body{font-size:13px;line-height:1.8;white-space:pre-wrap}.bbs-actions{display:flex;gap:8px;flex-wrap:wrap}.bbs-bounty-money{font-size:16px;font-weight:800;text-align:right}.bbs-bounty-status{font-size:10px;color:#999;text-align:right}.bbs-note{font-size:11px;color:#888;margin-top:10px}.bbs-form select{height:44px;border:1px solid #d8d8d5;border-radius:12px;background:#fff;padding:0 10px}.bbs-back{display:inline-block;font-size:11px;color:#777;margin-bottom:14px}
@media(max-width:800px){.bbs-board-grid{grid-template-columns:1fr}.bbs-row{grid-template-columns:1fr auto}.bbs-author{grid-column:1;text-align:left}.bbs-count{grid-column:2;grid-row:1/3}.bbs-hero{padding:28px}.bbs-hero h1{font-size:36px}}
</style>'''


def esc(v):
    return html.escape(str(v or ""), quote=True)


def init_db():
    with site.db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS bbs_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board TEXT NOT NULL CHECK(board IN ('lab','tree')),
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            anonymous INTEGER NOT NULL DEFAULT 0,
            views INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bbs_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            anonymous INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES bbs_posts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_bbs_posts_board ON bbs_posts(board,id DESC);
        CREATE INDEX IF NOT EXISTS idx_bbs_replies_post ON bbs_replies(post_id,id ASC);
        ''')


def _identity(row, anonymous=False):
    if anonymous:
        return "匿名设计师"
    name = esc(row["display_name"])
    return f"{name} · 小飞侠" if row["role"] == community_core.ROLE_XIAOFEIXIA else name


def _page(body, title="小飞侠 BBS"):
    return HTMLResponse(site.page(site.nav() + f'<div class="shell bbs-shell">{body}</div>', title=title, extra=CSS), headers={"Cache-Control": "no-cache"})


@router.get("/bbs", response_class=HTMLResponse)
def bbs_home(request: Request, board: str = "all"):
    init_db()
    if board not in {"all", *BOARDS.keys()}:
        board = "all"
    cards = "".join(
        f'''<a class="bbs-board {'active' if board == key else ''}" href="/bbs?board={key}"><div class="ico">{meta['icon']}</div><h3>{meta['name']}</h3><p>{meta['desc']}</p></a>'''
        for key, meta in BOARDS.items()
    )

    if board == "bounty":
        with site.db() as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bounties'").fetchone()
            rows = conn.execute("SELECT id,title,category,reward,status FROM bounties ORDER BY id DESC LIMIT 30").fetchall() if exists else []
        listing = "".join(
            f'''<a class="bbs-row" href="/bounties/{r['id']}"><div><div class="bbs-title">{esc(r['title'])}</div><div class="bbs-meta">{esc(r['category'])} · {esc(r['status'])}</div></div><div class="bbs-bounty-money">{int(r['reward'] or 0):,} {coin_core.COIN_NAME}</div><div class="bbs-count">查看 →</div></a>'''
            for r in rows
        ) or '<div class="bbs-empty">悬赏墙还没有任务。</div>'
        actions = '<div class="bbs-actions"><a class="btn" href="/bounties/new">发布悬赏</a><a class="btn secondary" href="/bounties">全部交易</a></div>'
        subtitle = "有明确交付目标的需求，直接在这里交易。"
        title = BOARDS["bounty"]["name"]
    else:
        where = "" if board == "all" else "WHERE p.board=?"
        params = () if board == "all" else (board,)
        with site.db() as conn:
            rows = conn.execute(
                f'''SELECT p.*,u.display_name,u.role,
                    (SELECT COUNT(*) FROM bbs_replies r WHERE r.post_id=p.id) AS reply_count
                    FROM bbs_posts p JOIN community_users u ON u.id=p.user_id
                    {where} ORDER BY p.id DESC LIMIT 40''', params
            ).fetchall()
        listing = "".join(
            f'''<a class="bbs-row" href="/bbs/post/{r['id']}"><div><div class="bbs-title">{BOARDS[r['board']]['icon']} {esc(r['title'])}</div><div class="bbs-meta">{BOARDS[r['board']]['name']} · {esc(r['created_at'][:10])}</div></div><div class="bbs-author">{_identity(r, bool(r['anonymous']))}</div><div class="bbs-count">{int(r['reply_count'])} 回复<br>{int(r['views'])} 浏览</div></a>'''
            for r in rows
        ) or '<div class="bbs-empty">这里还没有帖子，发第一帖吧。</div>'
        actions = '<div class="bbs-actions"><a class="btn" href="/bbs/new">+ 发帖</a></div>'
        subtitle = "技术、交易和真实行业日常，都在这里发生。" if board == "all" else BOARDS[board]["desc"]
        title = "正在发生" if board == "all" else BOARDS[board]["name"]

    body = f'''<section class="bbs-hero"><div class="bbs-kicker">DESIGNERS · TOOLS · COMMUNITY</div><h1>小飞侠 BBS</h1><p>不是官方论坛。这里是设计师自己讨论技术、发布悬赏和说真话的地方。</p></section>
<div class="bbs-board-grid">{cards}</div>
<div class="bbs-head"><div><h2>{title}</h2><p>{subtitle}</p></div>{actions}</div>
<div class="bbs-list">{listing}</div>'''
    return _page(body)


@router.get("/bbs/new", response_class=HTMLResponse)
def new_post(request: Request):
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login?next=/bbs/new", status_code=303)
    body = '''<a class="bbs-back" href="/bbs">← 返回 BBS</a><form class="bbs-form" method="post" action="/bbs/new"><h1>发一帖</h1>
<label>板块</label><select name="board"><option value="lab">🧪 黑科技实验室</option><option value="tree">🌳 设计院树洞</option></select>
<label>标题</label><input type="text" name="title" maxlength="100" required placeholder="说清楚你想聊什么">
<label>正文</label><textarea name="content" required placeholder="把问题、方法或者想说的话写下来"></textarea>
<label class="bbs-check"><input type="checkbox" name="anonymous" value="1"> 在设计院树洞匿名发布</label>
<div class="bbs-actions"><button class="btn" type="submit">发布</button><a class="btn secondary" href="/bbs">取消</a></div></form>'''
    return _page(body, "发帖 · 小飞侠 BBS")


@router.post("/bbs/new")
def create_post(request: Request, board: str = Form(...), title: str = Form(...), content: str = Form(...), anonymous: str = Form("")):
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    if board not in {"lab", "tree"}:
        raise HTTPException(400, "请选择正确板块。")
    title = title.strip()
    content = content.strip()
    if not title or not content:
        raise HTTPException(400, "标题和正文不能为空。")
    is_anon = 1 if board == "tree" and anonymous == "1" else 0
    stamp = community_core.now()
    with site.db() as conn:
        cur = conn.execute("INSERT INTO bbs_posts(board,user_id,title,content,anonymous,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (board, user["id"], title[:100], content, is_anon, stamp, stamp))
        pid = cur.lastrowid
    return RedirectResponse(f"/bbs/post/{pid}", status_code=303)


@router.get("/bbs/post/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, post_id: int):
    init_db()
    with site.db() as conn:
        row = conn.execute("SELECT p.*,u.display_name,u.role FROM bbs_posts p JOIN community_users u ON u.id=p.user_id WHERE p.id=?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(404, "帖子不存在。")
        conn.execute("UPDATE bbs_posts SET views=views+1 WHERE id=?", (post_id,))
        replies = conn.execute("SELECT r.*,u.display_name,u.role FROM bbs_replies r JOIN community_users u ON u.id=r.user_id WHERE r.post_id=? ORDER BY r.id ASC", (post_id,)).fetchall()
    reply_html = "".join(
        f'''<div class="bbs-reply"><div class="bbs-reply-head">{_identity(r, bool(r['anonymous']))} · {esc(r['created_at'][:16].replace('T',' '))}</div><div class="bbs-reply-body">{esc(r['content'])}</div></div>'''
        for r in replies
    ) or '<div class="bbs-empty">还没有回复。</div>'
    user = community_core.current_user(request)
    reply_form = '''<form class="bbs-form" method="post" action="/bbs/post/%d/reply"><label>回复</label><textarea name="content" required style="min-height:100px"></textarea>%s<div class="bbs-actions"><button class="btn" type="submit">回复</button></div></form>''' % (post_id, '<label class="bbs-check"><input type="checkbox" name="anonymous" value="1"> 匿名回复</label>' if row['board'] == 'tree' else '') if user else '<div class="bbs-note"><a href="/account/login">登录后参与回复 →</a></div>'
    body = f'''<a class="bbs-back" href="/bbs?board={row['board']}">← {BOARDS[row['board']]['name']}</a><article class="bbs-post"><div class="bbs-meta">{BOARDS[row['board']]['icon']} {BOARDS[row['board']]['name']} · {_identity(row, bool(row['anonymous']))}</div><h1>{esc(row['title'])}</h1><div class="bbs-post-content">{esc(row['content'])}</div></article><div class="bbs-head"><div><h2>{len(replies)} 条回复</h2></div></div><div class="bbs-replies">{reply_html}</div>{reply_form}'''
    return _page(body, f"{row['title']} · 小飞侠 BBS")


@router.post("/bbs/post/{post_id}/reply")
def reply_post(request: Request, post_id: int, content: str = Form(...), anonymous: str = Form("")):
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    content = content.strip()
    if not content:
        raise HTTPException(400, "回复不能为空。")
    with site.db() as conn:
        post = conn.execute("SELECT board FROM bbs_posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(404, "帖子不存在。")
        is_anon = 1 if post["board"] == "tree" and anonymous == "1" else 0
        conn.execute("INSERT INTO bbs_replies(post_id,user_id,content,anonymous,created_at) VALUES(?,?,?,?,?)", (post_id, user["id"], content, is_anon, community_core.now()))
    return RedirectResponse(f"/bbs/post/{post_id}", status_code=303)
