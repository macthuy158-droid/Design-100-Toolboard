from fastapi.responses import HTMLResponse

HOME_CSS = r'''<style>
.home-hero-card{min-height:500px;padding:58px 58px 46px}
.home-hero-grid{position:relative;z-index:2;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(330px,.75fr);gap:54px;min-height:396px}
.home-hero-left{display:flex;flex-direction:column;min-width:0}
.home-hero-left h1{max-width:680px;margin:20px 0 22px}
.home-hero-copy{max-width:610px}
.home-hero-tools{display:flex;align-items:flex-end;justify-content:space-between;gap:22px;margin-top:auto;padding-top:36px}
.home-search{width:min(410px,100%)}
.hero-ranking{border-left:1px solid rgba(255,255,255,.13);padding-left:34px;display:flex;flex-direction:column;min-width:0}
.hero-ranking-head{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:2px 0 15px}
.hero-ranking-title{font-size:17px;font-weight:760;letter-spacing:-.02em;color:#fff}
.hero-ranking-more{font-size:10px;color:#8f9196;white-space:nowrap}
.hero-ranking-more:hover{color:#fff}
.hero-rank-list{border-top:1px solid rgba(255,255,255,.11)}
.hero-rank-row{display:grid;grid-template-columns:38px minmax(0,1fr) auto;align-items:center;gap:10px;min-height:59px;border-bottom:1px solid rgba(255,255,255,.10);color:#fff;transition:.15s}
.hero-rank-row:hover{padding-left:5px}
.hero-rank-index{font-size:11px;color:#6f7278;font-weight:800;font-variant-numeric:tabular-nums}
.hero-rank-name{font-size:13px;font-weight:690;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hero-rank-count{font-size:10px;color:#8f9196;white-space:nowrap}
.hero-rank-empty{padding:28px 0;color:#777;font-size:11px;line-height:1.7}
.home-bounties{padding:16px 0 4px}
.home-courses{padding:16px 0 30px}
.home-course-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.home-course{display:flex;flex-direction:column;background:#fff;border:1px solid var(--line);border-radius:24px;padding:22px;color:#111;min-height:214px;transition:transform .2s,box-shadow .2s}
.home-course:hover{transform:translateY(-4px);box-shadow:var(--shadow)}
.home-course-cover{width:54px;height:54px;border-radius:16px;background:#0b0c0d;color:#fff;display:grid;place-items:center;font-size:13px;font-weight:850;margin-bottom:17px}
.home-course h3{font-size:18px;letter-spacing:-.03em;margin:0 0 8px;line-height:1.4}
.home-course-sum{font-size:11px;color:#84868b;line-height:1.7}
.home-course-foot{display:flex;justify-content:space-between;align-items:flex-end;margin-top:auto;padding-top:18px;border-top:1px solid #efefec;font-size:10px;color:#9a9ca0}
.home-course-price{font-size:15px;font-weight:790;color:#111;letter-spacing:-.02em}
.home-course-empty{grid-column:1/-1;padding:34px 22px;text-align:center;color:#888;font-size:11px;background:#fff;border:1px dashed #d6d6d2;border-radius:24px}
.home-section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:22px;padding:16px 0 15px}
.home-section-head h2{font-size:28px;letter-spacing:-.035em;margin:0 0 5px}
.home-section-head p{font-size:12px;color:#8b8d92;margin:0}
.home-bounty-actions{display:flex;gap:8px;align-items:center}
.home-bounty-list{background:#fff;border:1px solid var(--line);border-radius:25px;overflow:hidden}
.home-bounty-row{display:grid;grid-template-columns:92px minmax(0,1fr) 120px 42px;align-items:center;gap:16px;padding:18px 20px;border-bottom:1px solid #eeeeeb;transition:.15s}
.home-bounty-row:last-child{border-bottom:0}
.home-bounty-row:hover{background:#fafaf8}
.home-bounty-category{font-size:10px;color:#777}
.home-bounty-title{font-size:14px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.home-bounty-meta{font-size:9px;color:#a0a1a4;margin-top:4px}
.home-bounty-money{text-align:right;font-size:16px;font-weight:790;letter-spacing:-.02em}
.home-bounty-arrow{width:34px;height:34px;border-radius:50%;background:#111;color:#fff;display:grid;place-items:center;font-size:13px;justify-self:end}
.home-bounty-empty{padding:34px 22px;text-align:center;color:#888;font-size:11px}
.home-tools-toolbar{padding-top:34px}
@media(max-width:950px){.home-hero-grid{grid-template-columns:1fr;gap:36px}.hero-ranking{border-left:0;border-top:1px solid rgba(255,255,255,.13);padding:28px 0 0}.home-hero-tools{align-items:flex-start;flex-direction:column}.home-search{width:100%}.home-bounty-row{grid-template-columns:80px minmax(0,1fr) 96px 34px}.home-course-grid{grid-template-columns:1fr 1fr}}
@media(max-width:680px){.home-hero-card{padding:38px 26px 30px}.home-hero-grid{min-height:0}.home-section-head{align-items:flex-start;flex-direction:column}.home-bounty-row{grid-template-columns:minmax(0,1fr) auto;padding:15px 16px}.home-bounty-category{grid-column:1}.home-bounty-title{grid-column:1}.home-bounty-money{grid-column:2;grid-row:1/3}.home-bounty-arrow{display:none}.home-bounty-meta{display:none}.home-bounty-actions{width:100%}.home-bounty-actions .btn{flex:1}.home-course-grid{grid-template-columns:1fr}}
</style>'''


def _remove_existing_home(app):
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", None) == "/"
            and "GET" in (getattr(route, "methods", set()) or set())
        )
    ]


