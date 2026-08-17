import re
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v2 as site
import community_core as core

router = APIRouter(prefix="/bounties")

STATUSES = {"open": "招募中", "in_progress": "开发中", "completed": "已完成", "cancelled": "已取消"}
DELIVERABLES = ["Windows EXE", "CAD 插件", "网页工具", "Figma 插件", "Python 脚本", "其他"]

CSS = r'''<style>
.bw{width:min(1080px,calc(100% - 36px));margin:42px auto 80px}.bh{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;margin-bottom:20px}.bh h1{margin:5px 0 8px;font-size:34px}.ey{font-size:10px;letter-spacing:.14em;color:#888;font-weight:800}.lead{font-size:12px;color:#777;line-height:1.8;max-width:680px}.actions,.filters{display:flex;gap:8px;flex-wrap:wrap}.filters{margin-bottom:18px}.pill{padding:8px 11px;border-radius:999px;border:1px solid #ddd;background:#fff;font-size:10px}.pill.on{background:#111;color:#fff;border-color:#111}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.card,.panel{background:#fff;border:1px solid #e6e6e3;border-radius:22px;padding:22px}.card{display:block;color:#111}.card h2{font-size:21px;margin:8px 0;line-height:1.35}.head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.tag,.status{display:inline-flex;padding:5px 8px;border-radius:999px;background:#f0f0ed;font-size:9px}.status{background:#ebf4ec;color:#2f6f3b}.status.in_progress{background:#e8eef9;color:#315b9b}.status.completed{background:#ecebea;color:#555}.status.cancelled{background:#f3e5e5;color:#8b3535}.money{font-size:28px;font-weight:800;margin:17px 0 4px}.meta{font-size:10px;color:#888;line-height:1.7}.desc{font-size:12px;color:#666;line-height:1.75;min-height:44px}.stats{display:flex;gap:16px;flex-wrap:wrap;margin-top:14px;padding-top:12px;border-top:1px solid #eee;font-size:10px;color:#777}.layout{display:grid;grid-template-columns:1.4fr .8fr;gap:16px}.body{white-space:pre-wrap;font-size:13px;line-height:1.9;color:#444}.response{padding:15px 0;border-top:1px solid #eee}.response:first-child{border-top:0}.note{padding:12px 14px;border-radius:14px;background:#f3f3f0;color:#666;font-size:11px;line-height:1.7;margin-bottom:16px}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:10px 8px;border-bottom:1px solid #eee;text-align:left;font-size:11px}.empty{padding:28px;border:1px dashed #ddd;border-radius:16px;color:#888;text-align:center;font-size:12px}@media(max-width:760px){.grid,.layout,.formgrid{grid-template-columns:1fr}.bh{align-items:flex-start;flex-direction:column}}
</style>'''


def page(body, title="需求广场 · 小飞侠设计100%"):
    return site.page(CSS + body, title)


