import hashlib
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import app_v2 as site
import coin_core
import payment_core
import community_core as core

router = APIRouter()

# Public signup is the default; explicit TOOLBOARD_GUEST_SIGNUP=0 pauses it.
GUEST_SIGNUP_OPEN = os.getenv("TOOLBOARD_GUEST_SIGNUP", "1") == "1"

EXTRA_CSS = '''<style>
.memberbar{display:flex;gap:8px;align-items:center}.member-pill{padding:8px 12px;border-radius:999px;background:#fff;border:1px solid #dededb;font-size:11px}.community-wrap{width:min(980px,calc(100% - 36px));margin:42px auto 80px}.community-card{background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:26px;margin-bottom:16px}.community-card h1,.community-card h2{margin-top:0}.community-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.review{padding:15px 0;border-top:1px solid #eee}.review:first-of-type{border-top:0}.stars{letter-spacing:2px;font-size:13px}.notice{padding:12px 14px;border-radius:12px;background:#f3f3f0;font-size:11px;color:#666;margin-bottom:15px}.price{font-size:24px;font-weight:760}.role{font-size:10px;padding:5px 8px;border-radius:999px;background:#111;color:#fff}.dev-actions{display:flex;gap:8px;flex-wrap:wrap}.dev-tools{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin:16px 0 24px}.dev-tool{border:1px solid #e8e8e5;border-radius:19px;padding:18px;background:#fbfbfa}.dev-tool-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.dev-tool h3{margin:0 0 5px;font-size:19px}.dev-tool-sub{font-size:10px;color:#8c8e92}.dev-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:15px 0}.dev-stat{background:#f0f0ed;border-radius:12px;padding:10px;min-width:0}.dev-stat b{display:block;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dev-stat span{display:block;font-size:8px;color:#92949a;margin-top:2px}.status-dot{font-size:9px;border-radius:999px;padding:5px 8px;background:#ebf4ec;color:#2f6f3b;white-space:nowrap}.status-dot.off{background:#f3e5e5;color:#8b3535}.section-title{font-size:13px;color:#777;font-weight:720;margin:24px 0 10px}.table-wrap{overflow-x:auto}.small-link{font-size:10px;color:#555;text-decoration:underline;text-underline-offset:3px}.muted{font-size:11px;color:#888;line-height:1.7}.coin-balance{text-align:right;flex:none}.coin-balance b{display:block;font-size:34px;letter-spacing:-.04em;line-height:1}.coin-balance span{font-size:9px;color:#92949a}.coin-plus{color:#2f6f3b;font-weight:750}.coin-minus{color:#b42318;font-weight:750}.coin-price-form{display:flex;align-items:center;gap:8px;margin:0 0 11px;padding:11px 13px;background:#f2f2ef;border-radius:13px}.coin-price-form{flex-wrap:wrap}.coin-price-form label{font-size:10px;color:#777;flex:none}.coin-price-form input{width:62px;height:32px;border:1px solid #d7d7d3;border-radius:9px;padding:0 8px;background:#fff}.coin-price-form .coin-unit{font-size:9px;color:#92949a;flex:none}.coin-price-form .btn{height:32px;padding:0 11px;font-size:10px;margin-left:auto}@media(max-width:700px){.community-grid,.dev-tools{grid-template-columns:1fr}.dev-stats{grid-template-columns:1fr 1fr}}</style>'''


def page(body, title="小飞侠设计100%"):
    return site.page(EXTRA_CSS + body, title)


def login_required(request):
    user = core.current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录。")
    return user


class _NeedsLogin(Exception):
    """Raised by page handlers so a signed-out visitor lands on the form."""

    def __init__(self, next_path):
        self.next_path = next_path


def page_login_required(request, next_path):
    user = core.current_user(request)
    if not user:
        raise _NeedsLogin(next_path)
    return user


def developer_required(request):
    user = login_required(request)
    if not core.is_developer(user):
        raise HTTPException(status_code=403, detail="只有已获资格的开发者可以发布工具。")
    return user


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    user = core.current_user(request)
    if user:
        return RedirectResponse(next or "/", 303)
    body = f'''<div class="loginwrap"><div class="login"><div class="eyebrow">DESGIN 100%</div><h1>登录</h1>
    <div class="notice">使用注册时的邮箱或院内账号登录。还没有账号？<a href="/account/register">点此注册</a>。</div>
    <form action="/account/login" method="post"><input type="hidden" name="next" value="{site.esc(next)}"><div class="field"><label>用户名 / 邮箱</label><input name="account" required autofocus></div>
    <div class="field"><label>密码</label><input name="password" type="password" required></div><button class="btn" type="submit">登录</button> <a class="btn secondary" href="/account/register">注册</a></form></div></div>'''
    return HTMLResponse(page(body,"登录 · 小飞侠设计100%"))


