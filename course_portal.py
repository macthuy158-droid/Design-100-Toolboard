"""小飞侠设计课程 — course publishing and enrollment.

Schema is isolated from the tool/bounty migrations so the feature can evolve
independently. Courses are authored by 小飞侠 developers; lessons carry an
external video URL (no media hosting on this box).
"""

import re
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import community_core as core

router = APIRouter(prefix="/courses")

CATEGORIES = ["CAD", "Rhino", "SketchUp", "Revit", "UE", "Figma", "GIS", "参数化", "效率方法", "其他"]
LEVELS = ["入门", "进阶", "高级"]
STATUSES = {"draft": "草稿", "published": "已发布"}

CSS = r'''<style>
.cw{width:min(1180px,calc(100% - 36px));margin:42px auto 80px}.ch{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;margin-bottom:20px}.ch h1{margin:5px 0 8px;font-size:34px;letter-spacing:-.04em}.ey{font-size:10px;letter-spacing:.14em;color:#888;font-weight:800}.lead{font-size:12px;color:#777;line-height:1.8;max-width:680px}.actions,.filters{display:flex;gap:8px;flex-wrap:wrap}.filters{margin-bottom:18px}.pill{padding:8px 11px;border-radius:999px;border:1px solid #ddd;background:#fff;font-size:10px}.pill.on{background:#111;color:#fff;border-color:#111}.cgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.ccard{display:flex;flex-direction:column;background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:22px;color:#111;min-height:300px;transition:transform .2s,box-shadow .2s}.ccard:hover{transform:translateY(-4px);box-shadow:0 24px 70px rgba(0,0,0,.08)}.cover{width:64px;height:64px;border-radius:19px;background:#0b0c0d;color:#fff;display:grid;place-items:center;font-size:15px;font-weight:850;margin-bottom:20px}.ccard h2{font-size:21px;letter-spacing:-.03em;margin:0 0 9px;line-height:1.35}.sum{font-size:12px;color:#74767b;line-height:1.75;min-height:42px}.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:15px}.chip{background:#f2f2ef;border-radius:999px;padding:6px 9px;font-size:10px;color:#6d6f73}.cfoot{display:flex;justify-content:space-between;align-items:flex-end;margin-top:auto;padding-top:20px;border-top:1px solid #efefec}.money{font-size:19px;font-weight:800;letter-spacing:-.02em}.money small{display:block;font-size:9px;color:#9a9ca0;font-weight:500;margin-top:2px}.arrow{width:36px;height:36px;border-radius:50%;background:#111;color:#fff;display:grid;place-items:center;font-size:15px}.panel{background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:26px}.panel h2{margin:0 0 16px;font-size:20px;letter-spacing:-.025em}.layout{display:grid;grid-template-columns:1.4fr .8fr;gap:16px}.body{white-space:pre-wrap;font-size:13px;line-height:1.9;color:#494b50}.lesson{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:14px 0;border-top:1px solid #eee}.lesson:first-of-type{border-top:0}.lesson-idx{font-size:11px;color:#9b9da1;font-weight:800;font-variant-numeric:tabular-nums;width:26px;flex:none}.lesson-main{flex:1;min-width:0}.lesson-title{font-size:13px;font-weight:680}.lesson-meta{font-size:10px;color:#9a9ca0;margin-top:3px}.lock{font-size:10px;color:#a0a1a4}.free{font-size:9px;padding:4px 7px;border-radius:999px;background:#ebf4ec;color:#2f6f3b}.note{padding:12px 14px;border-radius:14px;background:#f3f3f0;color:#666;font-size:11px;line-height:1.7;margin-bottom:16px}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:10px 8px;border-bottom:1px solid #eee;text-align:left;font-size:11px}.empty{padding:28px;border:1px dashed #ddd;border-radius:16px;color:#888;text-align:center;font-size:12px;grid-column:1/-1}.status{display:inline-flex;padding:5px 8px;border-radius:999px;background:#ebf4ec;color:#2f6f3b;font-size:9px}.status.draft{background:#f3f3f0;color:#777}@media(max-width:950px){.cgrid{grid-template-columns:1fr 1fr}.layout{grid-template-columns:1fr}}@media(max-width:680px){.cgrid,.formgrid{grid-template-columns:1fr}.ch{align-items:flex-start;flex-direction:column}}
</style>'''


def page(body, title="设计课程 · 小飞侠设计100%"):
    return site.page(CSS + body, title)


