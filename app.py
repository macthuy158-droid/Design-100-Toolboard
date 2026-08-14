"""Canonical application entrypoint for 小飞侠设计100%."""

import app_v2 as public_site
import admin_portal

BRAND_NAME = "小飞侠设计100%"
SITE_TITLE = f"{BRAND_NAME} · 工具开发板"


def brand_text(value: str) -> str:
    """Replace every legacy public brand label with the current brand."""
    return (
        str(value)
        .replace("深圳院设计100%", BRAND_NAME)
        .replace("深圳设计100%", BRAND_NAME)
        .replace("100% 工具开发板", BRAND_NAME)
    )


# app_v2 defines the public routes. Its route functions resolve page() at
# request time, so patching the module-level renderer guarantees that every
# public page, nav, footer and document title receives the current brand.
_original_page = public_site.page


def branded_page(body, title=SITE_TITLE, extra=""):
    return _original_page(
        brand_text(body),
        brand_text(title),
        extra,
    )


public_site.page = branded_page
public_site.app.title = SITE_TITLE
app = public_site.app


# Apply the same brand to the tool-centric admin portal.
_original_admin_page = admin_portal.admin_page


def branded_admin_page(body, title=f"{BRAND_NAME} · 管理后台"):
    body = brand_text(body)
    body = body.replace("DESIGN 100 · TOOL ADMIN", f"{BRAND_NAME} · TOOL ADMIN")
    body = body.replace("DESIGN 100 · ADMIN", f"{BRAND_NAME} · ADMIN")
    body = body.replace("DESIGN 100", BRAND_NAME)
    return _original_admin_page(body, brand_text(title))


admin_portal.admin_page = branded_admin_page

# /manage/ uses the new per-tool management interface.
app.mount("/manage", admin_portal.app)
