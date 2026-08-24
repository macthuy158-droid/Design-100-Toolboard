import hashlib
import secrets
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import app_v2 as site
import coin_core
import community_core as core

router = APIRouter()

EXTRA_CSS = '''<style>
.memberbar{display:flex;gap:8px;align-items:center}.member-pill{padding:8px 12px;border-radius:999px;background:#fff;border:1px solid #dededb;font-size:11px}.community-wrap{width:min(980px,calc(100% - 36px));margin:42px auto 80px}.community-card{background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:26px;margin-bottom:16px}.community-card h1,.community-card h2{margin-top:0}.community-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.review{padding:15px 0;border-top:1px solid #eee}.review:first-of-type{border-top:0}.stars{letter-spacing:2px;font-size:13px}.notice{padding:12px 14px;border-radius:12px;background:#f3f3f0;font-size:11px;color:#666;margin-bottom:15px}.price{font-size:24px;font-weight:760}.role{font-size:10px;padding:5px 8px;border-radius:999px;background:#111;color:#fff}.dev-actions{display:flex;gap:8px;flex-wrap:wrap}.dev-tools{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin:16px 0 24px}.dev-tool{border:1px solid #e8e8e5;border-radius:19px;padding:18px;background:#fbfbfa}.dev-tool-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.dev-tool h3{margin:0 0 5px;font-size:19px}.dev-tool-sub{font-size:10px;color:#8c8e92}.dev-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:15px 0}.dev-stat{background:#f0f0ed;border-radius:12px;padding:10px;min-width:0}.dev-stat b{display:block;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dev-stat span{display:block;font-size:8px;color:#92949a;margin-top:2px}.status-dot{font-size:9px;border-radius:999px;padding:5px 8px;background:#ebf4ec;color:#2f6f3b;white-space:nowrap}.status-dot.off{background:#f3e5e5;color:#8b3535}.section-title{font-size:13px;color:#777;font-weight:720;margin:24px 0 10px}.table-wrap{overflow-x:auto}.small-link{font-size:10px;color:#555;text-decoration:underline;text-underline-offset:3px}.muted{font-size:11px;color:#888;line-height:1.7}.coin-balance{text-align:right;flex:none}.coin-balance b{display:block;font-size:34px;letter-spacing:-.04em;line-height:1}.coin-balance span{font-size:9px;color:#92949a}.coin-plus{color:#2f6f3b;font-weight:750}.coin-minus{color:#b42318;font-weight:750}.coin-price-form{display:flex;align-items:center;gap:8px;margin:0 0 11px;padding:11px 13px;background:#f2f2ef;border-radius:13px}.coin-price-form{flex-wrap:wrap}.coin-price-form label{font-size:10px;color:#777;flex:none}.coin-price-form input{width:62px;height:32px;border:1px solid #d7d7d3;border-radius:9px;padding:0 8px;background:#fff}.coin-price-form .coin-unit{font-size:9px;color:#92949a;flex:none}.coin-price-form .btn{height:32px;padding:0 11px;font-size:10px;margin-left:auto}@media(max-width:700px){.community-grid,.dev-tools{grid-template-columns:1fr}.dev-stats{grid-template-columns:1fr 1fr}}</style>'''


def page(body, title="小飞侠设计100%"):
    return site.page(EXTRA_CSS + body, title)


def login_required(request):
    user = core.current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录。")
    return user


def developer_required(request):
    user = login_required(request)
    if user['role'] != core.ROLE_XIAOFEIXIA:
        raise HTTPException(status_code=403, detail="只有小飞侠开发者可以发布工具。")
    return user


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    user = core.current_user(request)
    if user:
        return RedirectResponse(next or "/", 303)
    body = f'''<div class="loginwrap"><div class="login"><div class="eyebrow">DESGIN 100%</div><h1>登录</h1>
    <div class="notice">院内小飞侠：使用注册时设置的账号密码登录。还没有账号？<a href="/account/register">点此注册</a>。</div>
    <form action="/account/login" method="post"><input type="hidden" name="next" value="{site.esc(next)}"><div class="field"><label>用户名 / 邮箱</label><input name="account" required autofocus></div>
    <div class="field"><label>密码</label><input name="password" type="password" required></div><button class="btn" type="submit">登录</button> <a class="btn secondary" href="/account/register">小游侠注册</a></form></div></div>'''
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


