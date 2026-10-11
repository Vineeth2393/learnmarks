"""Local-only request guard (DESIGN §10).

The backend listens on 127.0.0.1, but any web page open in the laptop's browser can
still try to reach it. Checking Host blocks DNS-rebinding; checking Origin and
Sec-Fetch-Site blocks cross-site writes from other tabs.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from learnmarks.core.errors import problem

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: set[str]):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts
        self.allowed_origins = {f"http://{h}" for h in allowed_hosts}

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        if host not in self.allowed_hosts:
            return problem(421, "Unknown host", "This app only answers on 127.0.0.1 / localhost.")
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in self.allowed_origins:
                return problem(403, "Cross-site request blocked")
            if request.headers.get("sec-fetch-site") == "cross-site":
                return problem(403, "Cross-site request blocked")
        return await call_next(request)
