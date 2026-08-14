"""Canonical application entrypoint for 小飞侠设计100%."""

import app_v2 as public_site
import admin_portal
import community_admin
import community_core
import community_portal

BRAND_NAME = "小飞侠设计100%"
SITE_TITLE = f"{BRAND_NAME} · 工具开发板"
HERO_TITLE = "Desgin 100%"


def brand_text(value: str) -> str:
    return (
        str(value)
        .replace("深圳院设计100%", BRAND_NAME)
        .replace("深圳设计100%", BRAND_NAME)
        .replace("100% 工具开发板", BRAND_NAME)
    )


_original_page = public_site.page
_original_nav = public_site.nav


def branded_nav():
    html = brand_text(_original_nav())
    old = '<div class="navlinks"><a href="/#tools">工具</a><a href="/#about">关于</a><a class="admin-link" href="/manage">管理</a></div>'
    new = '''<div class="navlinks"><a href="/#tools">工具</a><a href="/developer/submit">开发者投稿</a><a href="/account/register">小游侠注册</a><a class="admin-link" href="/account/login">登录</a></div>'''
    return html.replace(old, new)


def branded_page(body, title=SITE_TITLE, extra=""):
    branded_body = brand_text(body)
    branded_body = branded_body.replace(
        f"<h1>{BRAND_NAME}</h1>",
        f"<h1>{HERO_TITLE}</h1>",
        1,
    )
    if '<section id="tools">' in branded_body and 'member-intro' not in branded_body:
        member_intro = '''
        <section class="member-intro" style="padding:18px 0 10px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
            <div style="background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:24px">
              <div class="eyebrow">院内用户 · DEVELOPER</div>
              <h2 style="margin:9px 0 8px;font-size:24px">小飞侠</h2>
              <p style="margin:0 0 18px;color:#777;font-size:13px;line-height:1.8">院内人员由管理员统一添加，无需自行注册。登录后全部工具免费下载，每位小飞侠都是开发者，可以提交工具和新版本，审核通过后公开发布。</p>
              <a class="btn" href="/account/login">小飞侠登录</a> <a class="btn secondary" href="/developer/submit">开发者投稿</a>
            </div>
            <div style="background:#fff;border:1px solid #e6e6e3;border-radius:24px;padding:24px">
              <div class="eyebrow">同行用户 · PEER USER</div>
              <h2 style="margin:9px 0 8px;font-size:24px">小游侠</h2>
              <p style="margin:0 0 18px;color:#777;font-size:13px;line-height:1.8">同行用户自行注册账号，可购买、下载、评分和留言。小游侠只使用工具，不具备产品发布权限。</p>
              <a class="btn" href="/account/register">注册小游侠</a> <a class="btn secondary" href="/account/login">已有账号登录</a>
            </div>
          </div>
        </section>
        <style>@media(max-width:700px){.member-intro>div{grid-template-columns:1fr!important}}</style>
        '''
        branded_body = branded_body.replace('<section id="tools">', member_intro + '<section id="tools">', 1)
    return _original_page(branded_body, brand_text(title), extra)


public_site.nav = branded_nav
public_site.page = branded_page
public_site.app.title = SITE_TITLE
app = public_site.app

community_core.init_db()
community_portal.install_public_routes(app)
app.include_router(community_portal.router, prefix="/account")
app.include_router(community_portal.developer_router, prefix="/developer")

_original_admin_page = admin_portal.admin_page


def branded_admin_page(body, title=f"{BRAND_NAME} · 管理后台"):
    body = brand_text(body)
    body = body.replace("DESIGN 100 · TOOL ADMIN", f"{BRAND_NAME} · TOOL ADMIN")
    body = body.replace("DESIGN 100 · ADMIN", f"{BRAND_NAME} · ADMIN")
    body = body.replace("DESIGN 100", BRAND_NAME)
    if "/manage/community/" not in body:
        body = body.replace(
            '<button class="btn secondary" onclick=',
            '<a class="btn secondary" href="/manage/community/">用户 / 投稿 / 订单</a> <button class="btn secondary" onclick=',
            1,
        )
    return _original_admin_page(body, brand_text(title))


admin_portal.admin_page = branded_admin_page
admin_portal.app.mount("/community", community_admin.app)
app.mount("/manage", admin_portal.app)