@router.get("/register", response_class=HTMLResponse)
def register_page():
    body='''<div class="loginwrap"><div class="login"><div class="eyebrow">DESGIN 100%</div><h1>注册</h1>
    <div class="notice">小飞侠：院内开发者，可上传工具、免费下载所有工具。需要邀请码。<br>小游侠：同行用户，可购买并下载工具。</div>
    <div class="field"><label>选择身份</label><select id="role-select" onchange="document.getElementById('form-xiaofeixia').style.display=this.value==='xiaofeixia'?'block':'none';document.getElementById('form-xiaoyouxia').style.display=this.value==='xiaoyouxia'?'block':'none'"><option value="xiaoyouxia">小游侠（同行用户）</option><option value="xiaofeixia">小飞侠（院内开发者）</option></select></div>
    <form id="form-xiaoyouxia" action="/account/register" method="post"><input type="hidden" name="role" value="xiaoyouxia"><div class="field"><label>昵称</label><input name="display_name" required></div><div class="field"><label>邮箱</label><input name="email" type="email" required></div><div class="field"><label>密码</label><input name="password" type="password" minlength="6" required></div><button class="btn">注册小游侠</button></form>
    <form id="form-xiaofeixia" action="/account/register" method="post" style="display:none"><input type="hidden" name="role" value="xiaofeixia"><div class="field"><label>真实姓名（用于验证邀请码）</label><input name="real_name" required></div><div class="field"><label>昵称（对外显示）</label><input name="display_name" placeholder="不填则使用真实姓名"></div><div class="field"><label>邀请码</label><input name="invite_code" required></div><div class="field"><label>设置密码</label><input name="password" type="password" minlength="6" required></div><button class="btn">注册小飞侠</button></form>
    </div></div>'''
    return HTMLResponse(page(body,"注册 · 小飞侠设计100%"))


@router.post("/register")
def register(request: Request, role: str = Form("xiaoyouxia"), display_name: str = Form(""), email: str = Form(""), password: str = Form(...), real_name: str = Form(""), invite_code: str = Form("")):
    core.init_db()
    if len(password)<6: raise HTTPException(400,"密码至少 6 位。")
    salt,digest=core.hash_password(password); stamp=core.now()
    if role == core.ROLE_XIAOFEIXIA:
        clean_name = " ".join(real_name.strip().split())
        if not clean_name: raise HTTPException(400,"请填写真实姓名。")
        nickname = display_name.strip() or clean_name
        invite, err = core.validate_invite(invite_code, clean_name)
        if err: raise HTTPException(400, err)
        try:
            with site.db() as conn:
                cur=conn.execute("INSERT INTO community_users(username,display_name,email,password_salt,password_hash,role,active,created_at,updated_at) VALUES(?,?,NULL,?,?,?,1,?,?)",(clean_name,nickname,salt,digest,core.ROLE_XIAOFEIXIA,stamp,stamp)); uid=cur.lastrowid
        except Exception:
            raise HTTPException(409,"该姓名已注册。")
        core.mark_invite_used(invite["id"], uid)
    else:
        email=email.strip().lower(); name=display_name.strip()
        if not name: raise HTTPException(400,"请填写昵称。")
        if not email: raise HTTPException(400,"请填写邮箱。")
        try:
            with site.db() as conn:
                cur=conn.execute("INSERT INTO community_users(username,display_name,email,password_salt,password_hash,role,active,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?)",(email,name,email,salt,digest,core.ROLE_XIAOYOUXIA,stamp,stamp)); uid=cur.lastrowid
        except Exception:
            raise HTTPException(409,"这个邮箱已经注册。")
    resp=RedirectResponse('/',303); resp.set_cookie(core.USER_COOKIE,core.make_session(uid),httponly=True,secure=True,samesite="lax",max_age=7*86400); return resp


@router.post("/logout")
def logout():
    resp=RedirectResponse('/',303); resp.delete_cookie(core.USER_COOKIE); return resp


