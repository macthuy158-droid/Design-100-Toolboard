"""Canonical application composition root for 小飞侠设计100%.

This file assembles the public homepage, member/developer features and the
current administrator application. Legacy admin and ungated public download
routes have been removed from app_v2.py, so route ownership is explicit.
"""

from fastapi import Request

import app_v2 as public_site
from runtime_support import install_database_connection, once_per_process

install_database_connection(public_site)

import admin_portal  # noqa: E402
import community_core  # noqa: E402
import community_portal  # noqa: E402
import developer_upload  # noqa: E402

community_core.init_db = once_per_process(community_core.init_db)
community_core.init_db()

import bounty_portal  # noqa: E402
import community_admin  # noqa: E402
import course_portal  # noqa: E402
import homepage_portal  # noqa: E402
import toolboard_portal  # noqa: E402

# Bounty and course schemas are deliberately isolated from the existing
# tool/community migrations so the new features can evolve without
# destabilising Tool Store.
bounty_portal.init_db()
course_portal.init_db()

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
    new = '''<div class="navlinks"><a href="/tools">工具</a><a href="/courses">课程</a><a href="/bounties">需求</a><a href="/account/register">注册</a><a class="admin-link" href="/account/login">登录</a></div>'''
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

community_portal.install_public_routes(app)
developer_upload.install_streaming_submit(community_portal.developer_router)
homepage_portal.install_homepage(app, public_site)


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
app.include_router(bounty_portal.router)
app.include_router(course_portal.router)
app.include_router(toolboard_portal.router)

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
