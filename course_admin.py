"""Administrator surface for 小飞侠设计课程.

Course authoring lives entirely inside /manage so the public site never
carries editing affordances. course_portal owns the schema and the reader
facing pages; this module owns creation, lesson upkeep and shelf state.
"""

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import admin_portal
import app_v2 as site
import community_core as core
import course_portal as courses

app = FastAPI(title="Course Admin", docs_url=None, redoc_url=None, openapi_url=None)

CSS = '''<style>
.wrap{max-width:1100px;margin:34px auto;padding:0 20px 70px}.top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:24px}.top h1{margin:5px 0 0;font-size:30px}.nav{display:flex;gap:8px;flex-wrap:wrap}.card{background:#fff;border:1px solid #e6e6e3;border-radius:22px;padding:22px;margin-bottom:14px}.card h2{margin:0 0 16px;font-size:19px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.badge{display:inline-flex;padding:5px 9px;border-radius:999px;background:#eee;font-size:9px}.ok{background:#e2f3e5}.draft{background:#f1f1ee;color:#777}.actions{display:flex;gap:7px;flex-wrap:wrap;align-items:center}.mini{height:32px!important;padding:0 10px!important;font-size:10px!important}.muted{font-size:11px;color:#888;line-height:1.7}.summary{display:flex;gap:10px;margin:16px 0 22px;flex-wrap:wrap}.stat{background:#f5f5f2;border-radius:14px;padding:13px 16px;min-width:110px}.stat b{display:block;font-size:20px}.stat span{font-size:9px;color:#888}.table-wrap{overflow-x:auto}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;border-bottom:1px solid #eee;padding:10px 8px;font-size:11px}.table th{color:#888}.empty{padding:40px 20px;text-align:center;color:#888;font-size:12px}.lesson{display:grid;grid-template-columns:30px 1fr auto;gap:12px;align-items:center;padding:13px 0;border-top:1px solid #eee}.lesson:first-of-type{border-top:0}.lesson-idx{font-size:11px;color:#9b9da1;font-weight:800;font-variant-numeric:tabular-nums}.lesson-title{font-size:13px;font-weight:680}.lesson-meta{font-size:10px;color:#9a9ca0;margin-top:3px;word-break:break-all}.free{font-size:9px;padding:3px 7px;border-radius:999px;background:#ebf4ec;color:#2f6f3b}.note{padding:12px 14px;border-radius:12px;background:#f6f6f3;color:#666;font-size:11px;line-height:1.7;margin-bottom:16px}@media(max-width:760px){.top{align-items:flex-start;flex-direction:column}.grid{grid-template-columns:1fr}.lesson{grid-template-columns:1fr}}
</style>'''


def require_admin(request):
    admin_portal.require_admin(request)


def page(body, title="课程管理 · 小飞侠设计100%"):
    return site.page(CSS + body, title)


def admin_nav(active=""):
    return f'''<div class="nav">
    <a class="btn secondary" href="/manage/">后台首页</a>
    <a class="btn secondary" href="/manage/community/review">投稿审核</a>
    <a class="btn secondary" href="/manage/tools/">工具管理</a>
    <a class="btn secondary" href="/manage/community/users">用户管理</a>
    <a class="btn {'secondary' if active != 'courses' else ''}" href="/manage/courses/">课程管理</a>
    </div>'''


def _load(conn, course_id):
    row = conn.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
    if not row:
        raise HTTPException(404, "课程不存在。")
    return row


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    require_admin(request)
    courses.init_db()
    with site.db() as conn:
        rows = conn.execute(courses._stats_sql('')).fetchall()
    published = sum(1 for c in rows if c['status'] == 'published')
    students = sum(int(c['student_count'] or 0) for c in rows)

    body_rows = ''.join(
        f'''<tr><td><a href="/manage/courses/{c['id']}">{site.esc(c['title'])}</a></td>
<td><span class="badge {'ok' if c['status'] == 'published' else 'draft'}">{site.esc(courses.STATUSES.get(c['status'], c['status']))}</span></td>
<td>{site.esc(c['category'])} · {site.esc(c['level'])}</td><td>{site.esc(c['instructor'])}</td>
<td>{int(c['lesson_count'] or 0)} 节 · {int(c['minutes'] or 0)} 分钟</td><td>{int(c['student_count'] or 0)}</td>
<td>{courses.money(c['price_cents'])}</td></tr>'''
        for c in rows)
    table = (f'<div class="table-wrap"><table class="table"><thead><tr><th>课程</th><th>状态</th><th>分类</th><th>讲师</th><th>课时</th><th>学员</th><th>价格</th></tr></thead><tbody>{body_rows}</tbody></table></div>'
             if rows else '<div class="empty">还没有创建课程。点击右上角「新建课程」开始。</div>')

    body = f'''<div class="wrap"><div class="top"><div><div class="eyebrow">DESIGN 100 · COURSE ADMIN</div><h1>课程管理</h1><div class="muted">官方设计课程的创建、课时维护与上下架。</div></div><a class="btn" href="/manage/courses/new">新建课程</a></div>
{admin_nav('courses')}
<div class="summary"><div class="stat"><b>{len(rows)}</b><span>课程总数</span></div><div class="stat"><b>{published}</b><span>已发布</span></div><div class="stat"><b>{students}</b><span>累计报名</span></div></div>
<div class="card">{table}</div></div>'''
    return HTMLResponse(page(body))