@router.get("/me", response_class=HTMLResponse)
def me(request: Request):
    core.init_db()
    user=login_required(request)
    with site.db() as conn:
        orders=conn.execute("SELECT o.*,t.name FROM orders o JOIN tools t ON t.id=o.tool_id WHERE o.user_id=? ORDER BY o.id DESC",(user['id'],)).fetchall()
        submissions=conn.execute("SELECT * FROM tool_submissions WHERE user_id=? ORDER BY id DESC",(user['id'],)).fetchall() if user['role']==core.ROLE_XIAOFEIXIA else []
        owned=conn.execute('''
            SELECT t.*,
                   (SELECT version FROM releases r WHERE r.tool_id=t.id AND r.active=1 ORDER BY r.id DESC LIMIT 1) current_version,
                   (SELECT COUNT(*) FROM reviews r WHERE r.tool_id=t.id) review_count,
                   (SELECT ROUND(AVG(rating),1) FROM reviews r WHERE r.tool_id=t.id) avg_rating,
                   (SELECT COUNT(*) FROM orders o WHERE o.tool_id=t.id AND o.status='paid' AND o.amount_cents>0) paid_orders,
                   (SELECT COALESCE(SUM(amount_cents),0) FROM orders o WHERE o.tool_id=t.id AND o.status='paid' AND o.amount_cents>0) paid_amount
            FROM tools t WHERE t.owner_user_id=? ORDER BY t.active DESC,t.name
        ''',(user['id'],)).fetchall() if user['role']==core.ROLE_XIAOFEIXIA else []
        currency=coin_core.currency_for_role(user['role'])
        coin_name=coin_core.label(currency)
        coin_balance=coin_core.balance(conn,user['id'],currency)
        coin_rows=coin_core.recent(conn,user['id'],currency)
        coin_earned=coin_core.earned(conn,user['id'],currency)

    order_rows=''.join(f'<tr><td>{site.esc(o["name"])}</td><td>¥{o["amount_cents"]/100:.2f}</td><td>{site.esc(o["status"])}</td></tr>' for o in orders) or '<tr><td colspan="3">暂无订单</td></tr>'
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
        <div class="dev-stats"><div class="dev-stat"><b>v{site.esc(version)}</b><span>当前版本</span></div><div class="dev-stat"><b>{coin_core.coin_price(t,coin_core.YOUXIA)}</b><span>院外游侠币</span></div><div class="dev-stat"><b>{int(t['downloads'] or 0):,}</b><span>累计下载</span></div><div class="dev-stat"><b>{rating} / 5</b><span>{reviews} 条评价</span></div><div class="dev-stat"><b>{paid_orders}</b><span>已确认购买</span></div><div class="dev-stat"><b>¥{paid_amount:.2f}</b><span>已确认销售额</span></div></div>
        <form class="coin-price-form" action="/account/tools/{site.esc(t['slug'])}/coin-price" method="post"><label>院内</label><input name="feixia_coin_price" type="number" min="0" max="{coin_core.MAX_PRICE}" step="1" value="{coin_core.coin_price(t,coin_core.FEIXIA)}" title="小飞侠下载需支付的飞侠币"><span class="coin-unit">飞侠币</span><label>院外</label><input name="youxia_coin_price" type="number" min="0" max="{coin_core.MAX_PRICE}" step="1" value="{coin_core.coin_price(t,coin_core.YOUXIA)}" title="小游侠下载需支付的游侠币"><span class="coin-unit">游侠币</span><button class="btn secondary">保存</button></form>
        <div class="dev-actions"><a class="btn" href="/developer/submit?tool={site.esc(t['slug'])}">提交新版本</a><a class="btn secondary" href="/tools/{site.esc(t['slug'])}">查看产品</a></div></div>''')

    led=''.join(f'<tr><td>{site.esc(coin_core.REASON_LABELS.get(r["reason"],r["reason"]))}</td><td>{site.esc(r["note"] or "—")}</td><td class="{"coin-plus" if int(r["delta"])>0 else "coin-minus"}">{"+" if int(r["delta"])>0 else ""}{int(r["delta"])}</td><td>{site.esc((r["created_at"] or "")[:10])}</td></tr>' for r in coin_rows) or f'<tr><td colspan="4">暂无{coin_name}记录</td></tr>'
    wallet_intro=(f'院内流通的开发者积分。工具审核通过可获得 {coin_core.PUBLISH_REWARD} 个；你的工具被其他小飞侠下载时，对方支付的飞侠币归你。'
                  if user['role']==core.ROLE_XIAOFEIXIA else
                  '院外下载使用的通用积分。解锁一次工具后永久可下载。余额不足请联系管理员充值。')
    coin_html=f'''<div class="community-card"><div class="dev-tool-head"><div><h2>{coin_name}钱包</h2><p class="muted">{wallet_intro}</p></div><div class="coin-balance"><b>{coin_balance}</b><span>当前余额</span></div></div>
    <div class="dev-stats" style="grid-template-columns:repeat(2,1fr)"><div class="dev-stat"><b>{coin_earned}</b><span>累计获得</span></div><div class="dev-stat"><b>{coin_earned-coin_balance}</b><span>累计消耗</span></div></div>
    <div class="section-title">最近流水</div><div class="table-wrap"><table class="table"><thead><tr><th>类型</th><th>说明</th><th>变动</th><th>时间</th></tr></thead><tbody>{led}</tbody></table></div></div>'''

    dev=''
    if user['role']==core.ROLE_XIAOFEIXIA:
        dev=f'''<div class="community-card"><div class="dev-tool-head"><div><h2>开发者中心</h2><p class="muted">每位小飞侠都可以提交新工具；已有工具的新版本只允许该工具原开发者提交。</p></div><a class="btn" href="/developer/submit">提交新工具</a></div>
        <div class="section-title">我的工具</div><div class="dev-tools">{''.join(tool_cards) if tool_cards else '<div class="notice">暂无已归属工具。提交新工具并审核通过后，会自动出现在这里。</div>'}</div>
        <div class="section-title">投稿记录</div><div class="table-wrap"><table class="table"><thead><tr><th>工具</th><th>类型</th><th>版本</th><th>状态</th></tr></thead><tbody>{sub_rows}</tbody></table></div></div>'''

    body=f'<div class="community-wrap"><div class="community-card"><span class="role">{core.role_label(user["role"])}</span><h1>{site.esc(user["display_name"])}</h1><p>{site.esc(user["email"] or "院内账号")}</p><form action="/account/logout" method="post"><button class="btn secondary">退出登录</button></form></div>{coin_html}{dev}<div class="community-card"><h2>我的购买</h2><div class="table-wrap"><table class="table"><tbody>{order_rows}</tbody></table></div></div></div>'
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
def create_order(request: Request, slug: str):
    user=login_required(request)
    if user['role']==core.ROLE_XIAOFEIXIA: return RedirectResponse(f'/tools/{slug}/download',303)
    with site.db() as conn:
        tool=conn.execute("SELECT * FROM tools WHERE slug=? AND active=1",(slug,)).fetchone()
        if not tool: raise HTTPException(404,"工具不存在。")
        if core.can_download(conn,user,tool): return RedirectResponse(f'/tools/{slug}/download',303)
        price=int(tool['price_cents'] or 0)
        if price<=0: raise HTTPException(409,"该工具的同行价格尚未配置，请联系管理员。")
        order_no='D100'+secrets.token_hex(8).upper(); cur=conn.execute("INSERT INTO orders(order_no,user_id,tool_id,amount_cents,status,created_at) VALUES(?,?,?,?,?,?)",(order_no,user['id'],tool['id'],price,'pending',core.now())); oid=cur.lastrowid
    return RedirectResponse(f'/account/orders/{oid}',303)


@router.post("/tools/{slug}/coin-unlock")
def coin_unlock(request: Request, slug: str):
    """Spend the balance matching your role to unlock a tool."""
    user = login_required(request)
    currency = coin_core.currency_for_role(user['role'])
    with site.db() as conn:
        tool = conn.execute("SELECT * FROM tools WHERE slug=? AND active=1", (slug,)).fetchone()
        if not tool:
            raise HTTPException(404, "工具不存在。")
        coin_core.purchase(conn, user, tool, currency)
    return RedirectResponse(f'/tools/{slug}', 303)


@router.post("/tools/{slug}/coin-price")
def set_coin_price(request: Request, slug: str, feixia_coin_price: int = Form(0),
                   youxia_coin_price: int = Form(0)):
    """Tool owners set what 院内 and 院外 downloaders pay."""
    user = developer_required(request)
    for value in (feixia_coin_price, youxia_coin_price):
        if value < 0 or value > coin_core.MAX_PRICE:
            raise HTTPException(400, f"价格需在 0—{coin_core.MAX_PRICE} 之间。")
    with site.db() as conn:
        tool = conn.execute("SELECT * FROM tools WHERE slug=?", (slug,)).fetchone()
        if not tool:
            raise HTTPException(404, "工具不存在。")
        if not core.is_tool_owner(tool, user):
            raise HTTPException(403, "只有该工具的开发者可以设置价格。")
        conn.execute("UPDATE tools SET feixia_coin_price=?,youxia_coin_price=?,updated_at=? WHERE id=?",
                     (feixia_coin_price, youxia_coin_price, core.now(), tool['id']))
    return RedirectResponse('/account/me', 303)


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_page(request: Request, order_id: int):
    user=login_required(request)
    with site.db() as conn:
        o=conn.execute("SELECT o.*,t.name,t.slug FROM orders o JOIN tools t ON t.id=o.tool_id WHERE o.id=? AND o.user_id=?",(order_id,user['id'])).fetchone()
    if not o: raise HTTPException(404,"订单不存在。")
    body=f'''<div class="community-wrap"><div class="community-card"><div class="eyebrow">订单 {site.esc(o['order_no'])}</div><h1>{site.esc(o['name'])}</h1><div class="price">¥{o['amount_cents']/100:.2f}</div>
    <div class="notice" style="margin-top:18px">订单系统已经建立。微信/支付宝正式支付需要配置商户号和支付回调后才会开放；现在不会伪造“已付款”。</div><a class="btn secondary" href="/tools/{site.esc(o['slug'])}">返回工具</a></div></div>'''
    return HTMLResponse(page(body,"订单 · 小飞侠设计100%"))


developer_router=APIRouter()


@developer_router.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request, tool: str = ""):
    core.init_db(); user=developer_required(request)
    with site.db() as conn:
        tools=conn.execute("SELECT id,name,slug,price_cents FROM tools WHERE owner_user_id=? ORDER BY active DESC,name",(user['id'],)).fetchall()
    selected_slug=tool.strip()
    opts=''.join(f'<option value="{site.esc(t["slug"])}" {"selected" if t["slug"]==selected_slug else ""}>{site.esc(t["name"])} · ¥{int(t["price_cents"] or 0)/100:.2f}</option>' for t in tools)
    default_type='new_release' if selected_slug and any(t['slug']==selected_slug for t in tools) else 'new_tool'
    category_opts=''.join(f'<option value="{site.esc(c)}">{site.esc(c)}</option>' for c in core.TOOL_CATEGORIES)
    body=f'''<div class="community-wrap"><div class="community-card"><span class="role">小飞侠开发者</span><h1>提交工具 / 新版本</h1><div class="notice">新工具可自行提交；已有工具的新版本只允许原开发者提交。网页工具提交后由管理员审核上架。</div>
    <form action="/developer/submit" method="post" enctype="multipart/form-data"><div class="field"><label>投稿类型</label><select name="submission_type" id="sub-type"><option value="new_tool" {"selected" if default_type=="new_tool" else ""}>新桌面工具</option><option value="new_web_app">新网页工具（小飞侠 Cloud）</option><option value="new_release" {"selected" if default_type=="new_release" else ""}>已有工具新版本</option></select></div>
    <div class="field" id="field-existing"><label>已有工具（仅显示你自己的工具）</label><select name="existing_slug"><option value="">—</option>{opts}</select></div><div class="community-grid"><div><div class="field"><label>工具名称</label><input name="name"></div><div class="field"><label>一句话介绍</label><input name="tagline"></div><div class="field"><label>分类</label><select name="category">{category_opts}</select></div></div><div><div class="field" id="field-platform"><label>平台</label><input name="platform" value="Windows"></div><div class="field"><label>图标文字</label><input name="icon_text" value="100"></div><div class="field" id="field-price"><label>院内价格 · 飞侠币（0 = 免费）</label><input name="feixia_coin_price" type="number" min="0" max="{coin_core.MAX_PRICE}" step="1" value="0"></div><div class="field" id="field-price-out"><label>院外价格 · 游侠币</label><input name="youxia_coin_price" type="number" min="0" max="{coin_core.MAX_PRICE}" step="1" value="0"><div class="muted" style="margin-top:5px">下载者支付的币值全部归你。审核通过还会获得 {coin_core.PUBLISH_REWARD} 个飞侠币发布奖励。</div></div><div class="field"><label>版本号</label><input name="version" required></div></div></div>
    <div class="field"><label>完整介绍</label><textarea name="description"></textarea></div><div class="field"><label>更新说明</label><textarea name="notes"></textarea></div><div class="field" id="field-package"><label>安装包（仅支持 .zip）</label><input name="package" type="file" accept=".zip"></div><div class="field" id="field-appurl" style="display:none"><label>工具访问地址</label><input name="app_url" placeholder="https://your-app.example.com"></div><button class="btn">提交审核</button></form></div></div>
    <script>!function(){{const s=document.getElementById('sub-type'),pkg=document.getElementById('field-package'),url=document.getElementById('field-appurl'),plat=document.getElementById('field-platform'),ex=document.getElementById('field-existing'),pr=document.getElementById('field-price'),pro=document.getElementById('field-price-out');function u(){{const v=s.value,web=v==='new_web_app';pkg.style.display=web?'none':'';url.style.display=web?'':'none';plat.style.display=web?'none':'';ex.style.display=v==='new_release'?'':'none';if(web){{plat.querySelector('input').value='Web';pr.querySelector('input').value='0';pro.querySelector('input').value='0'}}else{{plat.querySelector('input').value='Windows'}}const fi=pkg.querySelector('input');if(fi)fi.required=!web&&v!=='new_release'}}s.addEventListener('change',u);u()}}()</script>'''
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
            currency=coin_core.currency_for_role(user['role']) if user else coin_core.YOUXIA
            coin_cost=coin_core.coin_price(t,currency)
            coin_name=coin_core.label(currency)
            coin_balance=coin_core.balance(conn,user['id'],currency) if user else 0
            feixia_cost=coin_core.coin_price(t,coin_core.FEIXIA)
            youxia_cost=coin_core.coin_price(t,coin_core.YOUXIA)
        version=rel['version'] if rel else '待发布'; developer=t['developer_name'] or '小飞侠开发者'; price=int(t['price_cents'] or 0)
        tool_type=t['tool_type'] if 'tool_type' in t.keys() else 'desktop'
        app_url=t['app_url'] if 'app_url' in t.keys() else ''
        is_web=tool_type=='web_app' and app_url
        if is_web:
            action=f'<a class="btn" href="{site.esc(app_url)}" target="_blank" rel="noopener">立即使用 →</a>'
        elif not user: action=f'<a class="btn" href="/account/login?next=/tools/{site.esc(slug)}">登录后下载</a>'
        elif allowed: action=f'<a class="btn" href="/tools/{site.esc(slug)}/download">下载 · v{site.esc(version)}</a>'
        elif coin_cost>0:
            affordable=coin_balance>=coin_cost
            action=(f'<form action="/account/tools/{site.esc(slug)}/coin-unlock" method="post"><button class="btn">花费 {coin_cost} {coin_name}下载</button></form>'
                    if affordable else f'<span class="btn" style="background:#999">需要 {coin_cost} {coin_name}（余额 {coin_balance}）</span>')
            hint='' if affordable else ('　发布工具可获得飞侠币。' if user['role']==core.ROLE_XIAOFEIXIA else '　请联系管理员充值游侠币。')
            action+=f'<div class="muted" style="margin-top:9px">当前余额 {coin_balance} {coin_name} · 一次解锁后永久可下载{hint}</div>'
        else: action=f'<span class="btn" style="background:#999">{coin_name}价格待配置</span>'
        review_html=''.join(f'<div class="review"><div><b>{site.esc(r["display_name"])}</b> · <span class="stars">{"★"*int(r["rating"])}{"☆"*(5-int(r["rating"]))}</span></div><p>{site.esc(r["content"])}</p></div>' for r in reviews) or '<p>暂无评价，欢迎成为第一个评价的人。</p>'
        review_form=f'''<form action="/account/tools/{site.esc(slug)}/review" method="post"><div class="field"><label>评分 1-5</label><input name="rating" type="number" min="1" max="5" value="5" required></div><div class="field"><label>留言</label><textarea name="content"></textarea></div><button class="btn secondary">发布评价</button></form>''' if user else '<a class="btn secondary" href="/account/login?next=/tools/'+site.esc(slug)+'">登录后评价</a>'
        role_nav=(f'<a class="admin-link" href="/account/me">{site.esc(user["display_name"])} · {core.role_label(user["role"])}</a>' if user else '<a class="admin-link" href="/account/login">登录 / 注册</a>')
        nav_html=site.nav().replace('<a class="admin-link" href="/manage">管理</a>',role_nav)
        platform_label='Web · 小飞侠 Cloud' if is_web else t['platform']
        if is_web:
            obtain_text='小飞侠 Cloud 网页工具，打开即用，无需下载安装。'
            obtain_price='☁️ 在线使用'
        else:
            inner=f'{feixia_cost} 飞侠币' if feixia_cost>0 else '院内免费'
            outer=f'{youxia_cost} 游侠币' if youxia_cost>0 else '价格待配置'
            obtain_text=f'小飞侠（院内）：{inner}\n小游侠（院外）：{outer}\n解锁一次后永久可下载，币值收入归开发者。'
            obtain_price=(f'{coin_cost} {coin_name}' if coin_cost>0 else
                          ('院内免费' if user and user['role']==core.ROLE_XIAOFEIXIA else '价格待配置'))
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