def init_db():
    core.init_db()
    with site.db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS courses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          category TEXT NOT NULL DEFAULT '其他',
          level TEXT NOT NULL DEFAULT '入门',
          summary TEXT NOT NULL DEFAULT '',
          description TEXT NOT NULL DEFAULT '',
          cover_text TEXT NOT NULL DEFAULT '100',
          price_cents INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'draft',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS course_lessons(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          course_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          video_url TEXT NOT NULL DEFAULT '',
          duration_minutes INTEGER NOT NULL DEFAULT 0,
          sort_order INTEGER NOT NULL DEFAULT 0,
          free_preview INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS course_enrollments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          course_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(course_id,user_id),
          FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status,id DESC);
        CREATE INDEX IF NOT EXISTS idx_courses_user ON courses(user_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_course_lessons ON course_lessons(course_id,sort_order,id);
        CREATE INDEX IF NOT EXISTS idx_course_enrollments ON course_enrollments(user_id,id DESC);
        ''')


def user(request):
    return core.current_user(request)


def login_redirect(path):
    return RedirectResponse('/account/login?' + urlencode({'next': path}), 303)


def money(cents):
    cents = int(cents or 0)
    return '免费' if cents <= 0 else f'¥{cents/100:,.0f}'


def safe_url(value):
    value = value.strip()
    if not value:
        return ''
    if not re.match(r'^https?://', value, re.I):
        raise HTTPException(400, '视频链接必须以 http:// 或 https:// 开头。')
    return value[:1200]


def can_learn(conn, u, course):
    """小飞侠 全部免费；免费课登录即可；付费课需要报名记录。"""
    if not u:
        return False
    if int(course['user_id']) == int(u['id']) or u['role'] == core.ROLE_XIAOFEIXIA:
        return True
    if int(course['price_cents'] or 0) <= 0:
        return True
    return bool(conn.execute(
        'SELECT 1 FROM course_enrollments WHERE course_id=? AND user_id=?',
        (course['id'], u['id']),
    ).fetchone())


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
def list_courses(request: Request, category: str = '', level: str = ''):
    init_db()
    where = ["c.status='published'"]
    params = []
    if category in CATEGORIES:
        where.append('c.category=?')
        params.append(category)
    if level in LEVELS:
        where.append('c.level=?')
        params.append(level)
    clause = 'WHERE ' + ' AND '.join(where)
    with site.db() as conn:
        rows = conn.execute(f'''SELECT c.*,u.display_name,
            (SELECT COUNT(*) FROM course_lessons l WHERE l.course_id=c.id) lesson_count,
            (SELECT COALESCE(SUM(duration_minutes),0) FROM course_lessons l WHERE l.course_id=c.id) minutes,
            (SELECT COUNT(*) FROM course_enrollments e WHERE e.course_id=c.id) student_count
            FROM courses c JOIN community_users u ON u.id=c.user_id {clause}
            ORDER BY c.id DESC''', params).fetchall()

    cf = '<a class="pill {}" href="/courses?{}">全部分类</a>'.format('on' if category not in CATEGORIES else '', urlencode({'level': level})) + ''.join(
        f'<a class="pill {"on" if category == c else ""}" href="/courses?{urlencode({"category": c, "level": level})}">{site.esc(c)}</a>' for c in CATEGORIES)
    lf = '<a class="pill {}" href="/courses?{}">全部难度</a>'.format('on' if level not in LEVELS else '', urlencode({'category': category})) + ''.join(
        f'<a class="pill {"on" if level == v else ""}" href="/courses?{urlencode({"category": category, "level": v})}">{site.esc(v)}</a>' for v in LEVELS)

    cards = []
    for c in rows:
        cards.append(f'''<a class="ccard" href="/courses/{c['id']}"><div class="cover">{site.esc(c['cover_text'])}</div>
<h2>{site.esc(c['title'])}</h2><div class="sum">{site.esc(c['summary'])}</div>
<div class="chips"><span class="chip">{site.esc(c['category'])}</span><span class="chip">{site.esc(c['level'])}</span><span class="chip">{int(c['lesson_count'] or 0)} 节 · {int(c['minutes'] or 0)} 分钟</span></div>
<div class="cfoot"><div class="money">{money(c['price_cents'])}<small>{site.esc(c['display_name'])} · {int(c['student_count'] or 0)} 人学过</small></div><div class="arrow">↗</div></div></a>''')

    u = user(request)
    mine = '<a class="btn secondary" href="/courses/mine">我的课程</a>' if u else ''
    primary = ('<a class="btn" href="/courses/new">发布课程</a>' if u and u['role'] == core.ROLE_XIAOFEIXIA
               else ('' if u else '<a class="btn" href="/account/login?next=/courses">登录</a>'))
    body = f'''<div class="cw"><div class="ch"><div><div class="ey">DESIGN 100% · COURSES</div><h1>小飞侠设计课程</h1><div class="lead">把工具背后的方法讲清楚。小飞侠把自己的设计流程、插件用法与参数化经验做成课程，帮更多设计师少走弯路。</div></div><div class="actions">{mine}{primary}</div></div>
<div class="filters">{cf}</div><div class="filters">{lf}</div>
<div class="cgrid">{''.join(cards) if cards else '<div class="empty">暂时还没有已发布的课程。</div>'}</div></div>'''
    return HTMLResponse(page(body))


@router.get('/new', response_class=HTMLResponse)
def new_course(request: Request):
    init_db()
    u = user(request)
    if not u:
        return login_redirect('/courses/new')
    if u['role'] != core.ROLE_XIAOFEIXIA:
        raise HTTPException(403, '只有小飞侠开发者可以发布课程。')
    cats = ''.join(f'<option value="{site.esc(c)}">{site.esc(c)}</option>' for c in CATEGORIES)
    lvls = ''.join(f'<option value="{site.esc(v)}">{site.esc(v)}</option>' for v in LEVELS)
    body = f'''<div class="cw"><div class="ch"><div><div class="ey">NEW COURSE</div><h1>发布课程</h1><div class="lead">先建立课程框架，创建后再逐节添加课时与视频链接。确认内容完整后再发布上架。</div></div><a class="btn secondary" href="/courses">返回课程列表</a></div>
<div class="panel"><div class="note">课程创建后为草稿状态，只有你自己可见。添加完课时后点击「发布上架」才会出现在课程列表。</div>
<form action="/courses/new" method="post"><div class="field"><label>课程名称</label><input name="title" maxlength="120" required></div>
<div class="formgrid"><div class="field"><label>分类</label><select name="category">{cats}</select></div><div class="field"><label>难度</label><select name="level">{lvls}</select></div>
<div class="field"><label>封面文字（2-4 字）</label><input name="cover_text" maxlength="6" value="100"></div><div class="field"><label>价格（元，0 为免费）</label><input name="price_yuan" type="number" min="0" max="100000" step="1" value="0"></div></div>
<div class="field"><label>一句话简介</label><input name="summary" maxlength="200" required></div>
<div class="field"><label>课程详细说明</label><textarea name="description" rows="10" maxlength="10000" required></textarea></div>
<button class="btn">创建课程</button></form></div></div>'''
    return HTMLResponse(page(body, '发布课程 · 小飞侠设计100%'))


@router.post('/new')
def create_course(request: Request, title: str = Form(...), category: str = Form('其他'), level: str = Form('入门'),
                  summary: str = Form(''), description: str = Form(...), cover_text: str = Form('100'),
                  price_yuan: float = Form(0)):
    init_db()
    u = user(request)
    if not u:
        return login_redirect('/courses/new')
    if u['role'] != core.ROLE_XIAOFEIXIA:
        raise HTTPException(403, '只有小飞侠开发者可以发布课程。')
    title = title.strip()
    summary = summary.strip()
    description = description.strip()
    if not title or len(title) > 120:
        raise HTTPException(400, '课程名称不能为空，且最多 120 字。')
    if not description or len(description) > 10000:
        raise HTTPException(400, '课程说明不能为空，且最多 10000 字。')
    if category not in CATEGORIES:
        raise HTTPException(400, '请选择有效分类。')
    if level not in LEVELS:
        raise HTTPException(400, '请选择有效难度。')
    if price_yuan < 0 or price_yuan > 100000:
        raise HTTPException(400, '价格需在 0—100,000 元之间。')
    stamp = core.now()
    with site.db() as conn:
        cur = conn.execute('''INSERT INTO courses(user_id,title,category,level,summary,description,cover_text,price_cents,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,'draft',?,?)''',
            (u['id'], title, category, level, summary[:200], description, (cover_text.strip() or '100')[:6],
             int(round(price_yuan * 100)), stamp, stamp))
        cid = cur.lastrowid
    return RedirectResponse(f'/courses/{cid}', 303)


@router.get('/mine', response_class=HTMLResponse)
def mine(request: Request):
    init_db()
    u = user(request)
    if not u:
        return login_redirect('/courses/mine')
    with site.db() as conn:
        own = conn.execute('''SELECT c.*,
            (SELECT COUNT(*) FROM course_lessons l WHERE l.course_id=c.id) lesson_count,
            (SELECT COUNT(*) FROM course_enrollments e WHERE e.course_id=c.id) student_count
            FROM courses c WHERE c.user_id=? ORDER BY c.id DESC''', (u['id'],)).fetchall() if u['role'] == core.ROLE_XIAOFEIXIA else []
        learning = conn.execute('''SELECT c.id,c.title,c.category,c.level,u.display_name
            FROM course_enrollments e JOIN courses c ON c.id=e.course_id
            JOIN community_users u ON u.id=c.user_id WHERE e.user_id=? ORDER BY e.id DESC''', (u['id'],)).fetchall()

    learn_rows = ''.join(
        f'<tr><td><a href="/courses/{c["id"]}">{site.esc(c["title"])}</a></td><td>{site.esc(c["category"])}</td><td>{site.esc(c["level"])}</td><td>{site.esc(c["display_name"])}</td></tr>'
        for c in learning) or '<tr><td colspan="4">还没有报名任何课程</td></tr>'

    teach = ''
    if u['role'] == core.ROLE_XIAOFEIXIA:
        rows = ''.join(
            f'<tr><td><a href="/courses/{c["id"]}">{site.esc(c["title"])}</a></td><td>{site.esc(STATUSES.get(c["status"], c["status"]))}</td><td>{int(c["lesson_count"] or 0)}</td><td>{int(c["student_count"] or 0)}</td><td>{money(c["price_cents"])}</td></tr>'
            for c in own) or '<tr><td colspan="5">还没有创建课程</td></tr>'
        teach = f'<div class="panel" style="margin-bottom:16px"><h2>我发布的课程</h2><table class="table"><thead><tr><th>课程</th><th>状态</th><th>课时</th><th>学员</th><th>价格</th></tr></thead><tbody>{rows}</tbody></table></div>'

    primary = '<a class="btn" href="/courses/new">发布课程</a>' if u['role'] == core.ROLE_XIAOFEIXIA else ''
    body = f'''<div class="cw"><div class="ch"><div><div class="ey">MY COURSES</div><h1>我的课程</h1></div><div class="actions">{primary}<a class="btn secondary" href="/courses">课程列表</a></div></div>
{teach}<div class="panel"><h2>我在学的课程</h2><table class="table"><thead><tr><th>课程</th><th>分类</th><th>难度</th><th>讲师</th></tr></thead><tbody>{learn_rows}</tbody></table></div></div>'''
    return HTMLResponse(page(body, '我的课程 · 小飞侠设计100%'))


@router.get('/{course_id}', response_class=HTMLResponse)
def detail(request: Request, course_id: int):
    init_db()
    u = user(request)
    with site.db() as conn:
        c = conn.execute('SELECT c.*,u.display_name FROM courses c JOIN community_users u ON u.id=c.user_id WHERE c.id=?', (course_id,)).fetchone()
        if not c:
            raise HTTPException(404, '课程不存在。')
        owner = bool(u and int(u['id']) == int(c['user_id']))
        if c['status'] != 'published' and not owner:
            raise HTTPException(404, '课程不存在。')
        lessons = conn.execute('SELECT * FROM course_lessons WHERE course_id=? ORDER BY sort_order,id', (course_id,)).fetchall()
        students = conn.execute('SELECT COUNT(*) n FROM course_enrollments WHERE course_id=?', (course_id,)).fetchone()['n']
        unlocked = can_learn(conn, u, c)
        enrolled = bool(u and conn.execute('SELECT 1 FROM course_enrollments WHERE course_id=? AND user_id=?', (course_id, u['id'])).fetchone())

    minutes = sum(int(l['duration_minutes'] or 0) for l in lessons)
    price = int(c['price_cents'] or 0)

    items = []
    for i, l in enumerate(lessons, 1):
        open_now = unlocked or int(l['free_preview'] or 0) == 1
        if open_now and l['video_url']:
            right = f'<a class="btn secondary" style="height:36px" href="{site.esc(l["video_url"])}" target="_blank" rel="noopener noreferrer">观看 ↗</a>'
        elif open_now:
            right = '<span class="lock">视频待上传</span>'
        else:
            right = '<span class="lock">🔒 报名后解锁</span>'
        tag = '<span class="free">试看</span>' if int(l['free_preview'] or 0) == 1 and not unlocked else ''
        drop = f'<form action="/courses/{course_id}/lessons/{l["id"]}/delete" method="post" style="display:inline"><button class="btn secondary" style="height:36px">删除</button></form>' if owner else ''
        items.append(f'''<div class="lesson"><span class="lesson-idx">{i:02d}</span><div class="lesson-main"><div class="lesson-title">{site.esc(l['title'])} {tag}</div><div class="lesson-meta">{int(l['duration_minutes'] or 0)} 分钟</div></div><div class="actions">{right}{drop}</div></div>''')
    lesson_html = ''.join(items) or '<div class="empty">课程还没有添加课时。</div>'

    add_form = f'''<div class="panel" style="margin-top:16px"><h2>添加课时</h2><form action="/courses/{course_id}/lessons" method="post">
<div class="field"><label>课时标题</label><input name="title" maxlength="120" required></div>
<div class="field"><label>视频链接（可选，支持任意视频平台地址）</label><input name="video_url" placeholder="https://..."></div>
<div class="formgrid"><div class="field"><label>时长（分钟）</label><input name="duration_minutes" type="number" min="0" max="600" value="10"></div>
<div class="field"><label>是否允许试看</label><select name="free_preview"><option value="0">否</option><option value="1">是（未报名也能看）</option></select></div></div>
<button class="btn">添加课时</button></form></div>''' if owner else ''

    buttons = []
    if owner:
        nxt = 'published' if c['status'] == 'draft' else 'draft'
        label = '发布上架' if c['status'] == 'draft' else '下架为草稿'
        buttons.append(f'<form action="/courses/{course_id}/status" method="post"><input type="hidden" name="status" value="{nxt}"><button class="btn">{label}</button></form>')
    elif not u:
        buttons.append(f'<a class="btn" href="/account/login?next=/courses/{course_id}">登录后学习</a>')
    elif enrolled or (u['role'] == core.ROLE_XIAOFEIXIA):
        buttons.append('<span class="btn secondary">已可学习</span>')
    elif price <= 0:
        buttons.append(f'<form action="/courses/{course_id}/enroll" method="post"><button class="btn">免费报名</button></form>')
    else:
        buttons.append('<span class="btn secondary">支付接入后开放购买</span>')

    price_note = ('小飞侠：院内账号免费学习。' if u and u['role'] == core.ROLE_XIAOFEIXIA
                  else ('免费课程，登录后即可报名学习。' if price <= 0 else '付费课程，统一支付接入后开放购买。'))
    draft_note = '<div class="note">当前为草稿状态，只有你自己能看到这个页面。</div>' if owner and c['status'] == 'draft' else ''
    status_badge = f'<span class="status {"draft" if c["status"] == "draft" else ""}">{site.esc(STATUSES.get(c["status"], c["status"]))}</span>' if owner else ''

    side = f'''<div class="panel"><h3 style="margin-top:0">课程信息</h3><div class="money" style="font-size:26px">{money(price)}</div>
<div class="lesson-meta" style="margin-top:14px;line-height:2">讲师：{site.esc(c['display_name'])}<br>分类：{site.esc(c['category'])}<br>难度：{site.esc(c['level'])}<br>课时：{len(lessons)} 节 · {minutes} 分钟<br>学员：{students} 人</div>
<div class="actions" style="margin-top:16px">{''.join(buttons)}</div></div><div class="note" style="margin-top:16px">{price_note}</div>'''

    body = f'''<div class="cw"><div class="ch"><div><div class="ey">COURSE #{c['id']}</div><h1>{site.esc(c['title'])}</h1><div class="actions"><span class="chip">{site.esc(c['category'])}</span><span class="chip">{site.esc(c['level'])}</span>{status_badge}</div></div><a class="btn secondary" href="/courses">返回课程列表</a></div>
{draft_note}<div class="layout"><div><div class="panel"><h2>课程介绍</h2><div class="body">{site.esc(c['description'])}</div></div>
<div class="panel" style="margin-top:16px"><h2>课程目录 <span class="lesson-meta">{len(lessons)} 节</span></h2>{lesson_html}</div>{add_form}</div>
<div>{side}</div></div></div>'''
    return HTMLResponse(page(body, f"{c['title']} · 设计课程"))


@router.post('/{course_id}/lessons')
def add_lesson(request: Request, course_id: int, title: str = Form(...), video_url: str = Form(''),
               duration_minutes: int = Form(0), free_preview: int = Form(0)):
    init_db()
    u = user(request)
    if not u:
        return login_redirect(f'/courses/{course_id}')
    title = title.strip()
    if not title or len(title) > 120:
        raise HTTPException(400, '课时标题不能为空，且最多 120 字。')
    if duration_minutes < 0 or duration_minutes > 600:
        raise HTTPException(400, '时长需在 0—600 分钟之间。')
    stamp = core.now()
    with site.db() as conn:
        c = conn.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
        if not c:
            raise HTTPException(404, '课程不存在。')
        if int(c['user_id']) != int(u['id']):
            raise HTTPException(403, '只有课程作者可以添加课时。')
        nxt = conn.execute('SELECT COALESCE(MAX(sort_order),0)+1 n FROM course_lessons WHERE course_id=?', (course_id,)).fetchone()['n']
        conn.execute('INSERT INTO course_lessons(course_id,title,video_url,duration_minutes,sort_order,free_preview,created_at) VALUES(?,?,?,?,?,?,?)',
                     (course_id, title, safe_url(video_url), duration_minutes, nxt, 1 if int(free_preview or 0) == 1 else 0, stamp))
        conn.execute('UPDATE courses SET updated_at=? WHERE id=?', (stamp, course_id))
    return RedirectResponse(f'/courses/{course_id}', 303)


@router.post('/{course_id}/lessons/{lesson_id}/delete')
def delete_lesson(request: Request, course_id: int, lesson_id: int):
    init_db()
    u = user(request)
    if not u:
        return login_redirect(f'/courses/{course_id}')
    with site.db() as conn:
        c = conn.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
        if not c:
            raise HTTPException(404, '课程不存在。')
        if int(c['user_id']) != int(u['id']):
            raise HTTPException(403, '只有课程作者可以删除课时。')
        conn.execute('DELETE FROM course_lessons WHERE id=? AND course_id=?', (lesson_id, course_id))
        conn.execute('UPDATE courses SET updated_at=? WHERE id=?', (core.now(), course_id))
    return RedirectResponse(f'/courses/{course_id}', 303)


@router.post('/{course_id}/status')
def set_status(request: Request, course_id: int, status: str = Form(...)):
    init_db()
    u = user(request)
    if not u:
        return login_redirect(f'/courses/{course_id}')
    if status not in STATUSES:
        raise HTTPException(400, '状态不正确。')
    with site.db() as conn:
        c = conn.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
        if not c:
            raise HTTPException(404, '课程不存在。')
        if int(c['user_id']) != int(u['id']):
            raise HTTPException(403, '只有课程作者可以修改状态。')
        if status == 'published':
            n = conn.execute('SELECT COUNT(*) n FROM course_lessons WHERE course_id=?', (course_id,)).fetchone()['n']
            if not n:
                raise HTTPException(409, '至少添加一节课时后才能发布。')
        conn.execute('UPDATE courses SET status=?,updated_at=? WHERE id=?', (status, core.now(), course_id))
    return RedirectResponse(f'/courses/{course_id}', 303)


@router.post('/{course_id}/enroll')
def enroll(request: Request, course_id: int):
    init_db()
    u = user(request)
    if not u:
        return login_redirect(f'/courses/{course_id}')
    with site.db() as conn:
        c = conn.execute('SELECT * FROM courses WHERE id=?', (course_id,)).fetchone()
        if not c:
            raise HTTPException(404, '课程不存在。')
        if c['status'] != 'published':
            raise HTTPException(409, '课程尚未发布。')
        if int(c['user_id']) == int(u['id']):
            raise HTTPException(400, '不能报名自己发布的课程。')
        if int(c['price_cents'] or 0) > 0 and u['role'] != core.ROLE_XIAOFEIXIA:
            raise HTTPException(409, '付费课程的支付通道尚未接入，暂时无法报名。')
        conn.execute('INSERT OR IGNORE INTO course_enrollments(course_id,user_id,created_at) VALUES(?,?,?)',
                     (course_id, u['id'], core.now()))
    return RedirectResponse(f'/courses/{course_id}', 303)
