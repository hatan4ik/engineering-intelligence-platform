"""ASGI entry point.

Application composition lives in :mod:`app.application`; this module remains
the stable ``uvicorn app.main:app`` target used by the container and tooling.
"""

from app.application import create_app


app = create_app()


__all__ = ["app", "create_app"]
