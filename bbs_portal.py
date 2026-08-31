import html
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import coin_core
import community_core

router = APIRouter()

MAX_TITLE = 100
MAX_CONTENT = 5000

BOARDS = {
    "lab": {
        "name": "黑科技实验室",
        "icon": "🧪",
        "desc": "AI Coding、Agent、CAD/BIM 自动化与各种技术实验。",
        "accent": "#3b5bdb",
        "unit": "帖",
        "rules": [],
    },
    "bounty": {
        "name": "悬赏墙",
        "icon": "💰",
        "desc": "把真实设计需求变成可交易、可交付的开发任务。",
        "accent": "#c07800",
        "unit": "个任务",
        "rules": [],
    },
    "tree": {
        "name": "设计院树洞",
        "icon": "🌳",
        "desc": "聊工作、行业、AI 和设计院里的真实日常，可匿名。",
        "accent": "#2f6f3b",
        "unit": "帖",
        "rules": [
            "可以吐槽事，不点名骂人。",
            "不发未公开的项目信息和客户信息。",
            "匿名是对同事的保护，不是攻击的掩护。",
        ],
    },
}

CSS = r'''<style>
.bbs-shell{padding:38px 0 82px}
.bbs-hero{background:#0a0b0c;color:#fff;border-radius:30px;padding:34px 38px;margin-bottom:20px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:34px;align-items:center}
.bbs-kicker{font-size:10px;letter-spacing:.15em;color:#8f9196;font-weight:800}
.bbs-hero h1{font-size:38px;letter-spacing:-.05em;margin:10px 0 7px}
.bbs-hero p{margin:0;color:#a9abb0;font-size:12.5px;line-height:1.75;max-width:520px}
.bbs-stats{display:flex;gap:26px}
.bbs-stat b{display:block;font-size:24px;letter-spacing:-.04em;line-height:1}
.bbs-stat span{font-size:9px;color:#8f9196;letter-spacing:.05em}

.bbs-board-grid{display:flex;flex-direction:column;gap:9px;margin-bottom:26px}
.bbs-board{position:relative;background:#fff;border:1px solid var(--line);border-radius:16px;padding:15px 20px 15px 22px;transition:.16s;overflow:hidden;display:grid;grid-template-columns:30px minmax(0,1fr) auto auto;align-items:center;gap:16px;color:#111}
.bbs-board:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}
.bbs-board:hover{border-color:color-mix(in srgb,var(--accent) 40%,var(--line));background:color-mix(in srgb,var(--accent) 3%,#fff)}
.bbs-board .ico{font-size:19px;line-height:1}
.bbs-board h3{font-size:15px;margin:0 0 3px;letter-spacing:-.03em}
.bbs-board p{font-size:10.5px;line-height:1.55;color:#84868b;margin:0}
.bbs-board-count{font-size:9px;font-weight:750;color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,#fff);border:1px solid color-mix(in srgb,var(--accent) 22%,#fff);border-radius:999px;padding:4px 9px;white-space:nowrap}
.bbs-board-go{font-size:10px;font-weight:700;color:var(--accent);white-space:nowrap}
.bbs-board.active{background:color-mix(in srgb,var(--accent) 7%,#fff);border-color:color-mix(in srgb,var(--accent) 45%,#fff)}
.bbs-board.active:before{width:5px}
.bbs-board.active h3{color:var(--accent)}
.bbs-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin:0 0 13px}
.bbs-head h2{font-size:23px;margin:0 0 4px;letter-spacing:-.04em}
.bbs-head p{font-size:11px;color:#888;margin:0}
.bbs-list{background:#fff;border:1px solid var(--line);border-radius:22px;overflow:hidden}
.bbs-row{display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:14px;align-items:center;padding:15px 20px;border-bottom:1px solid #f0f0ed;color:#111}
.bbs-row:last-child{border-bottom:0}
.bbs-row:hover{background:#fafaf8}
.bbs-avatar{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;font-size:14px;background:#f2f2ef}
.bbs-avatar.tag{color:#fff;font-size:11px;font-weight:800}
.bbs-title{font-size:13.5px;font-weight:700;line-height:1.45;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bbs-meta{font-size:10px;color:#9a9ca0;margin-top:4px;display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.bbs-chip{border-radius:999px;padding:2px 7px;font-size:9px;font-weight:700;background:#f2f2ef;color:#6d6f73}
.bbs-chip.accent{background:color-mix(in srgb,var(--accent) 12%,#fff);color:var(--accent)}
.bbs-right{text-align:right;white-space:nowrap}
.bbs-money{font-size:15px;font-weight:800;letter-spacing:-.02em}
.bbs-count{font-size:10px;color:#9a9ca0;line-height:1.5}
.bbs-empty{padding:44px 24px;text-align:center}
.bbs-empty h3{margin:0 0 7px;font-size:16px;letter-spacing:-.02em}
.bbs-empty p{margin:0 0 16px;color:#8b8d92;font-size:11.5px;line-height:1.7}

.bbs-form,.bbs-post{background:#fff;border:1px solid var(--line);border-radius:24px;padding:26px}
.bbs-form h1,.bbs-post h1{margin:0 0 18px;font-size:27px;letter-spacing:-.04em;line-height:1.25}
.bbs-form label{font-size:11px;color:#777;display:block;margin:14px 0 7px}
.bbs-form input[type=text],.bbs-form textarea,.bbs-form select{width:100%;border:1px solid #d8d8d5;border-radius:12px;padding:12px;background:#fff;font-size:13px}
.bbs-form select{height:44px;padding:0 10px}
.bbs-form textarea{min-height:180px;resize:vertical;line-height:1.7}
.bbs-check{display:flex;gap:9px;align-items:center;margin:14px 0;font-size:11px;color:#666}
.bbs-post-head{display:flex;gap:10px;align-items:center;font-size:10px;color:#9a9ca0;margin-bottom:12px}
.bbs-post-content{font-size:14px;line-height:1.95;color:#3f4145;white-space:pre-wrap}
.bbs-replies{margin-top:14px}
.bbs-reply{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;margin-bottom:9px}
.bbs-reply-head{font-size:10px;color:#9a9ca0;margin-bottom:7px}
.bbs-reply-body{font-size:13px;line-height:1.8;white-space:pre-wrap;color:#3f4145}
.bbs-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.bbs-note{font-size:11px;color:#888;margin-top:10px}
.bbs-back{display:inline-block;font-size:11px;color:#777;margin-bottom:14px}
.bbs-back:hover{color:#111}
.bbs-pin{font-size:9px;font-weight:800;color:#c07800;background:#fdf6e8;border:1px solid #f0dfb8;border-radius:999px;padding:2px 7px;vertical-align:middle}
.bbs-mini{margin-left:10px;border:1px solid #e0e0dd;background:#fff;color:#8b8d92;border-radius:8px;padding:3px 9px;font-size:10px;cursor:pointer}
.bbs-mini:hover{border-color:#d4b3b3;color:#b42318}
.bbs-rules{background:#fff;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:14px;padding:14px 18px;margin-bottom:11px}
.bbs-rules b{font-size:11px;color:var(--accent)}
.bbs-rules ul{margin:7px 0 0;padding-left:17px;color:#7a7c81;font-size:11px;line-height:1.85}
@media(max-width:880px){.bbs-hero{grid-template-columns:1fr;gap:22px;padding:28px 24px}.bbs-hero h1{font-size:31px}.bbs-stats{gap:22px}}
@media(max-width:680px){.bbs-board{grid-template-columns:26px minmax(0,1fr) auto;gap:12px;padding:14px 16px 14px 18px}.bbs-board-go{display:none}.bbs-row{grid-template-columns:30px minmax(0,1fr);padding:14px 16px}.bbs-avatar{width:30px;height:30px;border-radius:9px}.bbs-right{grid-column:2;text-align:left;margin-top:6px}.bbs-head{flex-direction:column;align-items:flex-start}}
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
        CREATE TABLE IF NOT EXISTS bbs_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            reply_id INTEGER,
            actor_name TEXT NOT NULL DEFAULT '',
            seen INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE,
            FOREIGN KEY(post_id) REFERENCES bbs_posts(id) ON DELETE CASCADE,
            FOREIGN KEY(reply_id) REFERENCES bbs_replies(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_bbs_posts_board ON bbs_posts(board,id DESC);
        CREATE INDEX IF NOT EXISTS idx_bbs_replies_post ON bbs_replies(post_id,id ASC);
        CREATE INDEX IF NOT EXISTS idx_bbs_notify ON bbs_notifications(user_id,seen,id DESC);
        ''')
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(bbs_posts)").fetchall()}
        if "pinned" not in cols:
            conn.execute("ALTER TABLE bbs_posts ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")


