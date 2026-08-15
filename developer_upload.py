"""Developer submission endpoint with streaming package persistence.

This module intentionally owns only the POST /developer/submit behavior. The
existing form/UI remains in community_portal.py, while package persistence is
kept out of the large portal module.
"""

from pathlib import Path

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
        slug: str = Form(""),
        tagline: str = Form(""),
        description: str = Form(""),
        category: str = Form(core.DEFAULT_TOOL_CATEGORY),
        platform: str = Form("Windows"),
        icon_text: str = Form("100"),
        price_yuan: float = Form(...),
        version: str = Form(...),
        notes: str = Form(""),
        package: UploadFile = File(...),
    ):
        core.init_db()
        user = core.current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="请先登录。")
        if user["role"] != core.ROLE_XIAOFEIXIA:
            raise HTTPException(status_code=403, detail="只有小飞侠开发者可以发布工具。")
        if price_yuan <= 0:
            raise HTTPException(status_code=400, detail="同行价格必须大于 0 元。")

        clean_version = version.strip()
        if not clean_version:
            raise HTTPException(status_code=400, detail="版本号不能为空。")

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
        elif submission_type == "new_tool":
            slug = slug.strip().lower()
            if not core.VALID_SLUG.match(slug):
                raise HTTPException(status_code=400, detail="Slug 只能使用小写英文、数字和短横线。")
            if category not in core.TOOL_CATEGORIES:
                raise HTTPException(status_code=400, detail="请选择有效的工具分类。")
        else:
            raise HTTPException(status_code=400, detail="投稿类型无效。")

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

        try:
            with site.db() as conn:
                conn.execute(
                    """INSERT INTO tool_submissions(
                        user_id,submission_type,tool_id,slug,name,tagline,description,
                        category,platform,icon_text,price_cents,version,notes,
                        package_name,package_path,sha256,size,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)""",
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
                        saved.package_name,
                        str(saved.path),
                        saved.sha256,
                        saved.size,
                        core.now(),
                    ),
                )
        except Exception:
            Path(saved.path).unlink(missing_ok=True)
            raise

        return RedirectResponse("/account/me", status_code=303)
