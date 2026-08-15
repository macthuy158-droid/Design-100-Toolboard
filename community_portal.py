import hashlib
import secrets
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import app_v2 as site
import community_core as core

router = APIRouter()

EXTRA_CSS = '''<style>
.memberbar{display:flex;gap:8px;align-items:center}.member-pill{padding:8px 12px;border-radius:999px;background:#fff;border:1px solid #dededb;font-size:11px}.community-wrap{width:min(980px,calc(100% - 36px));margin:42px auto 80px}.community-card{background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:26px;margin-bottom:16px}.community-card h1,.community-card h2{margin-top:0}.community-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.review{padding:15px 0;border-top:1px solid #eee}.review:first-of-type{border-top:0}.stars{letter-spacing:2px;font-size:13px}.notice{padding:12px 14px;border-radius:12px;background:#f3f3f0;font-size:11px;color:#666;margin-bottom:15px}.price{font-size:24px;font-weight:760}.role{font-size:10px;padding:5px 8px;border-radius:999px;background:#111;color:#fff}.dev-actions{display:flex;gap:8px;flex-wrap:wrap}.dev-tools{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin:16px 0 24px}.dev-tool{border:1px solid #e8e8e5;border-radius:19px;padding:18px;background:#fbfbfa}.dev-tool-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.dev-tool h3{margin:0 0 5px;font-size:19px}.dev-tool-sub{font-size:10px;color:#8c8e92}.dev-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:15px 0}.dev-stat{background:#f0f0ed;border-radius:12px;padding:10px;min-width:0}.dev-stat b{display:block;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dev-stat span{display:block;font-size:8px;color:#92949a;margin-top:2px}.status-dot{font-size:9px;border-radius:999px;padding:5px 8px;background:#ebf4ec;color:#2f6f3b;white-space:nowrap}.status-dot.off{background:#f3e5e5;color:#8b3535}.section-title{font-size:13px;color:#777;font-weight:720;margin:24px 0 10px}.table-wrap{overflow-x:auto}.small-link{font-size:10px;color:#555;text-decoration:underline;text-underline-offset:3px}.muted{font-size:11px;color:#888;line-height:1.7}@media(max-width:700px){.community-grid,.dev-tools{grid-template-columns:1fr}.dev-stats{grid-template-columns:1fr 1fr}}</style>'''


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
    <div class="notice">院内小飞侠：用户名和初始密码均为本人姓名。同行用户请先注册成为小游侠。</div>
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
    body='''<div class="loginwrap"><div class="login"><div class="eyebrow">小游侠 · PEER USER</div><h1>注册同行用户</h1>
    <form action="/account/register" method="post"><div class="field"><label>昵称</label><input name="display_name" required></div><div class="field"><label>邮箱</label><input name="email" type="email" required></div>
    <div class="field"><label>密码</label><input name="password" type="password" minlength="6" required></div><button class="btn">注册小游侠</button></form></div></div>'''
    return HTMLResponse(page(body,"小游侠注册 · 小飞侠设计100%"))