@router.post("/login")
def login(request: Request, account: str = Form(...), password: str = Form(...), next: str = Form("/")):
    core.init_db()
    with site.db() as conn:
        user = conn.execute("SELECT * FROM community_users WHERE (username=? COLLATE NOCASE OR email=? COLLATE NOCASE) AND active=1", (account.strip(),account.strip())).fetchone()
    if not user or not core.verify_password(password,user['password_salt'],user['password_hash']):
        raise HTTPException(status_code=401, detail="用户名或密码不正确。")
    resp = RedirectResponse(next if next.startswith('/') else '/',303)
    resp.set_cookie(core.USER_COOKIE,core.make_session(user['id']),httponly=True,secure=True,samesite="lax",max_age=7*86400)
    return resp


def registration_page(internal=False, error='', values=None, status_code=200):
    values = values or {}
    value = lambda name: site.esc(values.get(name, ''))
    title = '院内人员注册' if internal else '创建账号'
    intro = '使用真实姓名和邀请码认证院内身份。' if internal else '下载免费工具，购买工具与课程。'
    fields = (f'''<div class="field"><label for="real-name">真实姓名</label><input id="real-name" name="real_name" autocomplete="name" value="{value('real_name')}" required></div>''' if internal else '')
    fields += f'''<div class="field"><label for="display-name">昵称</label><input id="display-name" name="display_name" autocomplete="nickname" value="{value('display_name')}" maxlength="80" required></div>'''
    if internal:
        fields += f'''<div class="field"><label for="invite-code">邀请码</label><input id="invite-code" name="invite_code" autocomplete="off" value="{value('invite_code')}" required><small>由管理员提供，仅用于院内身份认证。</small></div>'''
    else:
        fields += f'''<div class="field"><label for="signup-email">邮箱</label><input id="signup-email" name="email" type="email" autocomplete="username" value="{value('email')}" maxlength="254" required></div>'''
    notice = f'<div class="signup-error" role="alert">{site.esc(error)}</div>' if error else ''
    closed = not internal and not GUEST_SIGNUP_OPEN
    if closed:
        notice += '<div class="signup-error" role="status">公开注册暂未开放，请稍后再试。</div>'
    secondary = '<a href="/account/register">← 返回普通账号注册</a>' if internal else '<a href="/account/register/internal">院内人员注册 →</a>'
    role = core.ROLE_XIAOFEIXIA if internal else core.ROLE_XIAOYOUXIA
    body = f'''<style>
.signup-shell{{width:min(440px,calc(100% - 32px));margin:64px auto 80px}}
.signup-card{{padding:32px;background:#fff;border:1px solid #e6e6e3;border-radius:24px}}
.signup-card h1{{font-size:30px;margin:12px 0 8px}}.signup-intro{{color:#777;font-size:13px;line-height:1.7;margin:0 0 26px}}
.signup-card .field{{margin-bottom:18px}}.signup-card label{{display:block;font-size:12px;color:#555;margin-bottom:8px}}
.signup-card input{{box-sizing:border-box;width:100%;height:46px;padding:0 12px;border:1px solid #ddd;border-radius:10px;background:#fff}}
.signup-card input:focus{{outline:2px solid #777;outline-offset:2px}}.signup-card small{{display:block;color:#888;font-size:11px;margin-top:6px}}
.signup-submit{{width:100%;justify-content:center;margin-top:6px}}.signup-login{{font-size:12px;text-align:center;color:#777;margin:22px 0 0}}
.signup-login a{{color:#111;text-decoration:underline}}.signup-secondary{{border-top:1px solid #eee;margin-top:24px;padding-top:20px;text-align:center;font-size:12px;color:#777}}
.signup-error{{background:#fff0ee;border:1px solid #f2d2cd;padding:12px;border-radius:10px;font-size:12px;line-height:1.6;margin:16px 0}}
@media(max-width:520px){{.signup-shell{{margin-top:28px}}.signup-card{{padding:24px}}}}
</style><main class="signup-shell"><div class="signup-card"><div class="eyebrow">DESIGN 100%</div><h1>{title}</h1><p class="signup-intro">{intro}</p>{notice}
<form action="/account/register" method="post"><input type="hidden" name="role" value="{role}">{fields}
<div class="field"><label for="signup-password">密码</label><input id="signup-password" name="password" type="password" autocomplete="new-password" minlength="6" required><small>至少 6 位。</small></div>
<div class="field"><label for="confirm-password">确认密码</label><input id="confirm-password" name="confirm_password" type="password" autocomplete="new-password" minlength="6" required></div>
<button class="btn signup-submit" {'disabled' if closed else ''}>{'认证并注册' if internal else '注册'}</button></form>
<p class="signup-login">已有账号？ <a href="/account/login">登录</a></p><div class="signup-secondary">{secondary}</div></div></main>'''
    return HTMLResponse(page(body, title + ' · 小飞侠设计100%'), status_code=status_code)


@router.get('/register', response_class=HTMLResponse)
def register_page():
    return registration_page()


@router.get('/register/internal', response_class=HTMLResponse)
def internal_register_page():
    return registration_page(internal=True)