@app.get('/new', response_class=HTMLResponse)
def new_course(request: Request):
    require_admin(request)
    courses.init_db()
    cats = ''.join(f'<option value="{site.esc(c)}">{site.esc(c)}</option>' for c in courses.CATEGORIES)
    lvls = ''.join(f'<option value="{site.esc(v)}">{site.esc(v)}</option>' for v in courses.LEVELS)
    body = f'''<div class="wrap"><div class="top"><div><div class="eyebrow">NEW COURSE</div><h1>新建课程</h1><div class="muted">先建立课程框架，创建后再逐节添加课时。</div></div><a class="btn secondary" href="/manage/courses/">返回列表</a></div>
{admin_nav('courses')}
<div class="card"><div class="note">课程创建后为草稿，只有后台可见。添加课时后再发布上架。</div>
<form action="/manage/courses/new" method="post"><div class="field"><label>课程名称</label><input name="title" maxlength="120" required></div>
<div class="grid"><div class="field"><label>分类</label><select name="category">{cats}</select></div><div class="field"><label>难度</label><select name="level">{lvls}</select></div>
<div class="field"><label>讲师署名</label><input name="instructor" maxlength="40" value="{site.esc(courses.DEFAULT_INSTRUCTOR)}"></div><div class="field"><label>封面文字（2-4 字）</label><input name="cover_text" maxlength="6" value="100"></div></div>
<div class="field"><label>价格（元，0 为免费）</label><input name="price_yuan" type="number" min="0" max="100000" step="1" value="0"></div>
<div class="field"><label>一句话简介</label><input name="summary" maxlength="200" required></div>
<div class="field"><label>课程详细说明</label><textarea name="description" rows="10" maxlength="10000" required></textarea></div>
<button class="btn">创建课程</button></form></div></div>'''
    return HTMLResponse(page(body, "新建课程 · 小飞侠设计100%"))


@app.post('/new')
def create_course(request: Request, title: str = Form(...), category: str = Form('其他'), level: str = Form('入门'),
                  summary: str = Form(''), description: str = Form(...), cover_text: str = Form('100'),
                  instructor: str = Form(''), price_yuan: float = Form(0)):
    require_admin(request)
    courses.init_db()
    title = title.strip()
    description = description.strip()
    if not title or len(title) > 120:
        raise HTTPException(400, '课程名称不能为空，且最多 120 字。')
    if not description or len(description) > 10000:
        raise HTTPException(400, '课程说明不能为空，且最多 10000 字。')
    if category not in courses.CATEGORIES:
        raise HTTPException(400, '请选择有效分类。')
    if level not in courses.LEVELS:
        raise HTTPException(400, '请选择有效难度。')
    if price_yuan < 0 or price_yuan > 100000:
        raise HTTPException(400, '价格需在 0—100,000 元之间。')
    stamp = core.now()
    with site.db() as conn:
        cur = conn.execute('''INSERT INTO courses(instructor,title,category,level,summary,description,cover_text,price_cents,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,'draft',?,?)''',
            ((instructor.strip() or courses.DEFAULT_INSTRUCTOR)[:40], title, category, level,
             summary.strip()[:200], description, (cover_text.strip() or '100')[:6],
             int(round(price_yuan * 100)), stamp, stamp))
        cid = cur.lastrowid
    return RedirectResponse(f'/manage/courses/{cid}', 303)