@router.post("/register")
def register(display_name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    core.init_db()
    if len(password)<6: raise HTTPException(400,"密码至少 6 位。")
    email=email.strip().lower(); name=display_name.strip(); salt,digest=core.hash_password(password); stamp=core.now()
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
        <div class="dev-stats"><div class="dev-stat"><b>v{site.esc(version)}</b><span>当前版本</span></div><div class="dev-stat"><b>¥{int(t['price_cents'] or 0)/100:.2f}</b><span>同行售价</span></div><div class="dev-stat"><b>{int(t['downloads'] or 0):,}</b><span>累计下载</span></div><div class="dev-stat"><b>{rating} / 5</b><span>{reviews} 条评价</span></div><div class="dev-stat"><b>{paid_orders}</b><span>已确认购买</span></div><div class="dev-stat"><b>¥{paid_amount:.2f}</b><span>已确认销售额</span></div></div>
        <div class="dev-actions"><a class="btn" href="/developer/submit?tool={site.esc(t['slug'])}">提交新版本</a><a class="btn secondary" href="/tools/{site.esc(t['slug'])}">查看产品</a></div></div>''')

    dev=''
    if user['role']==core.ROLE_XIAOFEIXIA:
        dev=f'''<div class="community-card"><div class="dev-tool-head"><div><h2>开发者中心</h2><p class="muted">每位小飞侠都可以提交新工具；已有工具的新版本只允许该工具原开发者提交。</p></div><a class="btn" href="/developer/submit">提交新工具</a></div>
        <div class="section-title">我的工具</div><div class="dev-tools">{''.join(tool_cards) if tool_cards else '<div class="notice">暂无已归属工具。提交新工具并审核通过后，会自动出现在这里。</div>'}</div>
        <div class="section-title">投稿记录</div><div class="table-wrap"><table class="table"><thead><tr><th>工具</th><th>类型</th><th>版本</th><th>状态</th></tr></thead><tbody>{sub_rows}</tbody></table></div></div>'''

    body=f'<div class="community-wrap"><div class="community-card"><span class="role">{core.role_label(user["role"])}</span><h1>{site.esc(user["display_name"])}</h1><p>{site.esc(user["email"] or "院内账号")}</p><form action="/account/logout" method="post"><button class="btn secondary">退出登录</button></form></div>{dev}<div class="community-card"><h2>我的购买</h2><div class="table-wrap"><table class="table"><tbody>{order_rows}</tbody></table></div></div></div>'
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
    body=f'''<div class="community-wrap"><div class="community-card"><span class="role">小飞侠开发者</span><h1>提交工具 / 新版本</h1><div class="notice">新工具可自行提交；已有工具的新版本只允许原开发者提交。价格为产品当前同行售价，审核通过后同步更新。</div>
    <form action="/developer/submit" method="post" enctype="multipart/form-data"><div class="field"><label>投稿类型</label><select name="submission_type"><option value="new_tool" {"selected" if default_type=="new_tool" else ""}>新工具</option><option value="new_release" {"selected" if default_type=="new_release" else ""}>已有工具新版本</option></select></div>
    <div class="field"><label>已有工具（仅显示你自己的工具）</label><select name="existing_slug"><option value="">—</option>{opts}</select></div><div class="community-grid"><div><div class="field"><label>工具名称</label><input name="name"></div><div class="field"><label>Slug</label><input name="slug" placeholder="例如 text-100"></div><div class="field"><label>一句话介绍</label><input name="tagline"></div><div class="field"><label>分类</label><input name="category" value="效率工具"></div></div><div><div class="field"><label>平台</label><input name="platform" value="Windows"></div><div class="field"><label>图标文字</label><input name="icon_text" value="100"></div><div class="field"><label>同行价格（元）</label><input name="price_yuan" type="number" min="0.01" step="0.01" required></div><div class="field"><label>版本号</label><input name="version" required></div></div></div>
    <div class="field"><label>完整介绍</label><textarea name="description"></textarea></div><div class="field"><label>更新说明</label><textarea name="notes"></textarea></div><div class="field"><label>安装包（仅支持 .zip）</label><input name="package" type="file" accept=".zip" required></div><button class="btn">提交审核</button></form></div></div>'''
    return HTMLResponse(page(body,"开发者投稿 · 小飞侠设计100%"))


@developer_router.post("/submit")
async def submit(request: Request, submission_type: str=Form(...), existing_slug: str=Form(""), name: str=Form(""), slug: str=Form(""), tagline: str=Form(""), description: str=Form(""), category: str=Form("效率工具"), platform: str=Form("Windows"), icon_text: str=Form("100"), price_yuan: float=Form(...), version: str=Form(...), notes: str=Form(""), package: UploadFile=File(...)):
    core.init_db(); user=developer_required(request); content=await package.read()
    if not content or len(content)>core.MAX_UPLOAD_BYTES: raise HTTPException(400,"安装包为空或超过大小限制。")
    if price_yuan<=0: raise HTTPException(400,"同行价格必须大于 0 元。")
    with site.db() as conn:
        tool=None
        if submission_type=='new_release':
            tool=conn.execute("SELECT * FROM tools WHERE slug=?",(existing_slug.strip(),)).fetchone()
            if not tool: raise HTTPException(404,"已有工具不存在。")
            if not core.is_tool_owner(tool,user): raise HTTPException(403,"只有该工具原开发者可以提交新版本。")
            name=tool['name']; slug=tool['slug']; tagline=tool['tagline']; description=tool['description']; category=tool['category']; platform=tool['platform']; icon_text=tool['icon_text']
        elif submission_type=='new_tool':
            slug=slug.strip().lower()
            if not core.VALID_SLUG.match(slug): raise HTTPException(400,"Slug 只能使用小写英文、数字和短横线。")
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
        if not user: action=f'<a class="btn" href="/account/login?next=/tools/{site.esc(slug)}">登录后下载</a>'
        elif allowed: action=f'<a class="btn" href="/tools/{site.esc(slug)}/download">下载 · v{site.esc(version)}</a>'
        elif user['role']==core.ROLE_XIAOYOUXIA and price>0: action=f'<form action="/account/tools/{site.esc(slug)}/order" method="post"><button class="btn">购买 ¥{price/100:.2f}</button></form>'
        elif user['role']==core.ROLE_XIAOYOUXIA: action='<span class="btn" style="background:#999">价格待配置</span>'
        else: action=''
        review_html=''.join(f'<div class="review"><div><b>{site.esc(r["display_name"])}</b> · <span class="stars">{"★"*int(r["rating"])}{"☆"*(5-int(r["rating"]))}</span></div><p>{site.esc(r["content"])}</p></div>' for r in reviews) or '<p>暂无评价，欢迎成为第一个评价的人。</p>'
        review_form=f'''<form action="/account/tools/{site.esc(slug)}/review" method="post"><div class="field"><label>评分 1-5</label><input name="rating" type="number" min="1" max="5" value="5" required></div><div class="field"><label>留言</label><textarea name="content"></textarea></div><button class="btn secondary">发布评价</button></form>''' if user else '<a class="btn secondary" href="/account/login?next=/tools/'+site.esc(slug)+'">登录后评价</a>'
        role_nav=(f'<a class="admin-link" href="/account/me">{site.esc(user["display_name"])} · {core.role_label(user["role"])}</a>' if user else '<a class="admin-link" href="/account/login">登录 / 注册</a>')
        nav_html=site.nav().replace('<a class="admin-link" href="/manage">管理</a>',role_nav)
        body=nav_html+f'''<div class="shell"><section class="detail-hero"><a class="back" href="/">← 返回 Desgin 100%</a><div class="product"><div><div class="eyebrow">{site.esc(t['category'])} · {site.esc(t['platform'])}</div><h1>{site.esc(t['name'])}</h1><div class="lead">{site.esc(t['tagline'])}</div><div class="facts"><div class="fact"><b>v{site.esc(version)}</b><span>当前版本</span></div><div class="fact"><b>{int(t['downloads']):,}</b><span>累计下载</span></div><div class="fact"><b>{site.esc(developer)}</b><span>开发者</span></div><div class="fact"><b>{(str(round(avg['a'],1))+' / 5') if avg['c'] else '—'}</b><span>{avg['c']} 条评价</span></div></div>{action}</div><div class="product-icon">{site.esc(t['icon_text'])}</div></div></section><section class="detail-grid"><div class="panel"><h2>工具介绍</h2><p>{site.esc(t['description'])}</p></div><div class="panel"><h2>获取方式</h2><p>小飞侠：院内账号免费下载。\n小游侠：注册后按产品价格购买下载。</p><div class="price">{'院内免费' if user and user['role']==core.ROLE_XIAOFEIXIA else ('¥%.2f'%(price/100))}</div></div></section><section id="reviews" class="panel" style="margin-bottom:80px"><h2>评价与留言</h2>{review_form}<div style="margin-top:24px">{review_html}</div></section></div>'''
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