@router.post('/register')
def register(request: Request, role: str = Form('xiaoyouxia'), display_name: str = Form(''),
             email: str = Form(''), password: str = Form(...), confirm_password: str = Form(''),
             real_name: str = Form(''), invite_code: str = Form('')):
    import sqlite3
    import re
    core.init_db()
    internal = role == core.ROLE_XIAOFEIXIA
    values = dict(display_name=display_name, email=email, real_name=real_name, invite_code=invite_code)
    def fail(message, status=400):
        return registration_page(internal, message, values, status)
    if role not in (core.ROLE_XIAOFEIXIA, core.ROLE_XIAOYOUXIA):
        return fail('请选择正确的注册入口。')
    if not internal and not GUEST_SIGNUP_OPEN:
        return fail('公开注册暂未开放。', 403)
    if len(password) < 6 or len(password) > 1024:
        return fail('密码至少 6 位，最多 1024 位。')
    if password != confirm_password:
        return fail('两次输入的密码不一致，请重新输入。')
    nickname = display_name.strip()
    clean_name = ' '.join(real_name.strip().split())
    if internal and not nickname:
        nickname = clean_name
    if not nickname or len(nickname) > 80:
        return fail('请填写不超过 80 字的昵称。')
    email = email.strip().lower()
    if not internal and (len(email)>254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email)):
        return fail('请填写有效的邮箱地址。')
    if internal and (not clean_name or len(clean_name)>80):
        return fail('请填写正确的真实姓名。')
    salt, digest = core.hash_password(password)
    stamp = core.now()
    try:
        with site.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if internal:
                invite = conn.execute('SELECT * FROM xiaofeixia_invites WHERE code=? COLLATE NOCASE', (invite_code.strip(),)).fetchone()
                if not invite or invite['used'] or invite['real_name'].lower() != clean_name.lower():
                    return fail('邀请码无效、已使用，或与真实姓名不匹配。')
            cur = conn.execute('''INSERT INTO community_users(username,display_name,email,password_salt,password_hash,role,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,1,?,?)''',
                (clean_name if internal else email, nickname, None if internal else email, salt, digest, role, stamp, stamp))
            uid = cur.lastrowid
            if internal:
                conn.execute('UPDATE xiaofeixia_invites SET used=1,used_by_user_id=?,used_at=? WHERE id=?', (uid, stamp, invite['id']))
    except sqlite3.IntegrityError:
        return fail('该账号已注册，请登录或使用其他邮箱。', 409)
    resp = RedirectResponse('/account/me',303)
    resp.set_cookie(core.USER_COOKIE, core.make_session(uid), httponly=True, secure=True, samesite='lax', max_age=7*86400)
    return resp


@router.post("/logout")
def logout():
    resp=RedirectResponse('/',303); resp.delete_cookie(core.USER_COOKIE); return resp


