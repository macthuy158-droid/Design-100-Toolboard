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


def branded_page(body, title=SITE_TITLE, extra=""):
    branded_body = brand_text(body)
    branded_body = branded_body.replace(
        f"<h1>{BRAND_NAME}</h1>",
        f"<h1>{HERO_TITLE}</h1>",
        1,
    )
    return _original_page(branded_body, brand_text(title), extra)


public_site.page = branded_page
public_site.app.title = SITE_TITLE
app = public_site.app

# Initialize the expanded community schema on boot/import.
community_core.init_db()

# Replace legacy public detail/download handlers with authenticated,
# role-aware versions that support reviews and purchase entitlements.
community_portal.install_public_routes(app)
app.include_router(community_portal.router, prefix="/account")
app.include_router(community_portal.developer_router, prefix="/developer")


_original_admin_page = admin_portal.admin_page


def branded_admin_page(body, title=f"{BRAND_NAME} · 管理后台"):
    body = brand_text(body)
    body = body.replace("DESIGN 100 · TOOL ADMIN", f"{BRAND_NAME} · TOOL ADMIN")
    body = body.replace("DESIGN 100 · ADMIN", f"{BRAND_NAME} · ADMIN")
    body = body.replace("DESIGN 100", BRAND_NAME)
    # Always expose the expanded account/submission/order manager from admin pages.
    if "</div>" in body and "/manage/community/" not in body:
        body = body.replace(
            '<button class="btn secondary" onclick=',
            '<a class="btn secondary" href="/manage/community/">用户 / 投稿 / 订单</a> <button class="btn secondary" onclick=',
            1,
        )
    return _original_admin_page(body, brand_text(title))


admin_portal.admin_page = branded_admin_page
admin_portal.app.mount("/community", community_admin.app)
app.mount("/manage", admin_portal.app)
