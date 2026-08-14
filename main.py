"""Compatibility entrypoint.

The complete application now lives in app.py. Keeping this tiny wrapper means
both `uvicorn app:app` and `uvicorn main:app` start exactly the same site.
"""

from app import app