def _identity(row, anonymous=False):
    if anonymous:
        return "匿名设计师"
    name = esc(row["display_name"])
    return f"{name} · 小飞侠" if row["role"] == community_core.ROLE_XIAOFEIXIA else name


def _page(body, title="小飞侠 BBS"):
    return HTMLResponse(site.page(site.nav() + f'<div class="shell bbs-shell">{body}</div>', title=title, extra=CSS), headers={"Cache-Control": "no-cache"})


LAST_ACTIVITY = ("COALESCE((SELECT MAX(r.created_at) FROM bbs_replies r "
                 "WHERE r.post_id=p.id), p.created_at)")


def unread_count(conn, user):
    if not user:
        return 0
    return int(conn.execute(
        "SELECT COUNT(*) c FROM bbs_notifications WHERE user_id=? AND seen=0",
        (user["id"],),
    ).fetchone()["c"])


def _avatar(label, accent=None):
    if accent:
        return f'<div class="bbs-avatar tag" style="background:{accent}">{label}</div>'
    return f'<div class="bbs-avatar">{label}</div>'


def _post_row(r):
    meta = BOARDS[r["board"]]
    return f'''<a class="bbs-row" href="/bbs/post/{r['id']}" style="--accent:{meta['accent']}">
{_avatar(meta['icon'])}
<div><div class="bbs-title">{'<span class="bbs-pin">置顶</span> ' if int(r['pinned'] or 0) else ''}{esc(r['title'])}</div>
<div class="bbs-meta"><span class="bbs-chip accent">{meta['name']}</span><span>{_identity(r, bool(r['anonymous']))}</span><span>{esc((r['created_at'] or '')[:10])}</span></div></div>
<div class="bbs-right"><div class="bbs-count">{int(r['reply_count'])} 回复<br>{int(r['views'])} 浏览</div></div></a>'''