def init_db():
    core.init_db()
    with site.db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS bounties(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          category TEXT NOT NULL DEFAULT '其他',
          description TEXT NOT NULL,
          deliverable TEXT NOT NULL DEFAULT '其他',
          reference_url TEXT NOT NULL DEFAULT '',
          budget_cents INTEGER NOT NULL DEFAULT 0,
          deadline TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'open',
          accepted_response_id INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES community_users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bounty_responses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          bounty_id INTEGER NOT NULL,
          developer_user_id INTEGER NOT NULL,
          proposal TEXT NOT NULL,
          estimated_days INTEGER NOT NULL DEFAULT 0,
          quote_cents INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'proposed',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(bounty_id,developer_user_id),
          FOREIGN KEY(bounty_id) REFERENCES bounties(id) ON DELETE CASCADE,
          FOREIGN KEY(developer_user_id) REFERENCES community_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_bounties_status ON bounties(status,id DESC);
        CREATE INDEX IF NOT EXISTS idx_bounties_user ON bounties(user_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_bounty_responses_bounty ON bounty_responses(bounty_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_bounty_responses_dev ON bounty_responses(developer_user_id,id DESC);
        ''')


def user(request):
    return core.current_user(request)


def login_redirect(path):
    return RedirectResponse('/account/login?' + urlencode({'next': path}), 303)


def badge(status):
    return f'<span class="status {site.esc(status)}">{site.esc(STATUSES.get(status,status))}</span>'


def money(cents):
    return f'¥{int(cents or 0)/100:,.0f}'


def safe_url(value):
    value=value.strip()
    if not value:
        return ''
    if not re.match(r'^https?://',value,re.I):
        raise HTTPException(400,'参考链接必须以 http:// 或 https:// 开头。')
    return value[:1200]


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
def list_bounties(request: Request, category: str='', status: str='open'):
    init_db(); where=[]; params=[]
    if category and category in core.TOOL_CATEGORIES:
        where.append('b.category=?'); params.append(category)
    if status in STATUSES:
        where.append('b.status=?'); params.append(status)
    elif status!='all':
        status='open'; where.append("b.status='open'")
    clause='WHERE '+' AND '.join(where) if where else ''
    with site.db() as conn:
        rows=conn.execute(f'''SELECT b.*,u.display_name,(SELECT COUNT(*) FROM bounty_responses r WHERE r.bounty_id=b.id) response_count FROM bounties b JOIN community_users u ON u.id=b.user_id {clause} ORDER BY CASE b.status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,b.id DESC''',params).fetchall()
    sf=''.join(f'<a class="pill {"on" if status==k else ""}" href="/bounties?{urlencode({"status":k,"category":category})}">{v}</a>' for k,v in [('open','招募中'),('in_progress','开发中'),('completed','已完成'),('all','全部')])
    cf='<a class="pill {}" href="/bounties?{}">全部分类</a>'.format('on' if not category else '',urlencode({'status':status})) + ''.join(f'<a class="pill {"on" if category==c else ""}" href="/bounties?{urlencode({"status":status,"category":c})}">{site.esc(c)}</a>' for c in core.TOOL_CATEGORIES)
    cards=[]
    for b in rows:
        preview=(b['description'] or '').strip().replace('\n',' ')
        if len(preview)>92: preview=preview[:92]+'…'
        cards.append(f'''<a class="card" href="/bounties/{b['id']}"><div class="head"><div><span class="tag">{site.esc(b['category'])}</span><h2>{site.esc(b['title'])}</h2></div>{badge(b['status'])}</div><div class="desc">{site.esc(preview)}</div><div class="money">{money(b['budget_cents'])}</div><div class="meta">悬赏金额 · 期望交付：{site.esc(b['deliverable'])}</div><div class="stats"><span>{int(b['response_count'] or 0)} 个响应</span><span>截止 {site.esc(b['deadline'] or '不限')}</span><span>{site.esc(b['display_name'])}</span></div></a>''')
    u=user(request); primary='<a class="btn" href="/bounties/new">发布需求</a>' if u else '<a class="btn" href="/account/login?next=/bounties/new">登录后发布</a>'; mine='<a class="btn secondary" href="/bounties/mine">我的需求</a>' if u else ''
    body=f'''<div class="bw"><div class="bh"><div><div class="ey">DESIGN 100% · BOUNTY</div><h1>需求广场</h1><div class="lead">把还没有被解决的设计工作流问题公开出来。用户发布悬赏，小飞侠提交解决方案，优秀成果可以继续沉淀为平台工具。</div></div><div class="actions">{mine}{primary}</div></div><div class="filters">{sf}</div><div class="filters">{cf}</div><div class="grid">{''.join(cards) if cards else '<div class="empty">暂时没有符合条件的需求。</div>'}</div></div>'''
    return HTMLResponse(page(body))


@router.get('/new', response_class=HTMLResponse)
def new_bounty(request: Request):
    if not user(request): return login_redirect('/bounties/new')
    cats=''.join(f'<option value="{site.esc(c)}">{site.esc(c)}</option>' for c in core.TOOL_CATEGORIES)
    dels=''.join(f'<option value="{site.esc(d)}">{site.esc(d)}</option>' for d in DELIVERABLES)
    body=f'''<div class="bw"><div class="bh"><div><div class="ey">NEW BOUNTY</div><h1>发布需求</h1><div class="lead">描述真实工作中的问题，设置悬赏金额，让合适的小飞侠来解决。</div></div><a class="btn secondary" href="/bounties">返回需求广场</a></div><div class="panel"><div class="note">当前金额为悬赏意向，不代表平台已收款或托管；统一支付接入后再升级为资金托管结算。</div><form action="/bounties/new" method="post"><div class="field"><label>需求名称</label><input name="title" maxlength="120" required></div><div class="formgrid"><div class="field"><label>分类</label><select name="category">{cats}</select></div><div class="field"><label>期望交付</label><select name="deliverable">{dels}</select></div><div class="field"><label>悬赏金额（元）</label><input name="budget_yuan" type="number" min="1" max="1000000" step="1" required></div><div class="field"><label>截止日期（可选）</label><input name="deadline" type="date"></div></div><div class="field"><label>需求说明</label><textarea name="description" rows="10" maxlength="10000" required></textarea></div><div class="field"><label>参考链接（可选）</label><input name="reference_url" placeholder="https://..."></div><button class="btn">发布悬赏</button></form></div></div>'''
    return HTMLResponse(page(body,'发布需求 · 小飞侠设计100%'))


@router.post('/new')
def create_bounty(request: Request,title: str=Form(...),category: str=Form('其他'),description: str=Form(...),deliverable: str=Form('其他'),budget_yuan: float=Form(...),deadline: str=Form(''),reference_url: str=Form('')):
    init_db(); u=user(request)
    if not u: return login_redirect('/bounties/new')
    title=title.strip(); description=description.strip()
    if not title or len(title)>120: raise HTTPException(400,'需求名称不能为空，且最多 120 字。')
    if not description or len(description)>10000: raise HTTPException(400,'需求说明不能为空，且最多 10000 字。')
    if category not in core.TOOL_CATEGORIES: raise HTTPException(400,'请选择有效分类。')
    if deliverable not in DELIVERABLES: raise HTTPException(400,'请选择有效交付形式。')
    if budget_yuan<1 or budget_yuan>1000000: raise HTTPException(400,'悬赏金额需在 1—1,000,000 元之间。')
    stamp=core.now()
    with site.db() as conn:
        cur=conn.execute('''INSERT INTO bounties(user_id,title,category,description,deliverable,reference_url,budget_cents,deadline,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,'open',?,?)''',(u['id'],title,category,description,deliverable,safe_url(reference_url),int(round(budget_yuan*100)),deadline.strip()[:10],stamp,stamp)); bid=cur.lastrowid
    return RedirectResponse(f'/bounties/{bid}',303)


@router.get('/mine', response_class=HTMLResponse)
def mine(request: Request):
    init_db(); u=user(request)
    if not u: return login_redirect('/bounties/mine')
    with site.db() as conn:
        own=conn.execute('''SELECT b.*,(SELECT COUNT(*) FROM bounty_responses r WHERE r.bounty_id=b.id) response_count FROM bounties b WHERE b.user_id=? ORDER BY b.id DESC''',(u['id'],)).fetchall()
        responses=conn.execute('''SELECT r.*,b.title,b.status bounty_status FROM bounty_responses r JOIN bounties b ON b.id=r.bounty_id WHERE r.developer_user_id=? ORDER BY r.id DESC''',(u['id'],)).fetchall() if u['role']==core.ROLE_XIAOFEIXIA else []
    own_rows=''.join(f'<tr><td><a href="/bounties/{b["id"]}">{site.esc(b["title"])}</a></td><td>{money(b["budget_cents"])}</td><td>{site.esc(STATUSES.get(b["status"],b["status"]))}</td><td>{int(b["response_count"] or 0)}</td></tr>' for b in own) or '<tr><td colspan="4">暂无发布需求</td></tr>'
    dev=''
    if u['role']==core.ROLE_XIAOFEIXIA:
        rr=''.join(f'<tr><td><a href="/bounties/{r["bounty_id"]}">{site.esc(r["title"])}</a></td><td>{site.esc("已选中" if r["status"]=="accepted" else "已提交")}</td><td>{site.esc(STATUSES.get(r["bounty_status"],r["bounty_status"]))}</td></tr>' for r in responses) or '<tr><td colspan="3">暂无响应</td></tr>'
        dev=f'<div class="panel"><h2>我响应的需求</h2><table class="table"><thead><tr><th>需求</th><th>方案状态</th><th>需求状态</th></tr></thead><tbody>{rr}</tbody></table></div>'
    body=f'<div class="bw"><div class="bh"><div><div class="ey">MY BOUNTIES</div><h1>我的需求</h1></div><div class="actions"><a class="btn" href="/bounties/new">发布需求</a><a class="btn secondary" href="/bounties">需求广场</a></div></div><div class="panel"><h2>我发布的需求</h2><table class="table"><thead><tr><th>需求</th><th>悬赏</th><th>状态</th><th>响应</th></tr></thead><tbody>{own_rows}</tbody></table></div>{dev}</div>'
    return HTMLResponse(page(body,'我的需求 · 小飞侠设计100%'))


@router.get('/{bounty_id}', response_class=HTMLResponse)
def detail(request: Request,bounty_id: int):
    init_db(); u=user(request)
    with site.db() as conn:
        b=conn.execute('SELECT b.*,u.display_name FROM bounties b JOIN community_users u ON u.id=b.user_id WHERE b.id=?',(bounty_id,)).fetchone()
        if not b: raise HTTPException(404,'需求不存在。')
        rs=conn.execute('SELECT r.*,u.display_name FROM bounty_responses r JOIN community_users u ON u.id=r.developer_user_id WHERE r.bounty_id=? ORDER BY CASE r.status WHEN "accepted" THEN 0 ELSE 1 END,r.id DESC',(bounty_id,)).fetchall()
    owner=bool(u and int(u['id'])==int(b['user_id'])); own=next((r for r in rs if u and int(r['developer_user_id'])==int(u['id'])),None); can=bool(u and u['role']==core.ROLE_XIAOFEIXIA and not owner and b['status']=='open')
    ref=f'<p><a href="{site.esc(b["reference_url"])}" target="_blank" rel="noopener noreferrer">打开参考链接 ↗</a></p>' if b['reference_url'] else ''
    items=[]
    for r in (rs if owner else ([own] if own else [])):
        if not r: continue
        action=f'<form action="/bounties/{bounty_id}/accept/{r["id"]}" method="post"><button class="btn">选中该开发者</button></form>' if owner and b['status']=='open' and r['status']!='accepted' else ''
        state='已选中' if r['status']=='accepted' else '已提交'
        items.append(f'<div class="response"><div class="head"><div><b>{site.esc(r["display_name"])}</b><div class="meta">预计 {int(r["estimated_days"])} 天 · 报价 {money(r["quote_cents"]) if int(r["quote_cents"] or 0)>0 else "按悬赏金额"} · {state}</div></div>{action}</div><div class="body">{site.esc(r["proposal"])}</div></div>')
    response=''
    if owner: response=f'<div class="panel"><h2>开发者方案 <span class="meta">{len(rs)} 个响应</span></h2>{"".join(items) if items else "<div class=empty>暂时还没有开发者提交方案。</div>"}</div>'
    elif own: response=f'<div class="panel"><h2>我的方案</h2>{"".join(items)}</div>'
    elif can: response=f'''<div class="panel"><h2>提交解决方案</h2><form action="/bounties/{bounty_id}/respond" method="post"><div class="field"><label>方案说明</label><textarea name="proposal" rows="7" maxlength="5000" required></textarea></div><div class="formgrid"><div class="field"><label>预计完成周期（天）</label><input name="estimated_days" type="number" min="1" max="365" value="7" required></div><div class="field"><label>报价（元，可选）</label><input name="quote_yuan" type="number" min="0" step="1" value="0"></div></div><button class="btn">提交方案</button></form></div>'''
    elif not u and b['status']=='open': response=f'<div class="panel"><h2>想解决这个需求？</h2><a class="btn" href="/account/login?next=/bounties/{bounty_id}">登录小飞侠账号</a></div>'
    buttons=[]
    if owner and b['status']=='in_progress': buttons.append(f'<form action="/bounties/{bounty_id}/status" method="post"><input type="hidden" name="status" value="completed"><button class="btn">标记已完成</button></form>')
    if owner and b['status'] in ('open','in_progress'): buttons.append(f'<form action="/bounties/{bounty_id}/status" method="post"><input type="hidden" name="status" value="cancelled"><button class="btn secondary">取消需求</button></form>')
    if owner and b['status']=='cancelled': buttons.append(f'<form action="/bounties/{bounty_id}/status" method="post"><input type="hidden" name="status" value="open"><button class="btn">重新开放</button></form>')
    side=f'<div class="panel"><h3>需求信息</h3><div class="money">{money(b["budget_cents"])}</div><div class="meta">发布者：{site.esc(b["display_name"])}<br>分类：{site.esc(b["category"])}<br>交付：{site.esc(b["deliverable"])}<br>截止：{site.esc(b["deadline"] or "不限")}<br>响应：{len(rs)}</div><div class="actions" style="margin-top:14px">{"".join(buttons)}</div></div><div class="note">悬赏金额目前不代表平台已收款或托管。选中开发者后，需求进入“开发中”。</div>'
    body=f'<div class="bw"><div class="bh"><div><div class="ey">BOUNTY #{b["id"]}</div><h1>{site.esc(b["title"])}</h1><div class="actions">{badge(b["status"])}<span class="tag">{site.esc(b["category"])}</span></div></div><a class="btn secondary" href="/bounties">返回需求广场</a></div><div class="layout"><div><div class="panel"><h2>需求说明</h2><div class="body">{site.esc(b["description"])}</div>{ref}</div>{response}</div><div>{side}</div></div></div>'
    return HTMLResponse(page(body,f'{b["title"]} · 需求广场'))


@router.post('/{bounty_id}/respond')
def respond(request: Request,bounty_id: int,proposal: str=Form(...),estimated_days: int=Form(...),quote_yuan: float=Form(0)):
    init_db(); u=user(request)
    if not u: return login_redirect(f'/bounties/{bounty_id}')
    if u['role']!=core.ROLE_XIAOFEIXIA: raise HTTPException(403,'只有小飞侠开发者可以响应悬赏需求。')
    proposal=proposal.strip()
    if not proposal or len(proposal)>5000: raise HTTPException(400,'方案说明不能为空，且最多 5000 字。')
    if estimated_days<1 or estimated_days>365: raise HTTPException(400,'预计周期需在 1—365 天之间。')
    if quote_yuan<0 or quote_yuan>1000000: raise HTTPException(400,'报价金额不正确。')
    stamp=core.now()
    with site.db() as conn:
        b=conn.execute('SELECT * FROM bounties WHERE id=?',(bounty_id,)).fetchone()
        if not b: raise HTTPException(404,'需求不存在。')
        if b['status']!='open': raise HTTPException(409,'该需求当前不再接受新方案。')
        if int(b['user_id'])==int(u['id']): raise HTTPException(400,'不能响应自己发布的需求。')
        try: conn.execute("INSERT INTO bounty_responses(bounty_id,developer_user_id,proposal,estimated_days,quote_cents,status,created_at,updated_at) VALUES(?,?,?,?,?,'proposed',?,?)",(bounty_id,u['id'],proposal,estimated_days,int(round(quote_yuan*100)),stamp,stamp))
        except Exception as exc:
            if 'UNIQUE' in str(exc).upper(): raise HTTPException(409,'你已经提交过方案。')
            raise
    return RedirectResponse(f'/bounties/{bounty_id}',303)


@router.post('/{bounty_id}/accept/{response_id}')
def accept(request: Request,bounty_id: int,response_id: int):
    init_db(); u=user(request)
    if not u: return login_redirect(f'/bounties/{bounty_id}')
    stamp=core.now()
    with site.db() as conn:
        b=conn.execute('SELECT * FROM bounties WHERE id=?',(bounty_id,)).fetchone()
        if not b: raise HTTPException(404,'需求不存在。')
        if int(b['user_id'])!=int(u['id']): raise HTTPException(403,'只有需求发布者可以选择开发者。')
        if b['status']!='open': raise HTTPException(409,'该需求当前不能选择开发者。')
        r=conn.execute('SELECT * FROM bounty_responses WHERE id=? AND bounty_id=?',(response_id,bounty_id)).fetchone()
        if not r: raise HTTPException(404,'方案不存在。')
        conn.execute("UPDATE bounty_responses SET status='proposed',updated_at=? WHERE bounty_id=?",(stamp,bounty_id)); conn.execute("UPDATE bounty_responses SET status='accepted',updated_at=? WHERE id=?",(stamp,response_id)); conn.execute("UPDATE bounties SET status='in_progress',accepted_response_id=?,updated_at=? WHERE id=?",(response_id,stamp,bounty_id))
    return RedirectResponse(f'/bounties/{bounty_id}',303)


@router.post('/{bounty_id}/status')
def set_status(request: Request,bounty_id: int,status: str=Form(...)):
    init_db(); u=user(request)
    if not u: return login_redirect(f'/bounties/{bounty_id}')
    if status not in ('open','completed','cancelled'): raise HTTPException(400,'状态不正确。')
    stamp=core.now()
    with site.db() as conn:
        b=conn.execute('SELECT * FROM bounties WHERE id=?',(bounty_id,)).fetchone()
        if not b: raise HTTPException(404,'需求不存在。')
        if int(b['user_id'])!=int(u['id']): raise HTTPException(403,'只有需求发布者可以修改状态。')
        if status=='completed' and b['status']!='in_progress': raise HTTPException(409,'只有开发中的需求可以标记完成。')
        if status=='open' and b['status']!='cancelled': raise HTTPException(409,'只有已取消需求可以重新开放。')
        if status=='cancelled' and b['status'] not in ('open','in_progress'): raise HTTPException(409,'当前状态不能取消。')
        accepted=None if status=='open' else b['accepted_response_id']; conn.execute('UPDATE bounties SET status=?,accepted_response_id=?,updated_at=? WHERE id=?',(status,accepted,stamp,bounty_id))
        if status=='open': conn.execute("UPDATE bounty_responses SET status='proposed',updated_at=? WHERE bounty_id=?",(stamp,bounty_id))
    return RedirectResponse(f'/bounties/{bounty_id}',303)