@router.get("/me", response_class=HTMLResponse)
def me(request: Request):
    core.init_db()
    try:
        user=page_login_required(request,'/account/me')
    except _NeedsLogin as need:
        return RedirectResponse(f'/account/login?next={need.next_path}',303)
    with site.db() as conn:
        orders=conn.execute("SELECT o.*,t.name FROM orders o JOIN tools t ON t.id=o.tool_id WHERE o.user_id=? ORDER BY o.id DESC",(user['id'],)).fetchall()
        purchases=conn.execute("SELECT * FROM purchase_orders WHERE user_id=? ORDER BY id DESC", (user['id'],)).fetchall()
        submissions=conn.execute("SELECT * FROM tool_submissions WHERE user_id=? ORDER BY id DESC",(user['id'],)).fetchall() if core.is_developer(user) else []
        owned=conn.execute('''
            SELECT t.*,
                   (SELECT version FROM releases r WHERE r.tool_id=t.id AND r.active=1 ORDER BY r.id DESC LIMIT 1) current_version,
                   (SELECT COUNT(*) FROM reviews r WHERE r.tool_id=t.id) review_count,
                   (SELECT ROUND(AVG(rating),1) FROM reviews r WHERE r.tool_id=t.id) avg_rating,
                   ((SELECT COUNT(*) FROM orders o WHERE o.tool_id=t.id AND o.status='paid' AND o.amount_cents>0)+(SELECT COUNT(*) FROM purchase_orders o WHERE o.product_type='tool' AND o.product_id=t.id AND o.seller_user_id=t.owner_user_id AND o.status='paid')) paid_orders,
                   ((SELECT COALESCE(SUM(amount_cents),0) FROM orders o WHERE o.tool_id=t.id AND o.status='paid' AND o.amount_cents>0)+(SELECT COALESCE(SUM(amount_cents),0) FROM purchase_orders o WHERE o.product_type='tool' AND o.product_id=t.id AND o.seller_user_id=t.owner_user_id AND o.status='paid')) paid_amount
            FROM tools t WHERE t.owner_user_id=? ORDER BY t.active DESC,t.name
        ''',(user['id'],)).fetchall() if core.is_developer(user) else []
        application = conn.execute('SELECT * FROM developer_applications WHERE user_id=? ORDER BY id DESC LIMIT 1', (user['id'],)).fetchone()
        coin_name=coin_core.COIN_NAME
        coin_balance=coin_core.balance(conn,user['id'])
        coin_rows=coin_core.recent(conn,user['id'])
        coin_earned=coin_core.earned(conn,user['id'])

    order_rows=''.join(f'<tr><td>{site.esc(o["name"])}</td><td>¥{o["amount_cents"]/100:.2f}</td><td>{site.esc(o["status"])}</td></tr>' for o in orders) or '<tr><td colspan="3">暂无订单</td></tr>'
    purchase_rows=''.join(f'<tr><td><a href="/account/purchases/{o["id"]}">{site.esc(o["product_name"])}</a></td><td>¥{o["amount_cents"]/100:.2f}</td><td>{payment_core.STATUS_LABELS.get(o["status"], "处理中")}</td></tr>' for o in purchases)
    order_rows=purchase_rows+order_rows
    sub_rows=''.join(f'<tr><td>{site.esc(s["name"] or s["version"])}</td><td>{"新工具" if s["submission_type"]=="new_tool" else "版本更新"}</td><td>{site.esc(s["version"])}</td><td>{site.esc(s["status"])}</td></tr>' for s in submissions) or '<tr><td colspan="4">暂无投稿</td></tr>'

    tool_cards=[]
    for t in owned:
        version=t['current_version'] or '待发布'
        reviews=int(t['review_count'] or 0)
        rating=f"{float(t['avg_rating']):.1f}" if t['avg_rating'] is not None else '—'
        paid_orders=int(t['paid_orders'] or 0)
        paid_amount=int(t['paid_amount'] or 0)/100
        state='<span class="status-dot">已上架</span>' if t['active'] else '<span class="status-dot off">已下架</span>'
        tool_cards.append(f'''<div class="dev-tool"><div class="dev-tool-head"><div><h3>{site.esc(t['name'])}</h3><div class="dev-tool-sub">/{site.esc(t['slug'])} · {site.esc(t['platform'])}</div></div>{state}</div>
        <div class="dev-stats"><div class="dev-stat"><b>v{site.esc(version)}</b><span>当前版本</span></div><div class="dev-stat"><b>¥{int(t["price_cents"] or 0)/100:.2f}</b><span>人民币售价</span></div><div class="dev-stat"><b>{int(t['downloads'] or 0):,}</b><span>累计下载</span></div><div class="dev-stat"><b>{rating} / 5</b><span>{reviews} 条评价</span></div><div class="dev-stat"><b>{paid_orders}</b><span>已确认购买</span></div><div class="dev-stat"><b>¥{paid_amount:.2f}</b><span>现金销售总额（未结算）</span></div></div>
        <form class="coin-price-form" action="/account/tools/{site.esc(t['slug'])}/cash-price" method="post"><input type="hidden" name="csrf" value="{payment_core.csrf_token(request)}"><label>人民币售价</label><input name="price_yuan" type="number" min="0" max="100000" step="0.01" value="{int(t['price_cents'] or 0)/100:.2f}" required><span class="coin-unit">元</span><button class="btn secondary">保存</button></form>
        <div class="dev-actions"><a class="btn" href="/developer/submit?tool={site.esc(t['slug'])}">提交新版本</a><a class="btn secondary" href="/tools/{site.esc(t['slug'])}">查看产品</a></div></div>''')

    led=''.join(f'<tr><td>{site.esc(coin_core.REASON_LABELS.get(r["reason"],r["reason"]))}</td><td>{site.esc(r["note"] or "—")}</td><td class="{"coin-plus" if int(r["delta"])>0 else "coin-minus"}">{"+" if int(r["delta"])>0 else ""}{int(r["delta"])}</td><td>{site.esc((r["created_at"] or "")[:10])}</td></tr>' for r in coin_rows) or f'<tr><td colspan="4">暂无{coin_name}记录</td></tr>'
    coin_html = ''
    if coin_rows or coin_balance:
        coin_html = f'''<div class="community-card"><details><summary>历史积分记录 · 余额 {coin_balance}</summary><p class="muted">积分已停用，不再奖励或兑换工具。历史余额及流水保留，不折算现金；已兑换工具权限继续有效。已有悬赏可按原约定完成或取消。</p><div class="table-wrap"><table class="table"><thead><tr><th>类型</th><th>说明</th><th>变动</th><th>时间</th></tr></thead><tbody>{led}</tbody></table></div></details></div>'''

    dev=''
    if core.is_developer(user):
        dev=f'''<div class="community-card"><div class="dev-tool-head"><div><h2>开发者中心</h2><p class="muted">每位获批开发者都可以提交新工具；已有工具的新版本只允许该工具原开发者提交。</p></div><a class="btn" href="/developer/submit">提交新工具</a></div>
        <div class="section-title">我的工具</div><div class="dev-tools">{''.join(tool_cards) if tool_cards else '<div class="notice">暂无已归属工具。提交新工具并审核通过后，会自动出现在这里。</div>'}</div>
        <div class="section-title">投稿记录</div><div class="table-wrap"><table class="table"><thead><tr><th>工具</th><th>类型</th><th>版本</th><th>状态</th></tr></thead><tbody>{sub_rows}</tbody></table></div></div>'''

    if not core.is_developer(user):
        if application and application['status'] == 'pending':
            dev = '<div class="community-card"><h2>开发者申请</h2><p>申请已提交，等待管理员审核。</p></div>'
        else:
            note = ('<div class="notice">上次申请未通过：' + site.esc(application['review_note'] or '请补充工具计划后重新申请。') + '</div>') if application and application['status'] == 'rejected' else ''
            dev = f'''<div class="community-card"><h2>成为开发者</h2><p class="muted">想分享自己的工具？提交开发方向与工具计划，审核通过后即可发布。开发者资格不包含院内课程福利。</p>{note}<form action="/account/developer/apply" method="post"><input type="hidden" name="csrf" value="{payment_core.csrf_token(request)}"><div class="field"><label for="developer-proposal">开发方向与工具计划</label><textarea id="developer-proposal" name="proposal" minlength="10" maxlength="2000" required></textarea></div><button class="btn">申请成为开发者</button></form></div>'''

    body=f'<div class="community-wrap"><div class="community-card"><span class="role">{core.user_label(user)}</span><h1>{site.esc(user["display_name"])}</h1><p>{site.esc(user["email"] or "院内账号")}</p><form action="/account/logout" method="post"><button class="btn secondary">退出登录</button></form></div>{coin_html}{dev}<div class="community-card"><h2>我的购买</h2><div class="table-wrap"><table class="table"><tbody>{order_rows}</tbody></table></div></div></div>'
    return HTMLResponse(page(body,"我的账号 · 小飞侠设计100%"))