def _bounty_row(r):
    meta = BOARDS["bounty"]
    state = "招募中" if r["status"] == "open" else "开发中"
    return f'''<a class="bbs-row" href="/bounties/{r['id']}" style="--accent:{meta['accent']}">
{_avatar(meta['icon'])}
<div><div class="bbs-title">{esc(r['title'])}</div>
<div class="bbs-meta"><span class="bbs-chip accent">悬赏</span><span>{esc(r['category'])}</span><span>{state}</span></div></div>
<div class="bbs-right"><div class="bbs-money">{int(r['reward'] or 0):,}</div><div class="bbs-count">{coin_core.COIN_NAME}</div></div></a>'''


def _empty(title, text, cta):
    return f'<div class="bbs-empty"><h3>{title}</h3><p>{text}</p>{cta}</div>'


@router.get("/bbs", response_class=HTMLResponse)
def bbs_home(request: Request, board: str = "all"):
    init_db()
    if board not in {"all", *BOARDS.keys()}:
        board = "all"

    with site.db() as conn:
        has_bounties = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bounties'"
        ).fetchone()
        live_bounties = conn.execute(
            "SELECT id,title,category,reward,status,created_at FROM bounties "
            "WHERE status IN ('open','in_progress') "
            "ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,id DESC LIMIT 30"
        ).fetchall() if has_bounties else []

        counts = {
            key: conn.execute(
                "SELECT COUNT(*) c FROM bbs_posts WHERE board=?", (key,)
            ).fetchone()["c"]
            for key in ("lab", "tree")
        }
        counts["bounty"] = len(live_bounties)
        members = conn.execute(
            "SELECT COUNT(*) c FROM community_users WHERE active=1"
        ).fetchone()["c"]
        replies = conn.execute("SELECT COUNT(*) c FROM bbs_replies").fetchone()["c"]

        where = "" if board == "all" else "WHERE p.board=?"
        params = () if board == "all" else (board,)
        # Ordered by last reply, not creation, so a thread someone is still
        # answering does not sink below newer but finished ones.
        posts = conn.execute(
            f'''SELECT p.*,u.display_name,u.role,
                (SELECT COUNT(*) FROM bbs_replies r WHERE r.post_id=p.id) AS reply_count,
                {LAST_ACTIVITY} AS last_activity
                FROM bbs_posts p JOIN community_users u ON u.id=p.user_id
                {where} ORDER BY p.pinned DESC, last_activity DESC LIMIT 40''', params
        ).fetchall() if board != "bounty" else []
        viewer = community_core.current_user(request)
        unread = unread_count(conn, viewer)

    cards = "".join(
        f'''<a class="bbs-board {'active' if board == key else ''}" href="/bbs?board={key}" style="--accent:{meta['accent']}">
<span class="ico">{meta['icon']}</span>
<div><h3>{meta['name']}</h3><p>{meta['desc']}</p></div>
<span class="bbs-board-count">{counts[key]} {meta['unit']}</span>
<span class="bbs-board-go">进入 →</span></a>'''
        for key, meta in BOARDS.items()
    )

    if board == "bounty":
        listing = "".join(_bounty_row(r) for r in live_bounties) or _empty(
            "悬赏墙上还没有进行中的任务",
            "把手头真实的重复劳动写成需求，设置飞侠币悬赏，让能做的人接走。",
            '<a class="btn" href="/bounties/new">发布悬赏</a>',
        )
        actions = '<div class="bbs-actions"><a class="btn" href="/bounties/new">发布悬赏</a><a class="btn secondary" href="/bounties">全部需求</a></div>'
        subtitle = "有明确交付目标的需求，直接在这里交易。"
        title = BOARDS["bounty"]["name"]
    elif board == "all":
        # The feed used to read bbs_posts alone, so a board with live bounties
        # but no posts rendered as an empty page.
        feed = [(r["last_activity"] or r["created_at"] or "", _post_row(r)) for r in posts]
        feed += [(r["created_at"] or "", _bounty_row(r)) for r in live_bounties]
        feed.sort(key=lambda item: item[0], reverse=True)
        listing = "".join(html for _, html in feed[:40]) or _empty(
            "社区还很安静",
            "发第一帖，或者把你手上的重复劳动写成一个悬赏需求。",
            '<a class="btn" href="/bbs/new?board=lab">+ 发帖</a> <a class="btn secondary" href="/bounties/new">发布悬赏</a>',
        )
        actions = '<div class="bbs-actions"><a class="btn" href="/bbs/new?board=lab">+ 发帖</a></div>'
        subtitle = "技术、交易和真实行业日常，都在这里发生。"
        title = "正在发生"
    else:
        listing = "".join(_post_row(r) for r in posts) or _empty(
            f"{BOARDS[board]['name']}还没有帖子",
            BOARDS[board]["desc"],
            f'<a class="btn" href="/bbs/new?board={board}">发第一帖</a>',
        )
        actions = f'<div class="bbs-actions"><a class="btn" href="/bbs/new?board={board}">+ 发帖</a></div>'
        subtitle = BOARDS[board]["desc"]
        title = BOARDS[board]["name"]

    rules = BOARDS[board]["rules"] if board in BOARDS else []
    rules_html = ""
    if rules:
        items = "".join(f"<li>{r}</li>" for r in rules)
        rules_html = (f'<div class="bbs-rules" style="--accent:{BOARDS[board]["accent"]}">'
                      f'<b>{BOARDS[board]["name"]}版规</b><ul>{items}</ul></div>')
    inbox = (f'<a class="btn secondary" href="/bbs/notifications">收件箱 · {unread} 条新回复</a>'
             if unread else '')
    actions = actions.replace('<div class="bbs-actions">', f'<div class="bbs-actions">{inbox}')

    body = f'''<section class="bbs-hero"><div><div class="bbs-kicker">DESIGNERS · TOOLS · COMMUNITY</div><h1>小飞侠 BBS</h1><p>不是官方论坛。这里是设计师自己讨论技术、发布悬赏和说真话的地方。</p></div>
<div class="bbs-stats"><div class="bbs-stat"><b>{counts['lab'] + counts['tree']}</b><span>帖子</span></div><div class="bbs-stat"><b>{replies}</b><span>回复</span></div><div class="bbs-stat"><b>{counts['bounty']}</b><span>进行中悬赏</span></div><div class="bbs-stat"><b>{members}</b><span>社区成员</span></div></div></section>
<div class="bbs-board-grid">{cards}</div>
<div class="bbs-head"><div><h2>{title}</h2><p>{subtitle}</p></div>{actions}</div>
{rules_html}<div class="bbs-list">{listing}</div>'''
    return _page(body)


