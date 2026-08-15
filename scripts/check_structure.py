"""Lightweight architecture smoke check for Design-100-Toolboard.

Run with:
    python scripts/check_structure.py

The check intentionally uses only the standard library plus the project's
runtime dependencies. It catches route collisions and verifies that sensitive
routes are owned by the intended modules.
"""

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402


def route_key(route):
    path = getattr(route, "path", "")
    methods = tuple(sorted(getattr(route, "methods", set()) or set()))
    return path, methods


routes = [route_key(route) for route in app.router.routes]
counts = Counter(routes)
duplicates = [key for key, count in counts.items() if count > 1]

if duplicates:
    details = "\n".join(f"  {methods} {path}" for path, methods in duplicates)
    raise SystemExit(f"Duplicate top-level routes detected:\n{details}")

legacy_admin_routes = [
    (path, methods)
    for path, methods in routes
    if path == "/manage" or path.startswith("/manage/")
]

manage_mounts = [
    route
    for route in app.router.routes
    if getattr(route, "path", "") == "/manage"
]
if len(manage_mounts) != 1:
    raise SystemExit(f"Expected exactly one /manage mount, found {len(manage_mounts)}")

for path, methods in legacy_admin_routes:
    if path != "/manage":
        raise SystemExit(
            f"Legacy admin route leaked into public app: {methods} {path}"
        )

required_paths = {"/", "/account/session", "/account/login", "/account/me", "/developer/submit"}
actual_paths = {path for path, _ in routes}
missing = sorted(required_paths - actual_paths)
if missing:
    raise SystemExit(f"Required routes missing: {', '.join(missing)}")

submit_posts = [
    route
    for route in app.router.routes
    if getattr(route, "path", "") == "/developer/submit"
    and "POST" in (getattr(route, "methods", set()) or set())
]
if len(submit_posts) != 1:
    raise SystemExit(f"Expected exactly one POST /developer/submit, found {len(submit_posts)}")
submit_module = getattr(getattr(submit_posts[0], "endpoint", None), "__module__", "")
if submit_module != "developer_upload":
    raise SystemExit(
        f"POST /developer/submit must use streaming developer_upload endpoint, got {submit_module!r}"
    )

print("Structure check passed")
print(f"Top-level routes: {len(routes)}")
print("Admin mount: /manage")
print("Developer upload: streaming endpoint")