@router.post("/tools/{slug}/review")
def review(request: Request, slug: str, rating: int = Form(...), content: str = Form("")):
    user=login_required(request)
    if rating<1 or rating>5: raise HTTPException(400,"评分必须是 1-5 分。")
    with site.db() as conn:
        tool=conn.execute("SELECT id FROM tools WHERE slug=? AND active=1",(slug,)).fetchone()
        if not tool: raise HTTPException(404,"工具不存在。")
        stamp=core.now(); existing=conn.execute("SELECT id FROM reviews WHERE tool_id=? AND user_id=?",(tool['id'],user['id'])).fetchone()
        if existing: conn.execute("UPDATE reviews SET rating=?,content=?,updated_at=? WHERE id=?",(rating,content.strip(),stamp,existing['id']))
        else: conn.execute("INSERT INTO reviews(tool_id,user_id,rating,content,created_at,updated_at) VALUES(?,?,?,?,?,?)",(tool['id'],user['id'],rating,content.strip(),stamp,stamp))
    return RedirectResponse(f'/tools/{slug}#reviews',303)


@router.post("/tools/{slug}/order")
def create_order(request: Request, slug: str, csrf: str = Form("")):
    user = login_required(request)
    payment_core.check_csrf(request, csrf)
    with site.db() as conn:
        tool = conn.execute("SELECT id FROM tools WHERE slug=? AND active=1", (slug,)).fetchone()
        if not tool:
            raise HTTPException(404, "工具不存在。")
        oid = payment_core.create_purchase(conn, user, 'tool', tool['id'])
    return RedirectResponse(f'/account/purchases/{oid}', 303)


@router.post("/tools/{slug}/coin-unlock")
def coin_unlock(request: Request, slug: str, csrf: str = Form("")):
    login_required(request)
    raise HTTPException(410, "积分兑换已停用，历史兑换权限保留。")

@router.post("/tools/{slug}/coin-price")
def set_coin_price(request: Request, slug: str, feixia_coin_price: int = Form(0), csrf: str = Form("")):
    developer_required(request)
    raise HTTPException(410, "积分定价已停用，请设置人民币售价。")

@router.post("/tools/{slug}/cash-price")
def set_cash_price(request: Request, slug: str, price_yuan: str = Form(...), csrf: str = Form("")):
    user = developer_required(request)
    payment_core.check_csrf(request, csrf)
    cents = payment_core.yuan_to_cents(price_yuan)
    with site.db() as conn:
        tool = conn.execute("SELECT * FROM tools WHERE slug=?", (slug,)).fetchone()
        if not tool:
            raise HTTPException(404, "工具不存在。")
        if not core.is_tool_owner(tool, user):
            raise HTTPException(403, "只有原开发者可以设置价格。")
        if tool['tool_type'] == 'web_app' and cents > 0:
            raise HTTPException(400, "网页工具目前仅支持免费使用。")
        conn.execute("UPDATE tools SET price_cents=?,legacy_coin_only=0,updated_at=? WHERE id=?", (cents, core.now(), tool['id']))
    return RedirectResponse('/account/me', 303)


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_page(request: Request, order_id: int):
    try:
        user=page_login_required(request,f'/account/orders/{order_id}')
    except _NeedsLogin as need:
        return RedirectResponse(f'/account/login?next={need.next_path}',303)
    with site.db() as conn:
        o=conn.execute("SELECT o.*,t.name,t.slug FROM orders o JOIN tools t ON t.id=o.tool_id WHERE o.id=? AND o.user_id=?",(order_id,user['id'])).fetchone()
    if not o: raise HTTPException(404,"订单不存在。")
    body=f'''<div class="community-wrap"><div class="community-card"><div class="eyebrow">订单 {site.esc(o['order_no'])}</div><h1>{site.esc(o['name'])}</h1><div class="price">¥{o['amount_cents']/100:.2f}</div>
    <div class="notice" style="margin-top:18px">订单系统已经建立。微信/支付宝正式支付需要配置商户号和支付回调后才会开放；现在不会伪造“已付款”。</div><a class="btn secondary" href="/tools/{site.esc(o['slug'])}">返回工具</a></div></div>'''
    return HTMLResponse(page(body,"订单 · 小飞侠设计100%"))


