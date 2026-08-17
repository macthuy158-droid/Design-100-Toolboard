"""Standalone Tool Board page.

The homepage now only surfaces the ranking; the full searchable/filterable
tool grid lives here at /tools so the landing page stays focused.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app_v2 as site

router = APIRouter()

BOARD_CSS = r'''<style>
.board-head{padding:46px 0 6px}
.board-head .hero-kicker{color:#8c8e93}
.board-head h1{font-size:clamp(38px,5.6vw,64px);letter-spacing:-.055em;line-height:1;margin:16px 0 16px}
.board-lead{font-size:14px;line-height:1.8;color:#74767b;max-width:620px}
.board-bar{display:flex;justify-content:space-between;align-items:flex-end;gap:26px;flex-wrap:wrap;margin-top:30px}
.board-bar .stats{gap:32px}
.board-bar .stat b{color:#111;font-size:26px}
.board-bar .stat span{color:#9a9ca0}
.board-search{width:min(420px,100%);border:1px solid var(--line)}
.board-back{display:inline-flex;align-items:center;gap:7px;font-size:11px;color:#777}
@media(max-width:680px){.board-search{width:100%}.board-bar{align-items:flex-start;flex-direction:column}}
</style>'''

APPLY_INITIAL_FILTER = r'''<script>
(() => {
  const input = document.getElementById('tool-search');
  if (input && input.value) input.dispatchEvent(new Event('input'));
})();
</script>'''


@router.get("/tools", response_class=HTMLResponse)
def toolboard(request: Request, q: str = "", category: str = ""):
    site.init_db()
    with site.db() as conn:
        tools = conn.execute(
            "SELECT * FROM tools WHERE active=1 ORDER BY downloads DESC,id ASC"
        ).fetchall()
        total = sum(int(t["downloads"] or 0) for t in tools)

        categories = []
        cards = []
        for i, t in enumerate(tools, 1):
            cat = t["category"] or "效率工具"
            if cat not in categories:
                categories.append(cat)
            tool_type = t["tool_type"] if "tool_type" in t.keys() else "desktop"
            is_web = tool_type == "web_app"
            rel = site.latest_release(conn, t["id"])
            version = rel["version"] if rel else "待发布"
            platform_label = "Web" if is_web else t["platform"]
            search_text = f"{t['name']} {t['tagline']} {cat} {platform_label}".lower()
            rank_label = "CLOUD APP" if is_web else "DOWNLOAD RANK"
            foot = (
                '<div class="downloads"><b>Cloud</b><span>立即使用</span></div>'
                if is_web
                else f'<div class="downloads"><b>{int(t["downloads"]):,}</b><span>累计下载</span></div>'
            )
            cards.append(
                f'''<a class="tool" href="/tools/{site.esc(t['slug'])}" data-category="{site.esc(cat)}" data-search="{site.esc(search_text)}">
<div class="rank"><span>{rank_label}</span><span class="rank-num">#{i:02d}</span></div>
<div class="icon">{site.esc(t['icon_text'])}</div><h3>{site.esc(t['name'])}</h3><div class="tagline">{site.esc(t['tagline'])}</div>
<div class="chips"><span class="chip">{site.esc(cat)}</span><span class="chip">{site.esc(platform_label)}</span><span class="chip">v{site.esc(version)}</span></div>
<div class="footrow">{foot}<div class="arrow">↗</div></div></a>'''
            )

    active = category if category in categories else "all"
    filters = [
        f'<button class="filter{" active" if active == "all" else ""}" data-category="all">全部</button>'
    ]
    filters += [
        f'<button class="filter{" active" if active == c else ""}" data-category="{site.esc(c)}">{site.esc(c)}</button>'
        for c in categories
    ]

    body = site.nav() + f'''<div class="shell">
<section class="board-head"><a class="board-back" href="/">← 返回首页</a>
<div class="hero-kicker" style="margin-top:20px">TOOL BOARD</div><h1>工具排行榜</h1>
<div class="board-lead">所有已发布工具 · 按累计下载量自动排序。搜索名称、分类或关键词，快速找到你需要的那一个。</div>
<div class="board-bar"><div class="stats"><div class="stat"><b>{len(tools)}</b><span>已发布工具</span></div><div class="stat"><b>{total:,}</b><span>累计下载</span></div></div>
<label class="searchbox board-search" aria-label="搜索工具"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4.2-4.2"></path></svg><input id="tool-search" value="{site.esc(q)}" placeholder="搜索工具、分类或关键词"></label></div></section>
<section id="tools"><div class="toolbar"><div><h2>Tool Board</h2><p>点击卡片进入工具详情页</p></div><div class="filters">{''.join(filters)}</div></div>
<main class="grid">{''.join(cards)}<div id="empty-state" class="empty">没有找到匹配的工具。</div></main></section>
<footer id="about" class="footer"><span><strong>深圳院设计100%</strong> · 工具开发板</span><span>面向真实设计生产流程持续迭代 · Internal Design Tools</span></footer></div>'''

    return HTMLResponse(
        site.page(body, "工具排行榜 · 小飞侠设计100%", BOARD_CSS + site.JS + APPLY_INITIAL_FILTER),
        headers={"Cache-Control": "no-cache"},
    )