@router.get("/bbs/new", response_class=HTMLResponse)
def new_post(request: Request, board: str = "lab"):
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login?next=/bbs/new", status_code=303)
    if board not in {"lab", "tree"}:
        board = "lab"
    opts = "".join(
        f'''<option value="{key}" {"selected" if board == key else ""}>{BOARDS[key]["icon"]} {BOARDS[key]["name"]}</option>'''
        for key in ("lab", "tree")
    )
    body = f'''<a class="bbs-back" href="/bbs?board={board}">← 返回 BBS</a><form class="bbs-form" method="post" action="/bbs/new"><h1>发一帖</h1>
<label>板块</label><select name="board">{opts}</select>
<label>标题</label><input type="text" name="title" maxlength="100" required placeholder="说清楚你想聊什么">
<label>正文</label><textarea name="content" required maxlength="{MAX_CONTENT}" placeholder="把问题、方法或者想说的话写下来"></textarea>
<label class="bbs-check"><input type="checkbox" name="anonymous" value="1"> 在设计院树洞匿名发布</label>
<div class="bbs-actions"><button class="btn" type="submit">发布</button><a class="btn secondary" href="/bbs?board={board}">取消</a></div></form>'''
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
    if len(title) > MAX_TITLE:
        raise HTTPException(400, f"标题最多 {MAX_TITLE} 字。")
    if len(content) > MAX_CONTENT:
        raise HTTPException(400, f"正文最多 {MAX_CONTENT} 字，当前 {len(content)} 字。")
    is_anon = 1 if board == "tree" and anonymous == "1" else 0
    stamp = community_core.now()
    with site.db() as conn:
        cur = conn.execute("INSERT INTO bbs_posts(board,user_id,title,content,anonymous,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (board, user["id"], title, content, is_anon, stamp, stamp))
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
        viewer = community_core.current_user(request)
        if viewer:
            conn.execute(
                "UPDATE bbs_notifications SET seen=1 WHERE user_id=? AND post_id=? AND seen=0",
                (viewer["id"], post_id),
            )
        replies = conn.execute("SELECT r.*,u.display_name,u.role FROM bbs_replies r JOIN community_users u ON u.id=r.user_id WHERE r.post_id=? ORDER BY r.id ASC", (post_id,)).fetchall()
    def _reply_block(r):
        mine = viewer and int(r["user_id"]) == int(viewer["id"])
        drop = (f'<form action="/bbs/reply/{r["id"]}/delete" method="post" style="display:inline" '
                f'onsubmit="return confirm(\'删除这条回复？\')"><button class="bbs-mini">删除</button></form>'
                if mine else "")
        return (f'<div class="bbs-reply"><div class="bbs-reply-head">{_identity(r, bool(r["anonymous"]))}'
                f' · {esc(r["created_at"][:16].replace("T", " "))}{drop}</div>'
                f'<div class="bbs-reply-body">{esc(r["content"])}</div></div>')

    reply_html = "".join(_reply_block(r) for r in replies) or '<div class="bbs-reply" style="color:#9a9ca0;font-size:12px">还没有回复，来说两句。</div>'
    user = viewer
    reply_form = '''<form class="bbs-form" method="post" action="/bbs/post/%d/reply"><label>回复</label><textarea name="content" required style="min-height:100px"></textarea>%s<div class="bbs-actions"><button class="btn" type="submit">回复</button></div></form>''' % (post_id, '<label class="bbs-check"><input type="checkbox" name="anonymous" value="1"> 匿名回复</label>' if row['board'] == 'tree' else '') if user else '<div class="bbs-note"><a href="/account/login">登录后参与回复 →</a></div>'
    meta = BOARDS[row['board']]
    own_actions = ""
    if viewer and int(row["user_id"]) == int(viewer["id"]):
        own_actions = (f'<div class="bbs-actions" style="margin-top:20px">'
                       f'<form action="/bbs/post/{post_id}/delete" method="post" '
                       f'onsubmit="return confirm(\'删除这一帖及其全部回复？\')">'
                       f'<button class="bbs-mini">删除我的帖子</button></form></div>')
    body = f'''<a class="bbs-back" href="/bbs?board={row['board']}">← {meta['name']}</a>
<article class="bbs-post" style="--accent:{meta['accent']}"><div class="bbs-post-head"><span class="bbs-chip accent">{meta['icon']} {meta['name']}</span><span>{_identity(row, bool(row['anonymous']))}</span><span>{esc((row['created_at'] or '')[:16].replace('T',' '))}</span><span>{int(row['views'])} 浏览</span></div>
<h1>{'<span class="bbs-pin">置顶</span> ' if int(row['pinned'] or 0) else ''}{esc(row['title'])}</h1><div class="bbs-post-content">{esc(row['content'])}</div>{own_actions}</article>
<div class="bbs-head"><div><h2>{len(replies)} 条回复</h2></div></div><div class="bbs-replies">{reply_html}</div>{reply_form}'''
    return _page(body, f"{row['title']} · 小飞侠 BBS")


@router.post("/bbs/post/{post_id}/reply")
def reply_post(request: Request, post_id: int, content: str = Form(...), anonymous: str = Form("")):
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    content = content.strip()
    if not content:
        raise HTTPException(400, "回复不能为空。")
    if len(content) > MAX_CONTENT:
        raise HTTPException(400, f"回复最多 {MAX_CONTENT} 字，当前 {len(content)} 字。")
    with site.db() as conn:
        post = conn.execute("SELECT board,user_id FROM bbs_posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(404, "帖子不存在。")
        is_anon = 1 if post["board"] == "tree" and anonymous == "1" else 0
        stamp = community_core.now()
        cur = conn.execute("INSERT INTO bbs_replies(post_id,user_id,content,anonymous,created_at) VALUES(?,?,?,?,?)", (post_id, user["id"], content, is_anon, stamp))
        # Tell the author someone answered — the single thing that brings people
        # back. Replying to your own thread notifies nobody.
        if int(post["user_id"]) != int(user["id"]):
            conn.execute(
                "INSERT INTO bbs_notifications(user_id,post_id,reply_id,actor_name,created_at) "
                "VALUES(?,?,?,?,?)",
                (post["user_id"], post_id, cur.lastrowid,
                 "匿名设计师" if is_anon else user["display_name"], stamp),
            )
    return RedirectResponse(f"/bbs/post/{post_id}", status_code=303)


@router.get("/bbs/notifications", response_class=HTMLResponse)
def notifications(request: Request):
    init_db()
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login?next=/bbs/notifications", status_code=303)
    with site.db() as conn:
        rows = conn.execute(
            '''SELECT n.*,p.title,p.board,r.content FROM bbs_notifications n
               JOIN bbs_posts p ON p.id=n.post_id
               LEFT JOIN bbs_replies r ON r.id=n.reply_id
               WHERE n.user_id=? ORDER BY n.id DESC LIMIT 50''', (user["id"],)
        ).fetchall()
        conn.execute("UPDATE bbs_notifications SET seen=1 WHERE user_id=?", (user["id"],))

    items = "".join(
        f'''<a class="bbs-row" href="/bbs/post/{n['post_id']}" style="--accent:{BOARDS[n['board']]['accent']}">
{_avatar(BOARDS[n['board']]['icon'])}
<div><div class="bbs-title">{esc(n['actor_name'])} 回复了「{esc(n['title'])}」</div>
<div class="bbs-meta">{'<span class="bbs-chip accent">未读</span>' if not int(n['seen'] or 0) else ''}<span>{esc((n['content'] or '')[:48])}</span><span>{esc((n['created_at'] or '')[:10])}</span></div></div>
<div class="bbs-right"><div class="bbs-count">查看 →</div></div></a>'''
        for n in rows
    ) or _empty("还没有新回复", "有人回复你的帖子时会出现在这里。", '<a class="btn secondary" href="/bbs">回到 BBS</a>')

    body = f'''<a class="bbs-back" href="/bbs">← 返回 BBS</a>
<div class="bbs-head"><div><h2>收件箱</h2><p>别人对你帖子的回复。</p></div></div>
<div class="bbs-list">{items}</div>'''
    return _page(body, "收件箱 · 小飞侠 BBS")


@router.post("/bbs/post/{post_id}/delete")
def delete_own_post(request: Request, post_id: int):
    """Authors can withdraw their own thread; admins use the moderation page."""
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    with site.db() as conn:
        post = conn.execute("SELECT user_id,board FROM bbs_posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(404, "帖子不存在。")
        if int(post["user_id"]) != int(user["id"]):
            raise HTTPException(403, "只能删除自己的帖子。")
        conn.execute("DELETE FROM bbs_posts WHERE id=?", (post_id,))
    return RedirectResponse(f"/bbs?board={post['board']}", status_code=303)


@router.post("/bbs/reply/{reply_id}/delete")
def delete_own_reply(request: Request, reply_id: int):
    user = community_core.current_user(request)
    if not user:
        return RedirectResponse("/account/login", status_code=303)
    with site.db() as conn:
        reply = conn.execute("SELECT user_id,post_id FROM bbs_replies WHERE id=?", (reply_id,)).fetchone()
        if not reply:
            raise HTTPException(404, "回复不存在。")
        if int(reply["user_id"]) != int(user["id"]):
            raise HTTPException(403, "只能删除自己的回复。")
        conn.execute("DELETE FROM bbs_replies WHERE id=?", (reply_id,))
    return RedirectResponse(f"/bbs/post/{reply['post_id']}", status_code=303)