@app.get('/{course_id}', response_class=HTMLResponse)
def edit_course(request: Request, course_id: int):
    require_admin(request)
    courses.init_db()
    with site.db() as conn:
        c = _load(conn, course_id)
        lessons = conn.execute('SELECT * FROM course_lessons WHERE course_id=? ORDER BY sort_order,id', (course_id,)).fetchall()
        students = conn.execute('SELECT COUNT(*) n FROM course_enrollments WHERE course_id=?', (course_id,)).fetchone()['n']

    cats = ''.join(f'<option value="{site.esc(v)}" {"selected" if v == c["category"] else ""}>{site.esc(v)}</option>' for v in courses.CATEGORIES)
    lvls = ''.join(f'<option value="{site.esc(v)}" {"selected" if v == c["level"] else ""}>{site.esc(v)}</option>' for v in courses.LEVELS)

    items = ''.join(f'''<div class="lesson"><span class="lesson-idx">{i:02d}</span>
<div><div class="lesson-title">{site.esc(l['title'])} {'<span class="free">试看</span>' if int(l['free_preview'] or 0) == 1 else ''}</div>
<div class="lesson-meta">{int(l['duration_minutes'] or 0)} 分钟{' · ' + site.esc(l['video_url']) if l['video_url'] else ' · 视频待上传'}</div></div>
<form action="/manage/courses/{course_id}/lessons/{l['id']}/delete" method="post"><button class="btn secondary mini">删除</button></form></div>'''
        for i, l in enumerate(lessons, 1)) or '<div class="empty">还没有课时。</div>'

    nxt = 'published' if c['status'] == 'draft' else 'draft'
    label = '发布上架' if c['status'] == 'draft' else '下架为草稿'
    minutes = sum(int(l['duration_minutes'] or 0) for l in lessons)
    publish_hint = '<div class="note">至少添加一节课时后才能发布上架。</div>' if c['status'] == 'draft' and not lessons else ''
    preview = f'<a class="btn secondary" href="/courses/{course_id}" target="_blank" rel="noopener">预览公开页 ↗</a>'

    body = f'''<div class="wrap"><div class="top"><div><div class="eyebrow">COURSE #{c['id']}</div><h1>{site.esc(c['title'])}</h1>
<div class="actions" style="margin-top:9px"><span class="badge {'ok' if c['status'] == 'published' else 'draft'}">{site.esc(courses.STATUSES.get(c['status'], c['status']))}</span><span class="muted">{len(lessons)} 节 · {minutes} 分钟 · {students} 人报名</span></div></div>
<div class="actions">{preview}<form action="/manage/courses/{course_id}/status" method="post"><input type="hidden" name="status" value="{nxt}"><button class="btn">{label}</button></form></div></div>
{admin_nav('courses')}{publish_hint}
<div class="card"><h2>课程资料</h2><form action="/manage/courses/{course_id}" method="post">
<div class="field"><label>课程名称</label><input name="title" maxlength="120" value="{site.esc(c['title'])}" required></div>
<div class="grid"><div class="field"><label>分类</label><select name="category">{cats}</select></div><div class="field"><label>难度</label><select name="level">{lvls}</select></div>
<div class="field"><label>讲师署名</label><input name="instructor" maxlength="40" value="{site.esc(c['instructor'])}"></div><div class="field"><label>封面文字</label><input name="cover_text" maxlength="6" value="{site.esc(c['cover_text'])}"></div></div>
<div class="field"><label>价格（元，0 为免费）</label><input name="price_yuan" type="number" min="0" max="100000" step="1" value="{int(c['price_cents'] or 0)/100:.0f}"></div>
<div class="field"><label>一句话简介</label><input name="summary" maxlength="200" value="{site.esc(c['summary'])}" required></div>
<div class="field"><label>课程详细说明</label><textarea name="description" rows="10" maxlength="10000" required>{site.esc(c['description'])}</textarea></div>
<button class="btn">保存资料</button></form></div>
<div class="card"><h2>课程目录 <span class="muted">{len(lessons)} 节</span></h2>{items}</div>
<div class="card"><h2>添加课时</h2><form action="/manage/courses/{course_id}/lessons" method="post">
<div class="field"><label>课时标题</label><input name="title" maxlength="120" required></div>
<div class="field"><label>视频链接（可选）</label><input name="video_url" placeholder="https://..."></div>
<div class="grid"><div class="field"><label>时长（分钟）</label><input name="duration_minutes" type="number" min="0" max="600" value="10"></div>
<div class="field"><label>是否允许试看</label><select name="free_preview"><option value="0">否</option><option value="1">是（未报名也能看）</option></select></div></div>
<button class="btn">添加课时</button></form></div></div>'''
    return HTMLResponse(page(body, f"{c['title']} · 课程管理"))