developer_router=APIRouter()


@developer_router.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request, tool: str = ""):
    core.init_db()
    if not core.current_user(request):
        return RedirectResponse('/account/login?next=/developer/submit',303)
    user=developer_required(request)
    with site.db() as conn:
        tools=conn.execute("SELECT id,name,slug,price_cents,feixia_coin_price FROM tools WHERE owner_user_id=? ORDER BY active DESC,name",(user['id'],)).fetchall()
    selected_slug=tool.strip()
    opts=''.join(f'<option data-price="{int(t["price_cents"] or 0)/100:.2f}" data-coin="{coin_core.coin_price(t)}" value="{site.esc(t["slug"])}" {"selected" if t["slug"]==selected_slug else ""}>{site.esc(t["name"])} · ¥{int(t["price_cents"] or 0)/100:.2f}</option>' for t in tools)
    default_type='new_release' if selected_slug and any(t['slug']==selected_slug for t in tools) else 'new_tool'
    category_opts=''.join(f'<option value="{site.esc(c)}">{site.esc(c)}</option>' for c in core.TOOL_CATEGORIES)
    body=f'''<div class="community-wrap"><div class="community-card"><span class="role">开发者</span><h1>提交工具 / 新版本</h1><div class="notice">新工具可自行提交；已有工具的新版本只允许原开发者提交。网页工具提交后由管理员审核上架。</div>
    <form action="/developer/submit" method="post" enctype="multipart/form-data"><div class="field"><label>投稿类型</label><select name="submission_type" id="sub-type"><option value="new_tool" {"selected" if default_type=="new_tool" else ""}>新桌面工具</option><option value="new_web_app">新网页工具（小飞侠 Cloud）</option><option value="new_release" {"selected" if default_type=="new_release" else ""}>已有工具新版本</option></select></div>
    <div class="field" id="field-existing"><label>已有工具（仅显示你自己的工具）</label><select name="existing_slug"><option value="">—</option>{opts}</select></div><div class="community-grid"><div><div class="field"><label>工具名称</label><input name="name"></div><div class="field"><label>一句话介绍</label><input name="tagline"></div><div class="field"><label>分类</label><select name="category">{category_opts}</select></div></div><div><div class="field" id="field-platform"><label>平台</label><input name="platform" value="Windows"></div><div class="field"><label>图标文字</label><input name="icon_text" value="100"></div><div class="field" id="field-price"><label>人民币售价（0 = 免费）</label><input name="price_yuan" type="number" min="0" max="100000" step="0.01" value="0"><div class="muted" style="margin-top:5px">免费或人民币定价。发布及更新记录保留在开发者中心，现金销售单独统计。</div></div><div class="field"><label>版本号</label><input name="version" required></div></div></div>
    <div class="field"><label>完整介绍</label><textarea name="description"></textarea></div><div class="field"><label>更新说明</label><textarea name="notes"></textarea></div><div class="field" id="field-package"><label>安装包（仅支持 .zip）</label><input name="package" type="file" accept=".zip"></div><div class="field" id="field-appurl" style="display:none"><label>工具访问地址</label><input name="app_url" placeholder="https://your-app.example.com"></div><button class="btn">提交审核</button></form></div></div>
    <script>!function(){{const s=document.getElementById('sub-type'),pkg=document.getElementById('field-package'),url=document.getElementById('field-appurl'),plat=document.getElementById('field-platform'),ex=document.getElementById('field-existing'),pr=document.getElementById('field-price');function u(){{const v=s.value,web=v==='new_web_app';pkg.style.display=web?'none':'';url.style.display=web?'':'none';plat.style.display=web?'none':'';ex.style.display=v==='new_release'?'':'none';if(web){{plat.querySelector('input').value='Web';pr.querySelectorAll('input').forEach(i=>i.value='0')}}else{{plat.querySelector('input').value='Windows'}}const fi=pkg.querySelector('input');if(fi)fi.required=!web&&v!=='new_release'}}function prices(){{if(s.value==='new_release'){{const o=ex.querySelector('select').selectedOptions[0];if(o&&o.dataset.price){{pr.querySelector('[name=price_yuan]').value=o.dataset.price}}}}}}ex.querySelector('select').addEventListener('change',prices);s.addEventListener('change',()=>{{u();prices()}});u();prices()}}()</script>'''
    return HTMLResponse(page(body,"开发者投稿 · 小飞侠设计100%"))


