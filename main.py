import app as public_site
import admin_portal

BRAND_NAME = "小飞侠设计100%"
SITE_TITLE = f"{BRAND_NAME} · 工具开发板"


def _brand_public_html(text: str) -> str:
    return (
        text.replace("深圳院设计100%", BRAND_NAME)
        .replace("100% 工具开发板", BRAND_NAME)
    )


# Public pages use app.py's page() at request time, so centralize the brand here.
_original_public_page = public_site.page


def branded_public_page(body, title=SITE_TITLE, extra=""):
    return _original_public_page(
        _brand_public_html(body),
        _brand_public_html(title),
        extra,
    )


public_site.page = branded_public_page
public_site.app.title = SITE_TITLE
app = public_site.app


# Keep the tool-centric admin visually consistent with the public brand.
_original_admin_page = admin_portal.admin_page


def branded_admin_page(body, title=f"{BRAND_NAME} · 管理后台"):
    branded_body = (
        _brand_public_html(body)
        .replace("DESIGN 100 · TOOL ADMIN", f"{BRAND_NAME} · TOOL ADMIN")
        .replace("DESIGN 100 · ADMIN", f"{BRAND_NAME} · ADMIN")
        .replace("DESIGN 100", BRAND_NAME)
    )
    branded_title = _brand_public_html(title).replace(
        "工具开发板管理", f"{BRAND_NAME} · 管理后台"
    )
    return _original_admin_page(branded_body, branded_title)


admin_portal.admin_page = branded_admin_page

# New tool-centric admin lives under /manage/.
app.mount("/manage", admin_portal.app)