@app.post('/{course_id}')
def update_course(request: Request, course_id: int, title: str = Form(...), category: str = Form('其他'),
                  level: str = Form('入门'), summary: str = Form(''), description: str = Form(...),
                  cover_text: str = Form('100'), instructor: str = Form(''), price_yuan: float = Form(0)):
    require_admin(request)
    courses.init_db()
    title = title.strip()
    description = description.strip()
    if not title or len(title) > 120:
        raise HTTPException(400, '课程名称不能为空，且最多 120 字。')
    if not description or len(description) > 10000:
        raise HTTPException(400, '课程说明不能为空，且最多 10000 字。')
    if category not in courses.CATEGORIES:
        raise HTTPException(400, '请选择有效分类。')
    if level not in courses.LEVELS:
        raise HTTPException(400, '请选择有效难度。')
    if price_yuan < 0 or price_yuan > 100000:
        raise HTTPException(400, '价格需在 0—100,000 元之间。')
    with site.db() as conn:
        _load(conn, course_id)
        conn.execute('''UPDATE courses SET title=?,category=?,level=?,summary=?,description=?,
            cover_text=?,instructor=?,price_cents=?,updated_at=? WHERE id=?''',
            (title, category, level, summary.strip()[:200], description,
             (cover_text.strip() or '100')[:6], (instructor.strip() or courses.DEFAULT_INSTRUCTOR)[:40],
             int(round(price_yuan * 100)), core.now(), course_id))
    return RedirectResponse(f'/manage/courses/{course_id}', 303)


@app.post('/{course_id}/lessons')
def add_lesson(request: Request, course_id: int, title: str = Form(...), video_url: str = Form(''),
               duration_minutes: int = Form(0), free_preview: int = Form(0)):
    require_admin(request)
    courses.init_db()
    title = title.strip()
    if not title or len(title) > 120:
        raise HTTPException(400, '课时标题不能为空，且最多 120 字。')
    if duration_minutes < 0 or duration_minutes > 600:
        raise HTTPException(400, '时长需在 0—600 分钟之间。')
    stamp = core.now()
    with site.db() as conn:
        _load(conn, course_id)
        nxt = conn.execute('SELECT COALESCE(MAX(sort_order),0)+1 n FROM course_lessons WHERE course_id=?', (course_id,)).fetchone()['n']
        conn.execute('INSERT INTO course_lessons(course_id,title,video_url,duration_minutes,sort_order,free_preview,created_at) VALUES(?,?,?,?,?,?,?)',
                     (course_id, title, courses.safe_url(video_url), duration_minutes, nxt,
                      1 if int(free_preview or 0) == 1 else 0, stamp))
        conn.execute('UPDATE courses SET updated_at=? WHERE id=?', (stamp, course_id))
    return RedirectResponse(f'/manage/courses/{course_id}', 303)


@app.post('/{course_id}/lessons/{lesson_id}/delete')
def delete_lesson(request: Request, course_id: int, lesson_id: int):
    require_admin(request)
    courses.init_db()
    with site.db() as conn:
        conn.execute('DELETE FROM course_lessons WHERE id=? AND course_id=?', (lesson_id, course_id))
        conn.execute('UPDATE courses SET updated_at=? WHERE id=?', (core.now(), course_id))
    return RedirectResponse(f'/manage/courses/{course_id}', 303)


@app.post('/{course_id}/status')
def set_status(request: Request, course_id: int, status: str = Form(...)):
    require_admin(request)
    courses.init_db()
    if status not in courses.STATUSES:
        raise HTTPException(400, '状态不正确。')
    with site.db() as conn:
        _load(conn, course_id)
        if status == 'published':
            n = conn.execute('SELECT COUNT(*) n FROM course_lessons WHERE course_id=?', (course_id,)).fetchone()['n']
            if not n:
                raise HTTPException(409, '至少添加一节课时后才能发布。')
        conn.execute('UPDATE courses SET status=?,updated_at=? WHERE id=?', (status, core.now(), course_id))
    return RedirectResponse(f'/manage/courses/{course_id}', 303)