@developer_router.post("/submit")
async def submit(request: Request, submission_type: str=Form(...), existing_slug: str=Form(""), name: str=Form(""), tagline: str=Form(""), description: str=Form(""), category: str=Form("效率工具"), platform: str=Form("Windows"), icon_text: str=Form("100"), price_yuan: float=Form(...), version: str=Form(...), notes: str=Form(""), package: UploadFile=File(...)):
    core.init_db(); user=developer_required(request); content=await package.read()
    if not content or len(content)>core.MAX_UPLOAD_BYTES: raise HTTPException(400,"安装包为空或超过大小限制。")
    if price_yuan<=0: raise HTTPException(400,"同行价格必须大于 0 元。")
    with site.db() as conn:
        tool=None; slug=""
        if submission_type=='new_release':
            tool=conn.execute("SELECT * FROM tools WHERE slug=?",(existing_slug.strip(),)).fetchone()
            if not tool: raise HTTPException(404,"已有工具不存在。")
            if not core.is_tool_owner(tool,user): raise HTTPException(403,"只有该工具原开发者可以提交新版本。")
            name=tool['name']; slug=tool['slug']; tagline=tool['tagline']; description=tool['description']; category=tool['category']; platform=tool['platform']; icon_text=tool['icon_text']
        elif submission_type=='new_tool':
            if not name.strip(): raise HTTPException(400,"工具名称不能为空。")
            slug=core.slug_from_name(name)
        else:
            raise HTTPException(400,"投稿类型无效。")
        safe=(package.filename or f'{slug}-{version}.zip').replace('/','_').replace('\\','_'); folder=core.SUBMISSION_DIR/str(user['id']); folder.mkdir(parents=True,exist_ok=True); path=folder/f'{secrets.token_hex(4)}-{safe}'; path.write_bytes(content); digest=hashlib.sha256(content).hexdigest()
        conn.execute("INSERT INTO tool_submissions(user_id,submission_type,tool_id,slug,name,tagline,description,category,platform,icon_text,price_cents,version,notes,package_name,package_path,sha256,size,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)",(user['id'],submission_type,tool['id'] if tool else None,slug,name.strip(),tagline.strip(),description.strip(),category.strip(),platform.strip(),icon_text.strip(),int(round(price_yuan*100)),version.strip(),notes.strip(),safe,str(path),digest,len(content),core.now()))
    return RedirectResponse('/account/me',303)


