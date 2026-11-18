"""CareLoop API package.

The package exposes a persistence-backed :class:`CareLoopService` and an
HTTP-compatible ``app``.  FastAPI is used when installed; otherwise the same
service is available through the standard-library WSGI adapter.
"""

from .service import CareLoopService, AuthorizationError, NotFoundError, ValidationError


def create_service(db_path: str = ":memory:", *, seed: bool = False, seed_value: int = 20261019) -> CareLoopService:
    """Create a SQLite-backed service, optionally loading synthetic demo data."""

    service = CareLoopService(db_path)
    if seed:
        service.load_demo_data(seed=seed_value)
    return service


__all__ = ["CareLoopService", "AuthorizationError", "NotFoundError", "ValidationError", "create_service", "app", "create_app"]


def __getattr__(name: str):
    """Load the HTTP factories lazily so importing ``api`` stays side-effect free."""

    if name in {"app", "create_app"}:
        from importlib import import_module

        return getattr(import_module(".app", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
