"""Lightweight architecture smoke check for Design-100-Toolboard.

Run with:
    python scripts/check_structure.py

The check intentionally uses only the standard library plus the project's
runtime dependencies. It catches the route collisions that previously allowed
legacy password-only admin endpoints to shadow the current admin app.
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

# The current admin system must appear only as one mounted application.
manage_mounts = [
    route
    for route in app.router.routes
    if getattr(route, "path", "") == "/manage"
]
if len(manage_mounts) != 1:
    raise SystemExit(f"Expected exactly one /manage mount, found {len(manage_mounts)}")

# No legacy concrete /manage/login route is allowed on the public app.
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

print("Structure check passed")
print(f"Top-level routes: {len(routes)}")
print("Admin mount: /manage")
