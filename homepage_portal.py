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
.home-bbs{padding:16px 0 42px}
.home-section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:22px;padding:16px 0 15px}
.home-section-head h2{font-size:28px;letter-spacing:-.035em;margin:0 0 5px}
.home-section-head p{font-size:12px;color:#8b8d92;margin:0}
.home-bbs-grid{display:flex;flex-direction:column;gap:9px}
.home-bbs-card{position:relative;background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 22px 16px 24px;display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:center;gap:16px;color:#111;transition:.16s;overflow:hidden}
.home-bbs-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}
.home-bbs-card:hover{border-color:color-mix(in srgb,var(--accent) 40%,var(--line));background:color-mix(in srgb,var(--accent) 3%,#fff)}
.home-bbs-icon{font-size:19px;line-height:1}
.home-bbs-card h3{font-size:15px;letter-spacing:-.03em;margin:0 0 3px}
.home-bbs-card p{font-size:10.5px;line-height:1.55;color:#84868b;margin:0}
.home-bbs-go{font-size:10px;font-weight:700;color:var(--accent);white-space:nowrap}
@media(max-width:950px){.home-hero-grid{grid-template-columns:1fr;gap:36px}.hero-ranking{border-left:0;border-top:1px solid rgba(255,255,255,.13);padding:28px 0 0}.home-hero-tools{align-items:flex-start;flex-direction:column}.home-search{width:100%}}
@media(max-width:680px){.home-bbs-card{grid-template-columns:26px minmax(0,1fr);gap:12px;padding:14px 16px 14px 18px}.home-bbs-go{display:none}.home-hero-card{padding:38px 26px 30px}.home-hero-grid{min-height:0}.home-section-head{align-items:flex-start;flex-direction:column}}
</style>'''


def install_homepage(app, site):
    app.router.routes[:] = [
        route for route in app.router.routes
        if not (getattr(route, "path", None) == "/" and "GET" in (getattr(route, "methods", set()) or set()))
    ]

    @app.get("/", response_class=HTMLResponse)
    def homepage():
        site.init_db()
        with site.db() as conn:
            tools = conn.execute("SELECT * FROM tools WHERE active=1 ORDER BY downloads DESC,id ASC").fetchall()
            total = sum(int(t["downloads"] or 0) for t in tools)
            top_tools = tools[:5]

        ranking = "".join(
            f'''<a class="hero-rank-row" href="/tools/{site.esc(t['slug'])}"><span class="hero-rank-index">{i:02d}</span><span class="hero-rank-name">{site.esc(t['name'])}</span><span class="hero-rank-count">{int(t['downloads'] or 0):,}</span></a>'''
            for i, t in enumerate(top_tools, 1)
        ) or '<div class="hero-rank-empty">暂无已发布工具。</div>'

        body = site.nav() + f'''<div class="shell">
<section class="hero"><div class="hero-card home-hero-card"><div class="home-hero-grid">
<div class="home-hero-left"><div class="hero-kicker">DESIGN × TECHNOLOGY × PRODUCTIVITY</div><h1>100% 工具开发板</h1>
<div class="hero-copy home-hero-copy">把设计生产中的重复劳动，沉淀成每个人都能直接使用的工具。<br>让设计师把更多时间留给判断、创意与设计本身。</div>
<div class="home-hero-tools"><div class="stats"><div class="stat"><b>{len(tools)}</b><span>已发布工具</span></div><div class="stat"><b>{total:,}</b><span>累计下载</span></div></div>
<form class="searchbox home-search" action="/tools" method="get" role="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4.2-4.2"></path></svg><input name="q" aria-label="搜索工具" placeholder="搜索工具、分类或关键词"></form></div></div>
<div class="hero-ranking"><div class="hero-ranking-head"><a class="hero-ranking-title" href="/tools">工具排行榜</a><a class="hero-ranking-more" href="/tools">进入 Tool Board →</a></div><div class="hero-rank-list">{ranking}</div></div>
</div></div></section>
<section class="home-bbs"><div class="home-section-head"><div><h2>小飞侠 BBS</h2><p>技术交流、需求交易，以及设计院里真正想说的话。</p></div><a class="btn secondary" href="/bbs">进入 BBS →</a></div>
<div class="home-bbs-grid">
<a class="home-bbs-card" href="/bbs?board=lab" style="--accent:#3b5bdb"><div class="home-bbs-icon">🧪</div><div><h3>黑科技实验室</h3><p>AI Coding、Agent、CAD/BIM 自动化、插件脚本和各种新技术实验。</p></div><div class="home-bbs-go">技术交流 →</div></a>
<a class="home-bbs-card" href="/bbs?board=bounty" style="--accent:#c07800"><div class="home-bbs-icon">💰</div><div><h3>悬赏墙</h3><p>发布真实工具需求，设置悬赏，找到能把问题做成产品的人。</p></div><div class="home-bbs-go">去交易 →</div></a>
<a class="home-bbs-card" href="/bbs?board=tree" style="--accent:#2f6f3b"><div class="home-bbs-icon">🌳</div><div><h3>设计院树洞</h3><p>聊行业、工作、AI 和设计院里的真实日常；不方便署名时，可以匿名。</p></div><div class="home-bbs-go">进去看看 →</div></a>
</div></section>
<footer id="about" class="footer"><span><strong>小飞侠设计100%</strong> · 设计师工具与技术社区</span><span>Designers build tools for designers.</span></footer></div>'''
        return HTMLResponse(site.page(body, extra=HOME_CSS), headers={"Cache-Control": "no-cache"})
