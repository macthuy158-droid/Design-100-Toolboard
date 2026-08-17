"""Developer submission endpoint with streaming package persistence.

This module intentionally owns only the POST /developer/submit behavior. The
existing form/UI remains in community_portal.py, while package persistence is
kept out of the large portal module.
"""

from pathlib import Path
from typing import Optional

from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

import app_v2 as site
import community_core as core
from upload_storage import save_upload_stream


def _remove_old_submit_post(router):
    router.routes[:] = [
        route
        for route in router.routes
        if not (
            getattr(route, "path", "") == "/submit"
            and "POST" in (getattr(route, "methods", set()) or set())
        )
    ]


def install_streaming_submit(router):
    """Replace the legacy memory-buffered submit endpoint on a developer router."""
    _remove_old_submit_post(router)

    @router.post("/submit")
    async def submit(
        request: Request,
        submission_type: str = Form(...),
        existing_slug: str = Form(""),
        name: str = Form(""),
        tagline: str = Form(""),
        description: str = Form(""),
        category: str = Form(core.DEFAULT_TOOL_CATEGORY),
        platform: str = Form("Windows"),
        icon_text: str = Form("100"),
        price_yuan: float = Form(0),
        version: str = Form(...),
        notes: str = Form(""),
        app_url: str = Form(""),
        package: Optional[UploadFile] = File(None),
    ):
        core.init_db()
        user = core.current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="请先登录。")
        if user["role"] != core.ROLE_XIAOFEIXIA:
            raise HTTPException(status_code=403, detail="只有小飞侠开发者可以发布工具。")

        clean_version = version.strip()
        if not clean_version:
            raise HTTPException(status_code=400, detail="版本号不能为空。")

        is_web_app = submission_type == "new_web_app"

        tool = None
        if submission_type == "new_release":
            with site.db() as conn:
                tool = conn.execute(
                    "SELECT * FROM tools WHERE slug=?",
                    (existing_slug.strip(),),
                ).fetchone()
            if not tool:
                raise HTTPException(status_code=404, detail="已有工具不存在。")
            if not core.is_tool_owner(tool, user):
                raise HTTPException(status_code=403, detail="只有该工具原开发者可以提交新版本。")
            name = tool["name"]
            slug = tool["slug"]
            tagline = tool["tagline"]
            description = tool["description"]
            category = tool["category"]
            platform = tool["platform"]
            icon_text = tool["icon_text"]
        elif submission_type in ("new_tool", "new_web_app"):
            if not name.strip():
                raise HTTPException(status_code=400, detail="工具名称不能为空。")
            slug = core.slug_from_name(name)
            if category not in core.TOOL_CATEGORIES:
                raise HTTPException(status_code=400, detail="请选择有效的工具分类。")
            if is_web_app:
                clean_url = app_url.strip()
                if not clean_url or not clean_url.startswith("http"):
                    raise HTTPException(status_code=400, detail="请填写有效的工具访问地址（以 http 开头）。")
                platform = "Web"
                if price_yuan < 0:
                    raise HTTPException(status_code=400, detail="价格不能为负数。")
            else:
                if price_yuan <= 0:
                    raise HTTPException(status_code=400, detail="同行价格必须大于 0 元。")
        else:
            raise HTTPException(status_code=400, detail="投稿类型无效。")

        saved_package_name = ""
        saved_path = ""
        saved_sha256 = ""
        saved_size = 0

        if not is_web_app:
            if not package or not package.filename:
                raise HTTPException(status_code=400, detail="请上传安装包。")
            fallback_name = f"{slug}-{clean_version}.zip"
            folder = core.SUBMISSION_DIR / str(user["id"])
            try:
                saved = await save_upload_stream(
                    package,
                    folder,
                    fallback_name=fallback_name,
                    max_bytes=core.MAX_UPLOAD_BYTES,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            saved_package_name = saved.package_name
            saved_path = str(saved.path)
            saved_sha256 = saved.sha256
            saved_size = saved.size

        try:
            with site.db() as conn:
                conn.execute(
                    """INSERT INTO tool_submissions(
                        user_id,submission_type,tool_id,slug,name,tagline,description,
                        category,platform,icon_text,price_cents,version,notes,
                        package_name,package_path,sha256,size,status,created_at,
                        tool_type,app_url
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?)""",
                    (
                        user["id"],
                        submission_type,
                        tool["id"] if tool else None,
                        slug,
                        name.strip(),
                        tagline.strip(),
                        description.strip(),
                        category.strip(),
                        platform.strip(),
                        icon_text.strip(),
                        int(round(price_yuan * 100)),
                        clean_version,
                        notes.strip(),
                        saved_package_name,
                        saved_path,
                        saved_sha256,
                        saved_size,
                        core.now(),
                        "web_app" if is_web_app else "desktop",
                        app_url.strip() if is_web_app else "",
                    ),
                )
        except Exception:
            if saved_path:
                Path(saved_path).unlink(missing_ok=True)
            raise

        return RedirectResponse("/account/me", status_code=303)
