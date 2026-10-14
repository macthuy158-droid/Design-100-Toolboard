"""Administrator roles, sales reporting and manually approved annual awards."""
import csv
import io
import json
from datetime import datetime

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import admin_portal
import app_v2 as site
import community_core as core
import payment_core


def superadmin(user):
    return core.is_admin(user) and bool(user['is_superadmin'])


def finance(user):
    return core.is_admin(user) and bool(user['is_superadmin'] or user['finance_enabled'])


def require(request, permission='super'):
    user = admin_portal.require_admin(request)
    if not (superadmin(user) if permission == 'super' else finance(user)):
        raise HTTPException(403, '需要主管理员权限。' if permission == 'super' else '需要财务查看权限。')
    return user


def init_db():
    with site.db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id INTEGER NOT NULL,
            action TEXT NOT NULL,target TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS annual_awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,year INTEGER NOT NULL,
            user_id INTEGER NOT NULL REFERENCES community_users(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            basis TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft','approved','paid','cancelled')),
            created_by INTEGER NOT NULL,created_at TEXT NOT NULL,
            approved_by INTEGER,approved_at TEXT,paid_by INTEGER,paid_at TEXT,
            payment_reference TEXT NOT NULL DEFAULT '');
        ''')


def audit(conn, actor, action, target, details):
    conn.execute('INSERT INTO admin_audit(actor_id,action,target,details,created_at) VALUES(?,?,?,?,?)',
                 (actor['id'],action,str(target),json.dumps(details,ensure_ascii=False),core.now()))


def render(request, title, body):
    user=core.current_user(request)
    links='<a href="/manage/revenue">收入统计</a>' if finance(user) else ''
    if superadmin(user):
        links+='<a href="/manage/permissions">管理员权限</a><a href="/manage/awards">年度奖金</a><a href="/manage/audit">操作日志</a>'
    return HTMLResponse(admin_portal.admin_page(f'''<div class="admin-shell">
        <style>.admin-shell table{{width:100%;border-collapse:collapse;background:white;margin-top:24px}}.admin-shell th,.admin-shell td{{text-align:left;border-bottom:1px solid #eee;padding:14px 10px;font-size:13px;vertical-align:top}}.admin-shell form{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}}.admin-shell input,.admin-shell select{{border:1px solid #ddd;border-radius:9px;padding:10px;max-width:100%;background:white}}.admin-shell p{{font-size:14px;line-height:1.8;color:#666}}.admin-shell{{overflow-x:auto}}.admin-shell td form{{margin:6px 0}}.admin-shell td{{overflow-wrap:anywhere}}</style>
        <div class="admin-head"><h1>{site.esc(title)}</h1><a class="btn secondary" href="/manage/">后台首页</a></div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">{links}</div>{body}</div>''',title),
        headers={'Cache-Control':'no-store'})


@admin_portal.app.get('/permissions')
def permissions(request: Request, q: str = ''):
    require(request)
    q=q.strip()[:100]
    with site.db() as conn:
        users=conn.execute('SELECT * FROM community_users WHERE instr(lower(username),lower(?))>0 OR instr(lower(display_name),lower(?))>0 ORDER BY is_superadmin DESC,is_admin DESC,id LIMIT 100',(q,q)).fetchall()
    rows=[]
    for u in users:
        role='super' if u['is_superadmin'] else ('finance' if u['is_admin'] and u['finance_enabled'] else ('admin' if u['is_admin'] else 'user'))
        options=''.join(f'<option value="{key}" {"selected" if key==role else ""}>{label}</option>' for key,label in [('user','普通用户'),('admin','普通管理员'),('finance','管理员＋财务查看'),('super','主管理员')])
        rows.append(f'''<tr><td>{site.esc(u['username'])}<br>{site.esc(u['display_name'])}</td><td>{'启用' if u['active'] else '停用'}</td><td><form method="post" action="/manage/permissions/{u['id']}"><select name="role">{options}</select><button class="btn secondary">保存权限</button></form></td></tr>''')
    return render(request,'管理员权限',f'''<p>主管理员可设置权限；财务查看仅允许查看订单和收入，奖金核定及发放登记由主管理员操作。保留至少一个启用的主管理员。</p>
        <form method="get"><input name="q" value="{site.esc(q)}" placeholder="搜索登录用户名或姓名"><button class="btn">搜索</button></form>
        <table><thead><tr><th>账号</th><th>状态</th><th>权限</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p>最多显示100个账号，请使用搜索定位。</p>''')


@admin_portal.app.post('/permissions/{user_id}')
def set_permission(request: Request,user_id: int,role: str=Form(...)):
    require(request)
    if role not in ('user','admin','finance','super'):
        raise HTTPException(400,'权限无效。')
    with site.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        actor=conn.execute('SELECT * FROM community_users WHERE id=?',(core.current_user(request)['id'],)).fetchone()
        if not superadmin(actor):
            raise HTTPException(403,'需要主管理员权限。')
        user=conn.execute('SELECT * FROM community_users WHERE id=?',(user_id,)).fetchone()
        if not user: raise HTTPException(404,'用户不存在。')
        if role!='user' and not user['active']: raise HTTPException(409,'请先启用此账号。')
        if user['is_superadmin'] and user['active'] and role!='super' and conn.execute('SELECT COUNT(*) FROM community_users WHERE active=1 AND is_admin=1 AND is_superadmin=1').fetchone()[0]<=1:
            raise HTTPException(409,'至少保留一个启用的主管理员。')
        before={k:user[k] for k in ('is_admin','is_superadmin','finance_enabled')}
        conn.execute('UPDATE community_users SET is_admin=?,is_superadmin=?,finance_enabled=?,updated_at=? WHERE id=?',
                     (int(role!='user'),int(role=='super'),int(role=='finance'),core.now(),user_id))
        audit(conn,actor,'permission.change',user_id,{'before':before,'role':role})
    return RedirectResponse('/manage/permissions',303)


def checked_year(year):
    if not 2000<=year<=2100: raise HTTPException(400,'年份无效。')
    return year


def sales(conn,year):
    # UTC timestamps are converted to China time for the reporting year.
    return conn.execute('''SELECT o.product_type,o.product_id,o.product_name,o.seller_user_id,
        u.username, o.currency,
        SUM(CASE WHEN o.status='paid' THEN 1 ELSE 0 END) paid_count,
        SUM(CASE WHEN o.status='paid' THEN o.amount_cents ELSE 0 END) paid_cents,
        SUM(CASE WHEN o.status='refunded' THEN o.amount_cents ELSE 0 END) refunded_cents
        FROM purchase_orders o LEFT JOIN community_users u ON u.id=o.seller_user_id
        WHERE o.status IN ('paid','refunded') AND strftime('%Y',o.paid_at,'+8 hours')=?
        GROUP BY o.product_type,o.product_id,o.product_name,o.seller_user_id,o.currency
        ORDER BY paid_cents DESC''',(str(year),)).fetchall()


@admin_portal.app.get('/revenue')
def revenue(request: Request,year: int=datetime.now().year):
    require(request,'finance'); checked_year(year)
    with site.db() as conn: rows=sales(conn,year)
    totals={}
    for r in rows: totals[r['currency']]=totals.get(r['currency'],0)+r['paid_cents']
    summary=' · '.join(f'{site.esc(k)} {v/100:.2f}' for k,v in totals.items()) or '暂无销售收入'
    table=''.join(f'''<tr><td>{site.esc(r['product_name'])}</td><td>{site.esc(r['username'] or '平台 / 未绑定发布者')}</td><td>{r['paid_count']}</td><td>{site.esc(r['currency'])} {r['paid_cents']/100:.2f}</td><td>{r['refunded_cents']/100:.2f}</td></tr>''' for r in rows)
    return render(request,'收入统计',f'''<form method="get"><input type="number" name="year" value="{year}" min="2000" max="2100"><button class="btn">查询年度</button></form><h2>{year}年 · {summary}</h2>
        <p>按北京时间付款年度统计；已退款订单不计入已付款销售额。金额未扣税费、支付手续费和运营成本，不代表可分配奖金。发布者记录不认定知识产权归属。退款仅展示已有订单状态，此处不执行退款。</p>
        <a class="btn secondary" href="/manage/revenue.csv?year={year}">导出年度报表</a><a class="btn secondary" href="/manage/community/purchases">查看现金订单</a>
        <table><thead><tr><th>商品</th><th>发布者</th><th>已付款笔数</th><th>已付款销售额</th><th>已退款订单额</th></tr></thead><tbody>{table or '<tr><td colspan="5">暂无记录</td></tr>'}</tbody></table>''')


@admin_portal.app.get('/revenue.csv')
def revenue_csv(request: Request,year: int=datetime.now().year):
    actor=require(request,'finance'); checked_year(year)
    with site.db() as conn:
        rows=sales(conn,year)
        audit(conn,actor,'revenue.export',year,{'rows':len(rows)})
    out=io.StringIO(); writer=csv.writer(out)
    writer.writerow(['年度','类型','商品ID','商品名称','发布者账号','币种','已付款笔数','已付款销售额','已退款订单额'])
    def safe(value):
        value=str(value or '')
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
    for r in rows:
        writer.writerow([year,r['product_type'],r['product_id'],safe(r['product_name']),safe(r['username']),safe(r['currency']),r['paid_count'],f"{r['paid_cents']/100:.2f}",f"{r['refunded_cents']/100:.2f}"])
    return Response(('\ufeff'+out.getvalue()).encode(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="revenue-{year}.csv"','Cache-Control':'no-store'})


@admin_portal.app.get('/awards')
def awards(request: Request,year: int=datetime.now().year):
    require(request); checked_year(year)
    with site.db() as conn:
        rows=conn.execute('SELECT a.*,u.username FROM annual_awards a JOIN community_users u ON u.id=a.user_id WHERE year=? ORDER BY a.id DESC',(year,)).fetchall()
    labels={'draft':'待核定','approved':'已核定','paid':'已发放','cancelled':'已取消'}
    items=[]
    for r in rows:
        actions=''
        if r['status'] in ('draft','approved'):
            action='approve' if r['status']=='draft' else 'paid'
            extra='<input name="reference" required maxlength="200" placeholder="实际付款凭证编号">' if action=='paid' else ''
            actions=f'''<form method="post" action="/manage/awards/{r['id']}/{action}">{extra}<button class="btn">{'核定奖金' if action=='approve' else '登记已发放'}</button></form><form method="post" action="/manage/awards/{r['id']}/cancel"><button class="btn secondary">取消</button></form>'''
        items.append(f'''<tr><td>{site.esc(r['username'])}</td><td>¥{r['amount_cents']/100:.2f}</td><td>{site.esc(r['basis'])}</td><td>{labels[r['status']]}</td><td>{site.esc(r['payment_reference'])}<br>{site.esc(r['paid_at'] or '')}{actions}</td></tr>''')
    total=sum(r['amount_cents'] for r in rows if r['status'] in ('approved','paid'))
    return render(request,'年度奖金',f'''<form method="get"><input type="number" name="year" value="{year}"><button class="btn">查询年度</button></form><h2>已核定总额 ¥{total/100:.2f}</h2>
        <p>仅登记院内批准的人民币奖金，不自动按销售额分成，不产生个人提现余额。登记发放不会实际转账。请依据院内制度核定并由财务实际发放后登记。</p>
        <h2>新增奖金草稿</h2><form method="post" action="/manage/awards"><input type="number" name="year" value="{year}" required><input name="username" placeholder="准确登录用户名" required maxlength="100"><input name="amount" placeholder="奖金金额（元）" required><input name="basis" placeholder="开发、维护、应用贡献及批准依据" required maxlength="1000"><button class="btn">保存草稿</button></form>
        <table><thead><tr><th>受奖人</th><th>金额</th><th>依据</th><th>状态</th><th>发放及操作</th></tr></thead><tbody>{''.join(items) or '<tr><td colspan="5">暂无记录</td></tr>'}</tbody></table>''')


@admin_portal.app.post('/awards')
def new_award(request: Request,year: int=Form(...),username: str=Form(...),amount: str=Form(...),basis: str=Form(...)):
    require(request); checked_year(year)
    cents=payment_core.yuan_to_cents(amount)
    if cents<=0 or not basis.strip() or len(basis)>1000 or len(username)>100: raise HTTPException(400,'请填写有效金额和依据。')
    with site.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        actor=conn.execute('SELECT * FROM community_users WHERE id=?',(core.current_user(request)['id'],)).fetchone()
        if not superadmin(actor): raise HTTPException(403,'需要主管理员权限。')
        u=conn.execute('SELECT id FROM community_users WHERE username=? COLLATE NOCASE',(username.strip(),)).fetchone()
        if not u: raise HTTPException(404,'登录用户名不存在。')
        row=conn.execute('INSERT INTO annual_awards(year,user_id,amount_cents,basis,created_by,created_at) VALUES(?,?,?,?,?,?)',(year,u['id'],cents,basis.strip(),actor['id'],core.now()))
        audit(conn,actor,'award.create',row.lastrowid,{'year':year,'user_id':u['id'],'amount_cents':cents})
    return RedirectResponse(f'/manage/awards?year={year}',303)


@admin_portal.app.post('/awards/{award_id}/{action}')
def update_award(request: Request,award_id: int,action: str,reference: str=Form('')):
    require(request)
    with site.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        actor=conn.execute('SELECT * FROM community_users WHERE id=?',(core.current_user(request)['id'],)).fetchone()
        if not superadmin(actor): raise HTTPException(403,'需要主管理员权限。')
        r=conn.execute('SELECT * FROM annual_awards WHERE id=?',(award_id,)).fetchone()
        if not r: raise HTTPException(404,'奖金记录不存在。')
        if action=='approve' and r['status']=='draft':
            conn.execute("UPDATE annual_awards SET status='approved',approved_by=?,approved_at=? WHERE id=?",(actor['id'],core.now(),award_id))
        elif action=='paid' and r['status']=='approved' and reference.strip() and len(reference)<=200:
            conn.execute("UPDATE annual_awards SET status='paid',paid_by=?,paid_at=?,payment_reference=? WHERE id=?",(actor['id'],core.now(),reference.strip(),award_id))
        elif action=='cancel' and r['status'] in ('draft','approved'):
            conn.execute("UPDATE annual_awards SET status='cancelled' WHERE id=?",(award_id,))
        else: raise HTTPException(409,'状态不允许此操作，发放必须填写实际付款凭证编号。')
        audit(conn,actor,'award.'+action,award_id,{'reference':reference.strip()})
    return RedirectResponse(f"/manage/awards?year={r['year']}",303)


@admin_portal.app.get('/audit')
def audit_page(request: Request,offset: int=0):
    require(request); offset=max(0,offset)
    with site.db() as conn:
        rows=conn.execute('SELECT a.*,u.username FROM admin_audit a LEFT JOIN community_users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 100 OFFSET ?',(offset,)).fetchall()
        grants=conn.execute('SELECT * FROM admin_access_events ORDER BY id DESC LIMIT 20').fetchall()
    table=''.join(f'<tr><td>{site.esc(r["created_at"])}</td><td>{site.esc(r["username"] or str(r["actor_id"]))}</td><td>{site.esc(r["action"])}</td><td>{site.esc(r["target"])}</td><td>{site.esc(r["details"])}</td></tr>' for r in rows)
    provision=''.join(f'<li>{site.esc(r["created_at"])} · 用户ID {r["user_id"]} · {site.esc(r["action"])} · {site.esc(r["actor"])}</li>' for r in grants)
    return render(request,'操作日志',f'''<p>记录权限变更、奖金操作、报表导出及后台写入请求；时间为UTC。写入请求记录HTTP结果，不包含密码或请求内容。</p><table><thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>详情</th></tr></thead><tbody>{table}</tbody></table><a href="?offset={max(0,offset-100)}">上一页</a> · <a href="?offset={offset+100}">下一页</a><h2>服务器授权记录</h2><ul>{provision}</ul>''')
