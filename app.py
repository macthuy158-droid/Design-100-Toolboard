"""Canonical application entrypoint for 小飞侠设计100%."""

from fastapi import Request

import app_v2 as public_site
import admin_portal
import community_admin
import community_core
import community_portal

BRAND_NAME = "小飞侠设计100%"
SITE_TITLE = f"{BRAND_NAME} · 工具开发板"
HERO_TITLE = "Desgin 100%"

SESSION_UI = r'''
<script>
(() => {
  async function syncMemberNav() {
    try {
      const res = await fetch('/account/session', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      if (!res.ok) return;
      const state = await res.json();
      if (!state.authenticated) return;

      document.querySelectorAll('.navlinks').forEach(nav => {
        const login = nav.querySelector('a[href="/account/login"]');
        const register = nav.querySelector('a[href="/account/register"]');
        const developer = nav.querySelector('a[href="/developer/submit"]');

        if (login) {
          login.href = '/account/me';
          login.textContent = `${state.display_name} · ${state.role_label}`;
          login.title = '进入个人中心';
        }
        if (register) register.remove();
        if (developer && state.role !== 'xiaofeixia') developer.remove();
      });
    } catch (_) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncMemberNav);
  } else {
    syncMemberNav();
  }
})();
</script>
'''


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
    return _original_page(
        branded_body,
        brand_text(title),
        (extra or "") + SESSION_UI,
    )


public_site.nav = branded_nav
public_site.page = branded_page
public_site.app.title = SITE_TITLE
app = public_site.app

community_core.init_db()
community_portal.install_public_routes(app)


@app.get("/account/session")
def account_session(request: Request):
    user = community_core.current_user(request)
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "display_name": user["display_name"],
        "role": user["role"],
        "role_label": community_core.role_label(user["role"]),
    }


app.include_router(community_portal.router, prefix="/account")
app.include_router(community_portal.developer_router, prefix="/developer")

_original_admin_page = admin_portal.admin_page


def branded_admin_page(body, title=f"{BRAND_NAME} · 管理后台"):
    body = brand_text(body)
    body = body.replace("DESIGN 100 · PRODUCT ADMIN", f"{BRAND_NAME} · PRODUCT ADMIN")
    body = body.replace("DESIGN 100 · ADMIN", f"{BRAND_NAME} · ADMIN")
    body = body.replace("DESIGN 100", BRAND_NAME)
    return _original_admin_page(body, brand_text(title))


admin_portal.admin_page = branded_admin_page
admin_portal.app.mount("/community", community_admin.app)
app.mount("/manage", admin_portal.app)