def _money(cents):
    return f"¥{int(cents or 0) / 100:,.0f}"


def install_homepage(app, site):
    _remove_existing_home(app)

    @app.get("/", response_class=HTMLResponse)
    def homepage():
        site.init_db()
        with site.db() as conn:
            tools = conn.execute(
                "SELECT * FROM tools WHERE active=1 ORDER BY downloads DESC,id ASC"
            ).fetchall()
            total = sum(int(t["downloads"] or 0) for t in tools)

            top_tools = tools[:5]
            ranking = "".join(
                f'''<a class="hero-rank-row" href="/tools/{site.esc(t['slug'])}"><span class="hero-rank-index">{i:02d}</span><span class="hero-rank-name">{site.esc(t['name'])}</span><span class="hero-rank-count">{int(t['downloads'] or 0):,}</span></a>'''
                for i, t in enumerate(top_tools, 1)
            )
            if not ranking:
                ranking = '<div class="hero-rank-empty">暂无已发布工具。</div>'

            has_bounties = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bounties'"
            ).fetchone()
            bounties = []
            if has_bounties:
                bounties = conn.execute(
                    '''SELECT id,title,category,budget_cents,deadline
                       FROM bounties
                       WHERE status='open'
                       ORDER BY id DESC
                       LIMIT 5'''
                ).fetchall()

            has_courses = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='courses'"
            ).fetchone()
            courses = []
            if has_courses:
                courses = conn.execute(
                    '''SELECT c.id,c.title,c.summary,c.category,c.level,c.cover_text,c.price_cents,
                              u.display_name,
                              (SELECT COUNT(*) FROM course_lessons l WHERE l.course_id=c.id) lesson_count
                       FROM courses c JOIN community_users u ON u.id=c.user_id
                       WHERE c.status='published'
                       ORDER BY c.id DESC
                       LIMIT 3'''
                ).fetchall()

        bounty_rows = "".join(
            f'''<a class="home-bounty-row" href="/bounties/{b['id']}"><div class="home-bounty-category">{site.esc(b['category'])}</div><div><div class="home-bounty-title">{site.esc(b['title'])}</div><div class="home-bounty-meta">招募中 · 截止 {site.esc(b['deadline'] or '不限')}</div></div><div class="home-bounty-money">{_money(b['budget_cents'])}</div><div class="home-bounty-arrow">↗</div></a>'''
            for b in bounties
        )
        if not bounty_rows:
            bounty_rows = '<div class="home-bounty-empty">还没有开放中的悬赏需求，发布第一个需求吧。</div>'

        course_cards = "".join(
            f'''<a class="home-course" href="/courses/{c['id']}"><div class="home-course-cover">{site.esc(c['cover_text'])}</div><h3>{site.esc(c['title'])}</h3><div class="home-course-sum">{site.esc(c['summary'])}</div><div class="home-course-foot"><span>{site.esc(c['category'])} · {site.esc(c['level'])} · {int(c['lesson_count'] or 0)} 节</span><span class="home-course-price">{'免费' if int(c['price_cents'] or 0) <= 0 else _money(c['price_cents'])}</span></div></a>'''
            for c in courses
        )
        if not course_cards:
            course_cards = '<div class="home-course-empty">还没有已发布的课程。小飞侠可以把自己的设计方法做成课程分享出来。</div>'

        body = site.nav() + f'''<div class="shell">
<section class="hero"><div class="hero-card home-hero-card"><div class="home-hero-grid">
<div class="home-hero-left"><div class="hero-kicker">DESIGN × TECHNOLOGY × PRODUCTIVITY</div><h1>100% 工具开发板</h1>
<div class="hero-copy home-hero-copy">把设计生产中的重复劳动，沉淀成每个人都能直接使用的工具。<br>让设计师把更多时间留给判断、创意与设计本身。</div>
<div class="home-hero-tools"><div class="stats"><div class="stat"><b>{len(tools)}</b><span>已发布工具</span></div><div class="stat"><b>{total:,}</b><span>累计下载</span></div></div>
<form class="searchbox home-search" action="/tools" method="get" role="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4.2-4.2"></path></svg><input name="q" aria-label="搜索工具" placeholder="搜索工具、分类或关键词"></form></div></div>
<div class="hero-ranking"><div class="hero-ranking-head"><a class="hero-ranking-title" href="/tools">工具排行榜</a><a class="hero-ranking-more" href="/tools">进入 Tool Board →</a></div><div class="hero-rank-list">{ranking}</div></div>
</div></div></section>
<section class="home-bounties"><div class="home-section-head"><div><h2>需求广场</h2><p>发布你的工具需求，设置悬赏，等待小飞侠响应。</p></div><div class="home-bounty-actions"><a class="btn secondary" href="/bounties">查看全部</a><a class="btn" href="/bounties/new">发布悬赏</a></div></div><div class="home-bounty-list">{bounty_rows}</div></section>
<section class="home-courses"><div class="home-section-head"><div><h2>小飞侠设计课程</h2><p>把工具背后的方法讲清楚 · 设计流程、插件用法与参数化经验。</p></div><div class="home-bounty-actions"><a class="btn secondary" href="/courses">查看全部</a><a class="btn" href="/courses/new">发布课程</a></div></div><div class="home-course-grid">{course_cards}</div></section>
<footer id="about" class="footer"><span><strong>深圳院设计100%</strong> · 工具开发板</span><span>面向真实设计生产流程持续迭代 · Internal Design Tools</span></footer></div>'''
        return HTMLResponse(
            site.page(body, extra=HOME_CSS),
            headers={"Cache-Control": "no-cache"},
        )
