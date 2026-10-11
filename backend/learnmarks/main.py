import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from learnmarks.api import bookmarks, dashboard, data, sync, tags, topics
from learnmarks.core.config import Settings, settings as default_settings
from learnmarks.core.db import init_db
from learnmarks.core.errors import AppError, app_error_handler, problem
from learnmarks.core.security import LocalOnlyMiddleware
from learnmarks.services import backup


log = logging.getLogger("learnmarks")


async def _daily_backups(settings: Settings) -> None:
    """Take an 'auto' backup when the newest one is over a day old; check hourly."""
    while True:
        try:
            age = backup.latest_auto_age(settings)
            if age is None or age > timedelta(hours=24):
                info = await asyncio.to_thread(backup.create, settings, "auto")
                log.info("auto backup %s", info.name)
        except Exception:  # never let a failed backup take the server down
            log.exception("auto backup failed")
        await asyncio.sleep(3600)


def create_app(settings: Settings = default_settings) -> FastAPI:
    init_db(settings.db_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(_daily_backups(settings)) if settings.auto_backup else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Learnmarks", version="0.2.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
                  lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return problem(422, "Invalid request", errors[0]["msg"] if errors else None, errors=errors)

    for module in (bookmarks, topics, tags, dashboard, data):
        app.include_router(module.router, prefix="/api/v1")
    app.include_router(sync.admin_router, prefix="/api/v1")
    app.include_router(sync.device_router)

    _mount_spa(app, settings.web_dist)
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built web UI (web/dist) with client-side routing fallback."""
    index = dist / "index.html"
    if not index.exists():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        if path.startswith(("api/", "sync/")):
            return problem(404, "Not found")
        return FileResponse(index)