def install_public_routes(app):
    app.router.routes[:] = [r for r in app.router.routes if getattr(r,'path',None) not in ('/tools/{slug}','/tools/{slug}/download')]

    @app.get('/tools/{slug}',response_class=HTMLResponse)
    def detail(request: Request, slug: str):
        core.init_db(); user=core.current_user(request)
        with site.db() as conn:
            t=conn.execute("SELECT * FROM tools WHERE slug=? AND active=1",(slug,)).fetchone()
            if not t: raise HTTPException(404,"工具不存在。")
            rel=site.latest_release(conn,t['id']); reviews=conn.execute("SELECT r.*,u.display_name,u.role FROM reviews r JOIN community_users u ON u.id=r.user_id WHERE r.tool_id=? ORDER BY r.id DESC",(t['id'],)).fetchall(); avg=conn.execute("SELECT AVG(rating) a,COUNT(*) c FROM reviews WHERE tool_id=?",(t['id'],)).fetchone(); allowed=core.can_download(conn,user,t)
        version=rel['version'] if rel else '待发布'; developer=t['developer_name'] or '小飞侠开发者'; price=int(t['price_cents'] or 0)
        tool_type=t['tool_type'] if 'tool_type' in t.keys() else 'desktop'
        app_url=t['app_url'] if 'app_url' in t.keys() else ''
        is_web=tool_type=='web_app' and app_url
        if is_web:
            action=f'<a class="btn" href="{site.esc(app_url)}" target="_blank" rel="noopener">立即使用 →</a>'
        elif not user: action=f'<a class="btn" href="/account/login?next=/tools/{site.esc(slug)}">登录后购买或下载</a>'
        elif allowed: action=f'<a class="btn" href="/tools/{site.esc(slug)}/download">下载 · v{site.esc(version)}</a>'
        else:
            action=''
            token=payment_core.csrf_token(request)
            if price>0:
                action=f'<form action="/account/purchases/new/tool/{t["id"]}" method="post"><input type="hidden" name="csrf" value="{token}"><button class="btn">购买工具 · ¥{price/100:.2f}</button></form>'
            if not action:
                action='<span class="btn secondary">暂不可购买</span>'
        review_html=''.join(f'<div class="review"><div><b>{site.esc(r["display_name"])}</b> · <span class="stars">{"★"*int(r["rating"])}{"☆"*(5-int(r["rating"]))}</span></div><p>{site.esc(r["content"])}</p></div>' for r in reviews) or '<p>暂无评价，欢迎成为第一个评价的人。</p>'
        review_form=f'''<form action="/account/tools/{site.esc(slug)}/review" method="post"><div class="field"><label>评分 1-5</label><input name="rating" type="number" min="1" max="5" value="5" required></div><div class="field"><label>留言</label><textarea name="content"></textarea></div><button class="btn secondary">发布评价</button></form>''' if user else '<a class="btn secondary" href="/account/login?next=/tools/'+site.esc(slug)+'">登录后评价</a>'
        role_nav=(f'<a class="admin-link" href="/account/me">{site.esc(user["display_name"])} · {core.user_label(user)}</a>' if user else '<a class="admin-link" href="/account/login">登录 / 注册</a>')
        nav_html=site.nav().replace('<a class="admin-link" href="/manage">管理</a>',role_nav)
        platform_label='Web · 小飞侠 Cloud' if is_web else t['platform']
        if is_web:
            obtain_text='小飞侠 Cloud 网页工具，打开即用，无需下载安装。'
            obtain_price='☁️ 在线使用'
        elif price>0:
            obtain_text='人民币直接购买，付款后开通该工具下载权限。'
            obtain_price=f'¥{price/100:.2f}'
        elif t['legacy_coin_only']:
            obtain_text='现金售价待开发者确认，暂不接受新购买；历史兑换用户可继续下载。'
            obtain_price='待定价'
        else:
            obtain_text='该工具免费，登录后即可下载。'
            obtain_price='免费'
        body=nav_html+f'''<div class="shell"><section class="detail-hero"><a class="back" href="/">← 返回 Desgin 100%</a><div class="product"><div><div class="eyebrow">{site.esc(t['category'])} · {site.esc(platform_label)}</div><h1>{site.esc(t['name'])}</h1><div class="lead">{site.esc(t['tagline'])}</div><div class="facts"><div class="fact"><b>v{site.esc(version)}</b><span>当前版本</span></div><div class="fact"><b>{int(t['downloads']):,}</b><span>累计下载</span></div><div class="fact"><b>{site.esc(developer)}</b><span>开发者</span></div><div class="fact"><b>{(str(round(avg['a'],1))+' / 5') if avg['c'] else '—'}</b><span>{avg['c']} 条评价</span></div></div>{action}</div><div class="product-icon">{site.esc(t['icon_text'])}</div></div></section><section class="detail-grid"><div class="panel"><h2>工具介绍</h2><p>{site.esc(t['description'])}</p></div><div class="panel"><h2>获取方式</h2><p>{obtain_text}</p><div class="price">{obtain_price}</div></div></section><section id="reviews" class="panel" style="margin-bottom:80px"><h2>评价与留言</h2>{review_form}<div style="margin-top:24px">{review_html}</div></section></div>'''
        return HTMLResponse(site.page(body,f"{t['name']} · 小飞侠设计100%",EXTRA_CSS))

    @app.get('/tools/{slug}/download')
    def gated_download(request: Request, slug: str):
        user=core.current_user(request)
        if not user: return RedirectResponse(f'/account/login?next=/tools/{slug}',303)
        with site.db() as conn:
            t=conn.execute("SELECT * FROM tools WHERE slug=? AND active=1",(slug,)).fetchone()
            if not t: raise HTTPException(404,"工具不存在。")
            if not core.can_download(conn,user,t): return RedirectResponse(f'/tools/{slug}',303)
            rel=site.latest_release(conn,t['id'])
            if not rel: raise HTTPException(404,"安装包尚未发布。")
            path=Path(rel['package_path'])
            if not path.exists(): raise HTTPException(404,"安装包文件不存在。")
            conn.execute("UPDATE tools SET downloads=downloads+1,updated_at=? WHERE id=?",(core.now(),t['id'])); conn.execute("INSERT INTO download_logs(user_id,tool_id,release_id,created_at) VALUES(?,?,?,?)",(user['id'],t['id'],rel['id'],core.now()))
        return FileResponse(path=str(path),filename=rel['package_name'],media_type='application/octet-stream')


@router.post('/developer/apply')
def apply_developer(request: Request, proposal: str = Form(...), csrf: str = Form('')):
    user = login_required(request)
    payment_core.check_csrf(request, csrf)
    if core.is_developer(user):
        raise HTTPException(409, '你已具备开发者资格。')
    proposal = proposal.strip()
    if not 10 <= len(proposal) <= 2000:
        raise HTTPException(400, '请填写10—2000字的开发方向与工具计划。')
    with site.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        pending = conn.execute("SELECT id FROM developer_applications WHERE user_id=? AND status='pending'", (user['id'],)).fetchone()
        if not pending:
            conn.execute('INSERT INTO developer_applications(user_id,proposal,created_at) VALUES(?,?,?)',
                         (user['id'], proposal, core.now()))
    return RedirectResponse('/account/me', 303)
