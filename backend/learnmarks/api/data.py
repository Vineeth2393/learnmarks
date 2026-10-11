"""Import, export and backups (DESIGN §5, §10, §11)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from learnmarks.core.config import Settings
from learnmarks.core.db import get_session
from learnmarks.core.errors import AppError
from learnmarks.services import backup, export, importer

router = APIRouter(tags=["data"])
SessionDep = Annotated[Session, Depends(get_session)]
MAX_UPLOAD = 20 * 1024 * 1024


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


class BackupOut(BaseModel):
    name: str
    kind: str
    created_at: str
    size_bytes: int
    counts: dict[str, int]


class RestoreOut(BaseModel):
    restored: str
    safety_backup: str


@router.get("/export")
def export_all(session: SessionDep):
    body = export.build(session)
    filename = f"learnmarks-export-{date.today():%Y%m%d}.json"
    return JSONResponse(body, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/import", response_model=importer.Report)
async def import_file(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    format: Literal["ai-learning-path", "learnmarks", "csv"],
    dry_run: Annotated[bool, Query()] = True,
):
    """Send the file itself as the request body. Always try dry_run=true first."""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_UPLOAD:
            raise AppError(413, "File too large", "Imports are limited to 20 MB.")
    try:
        data = importer.parse(format, bytes(raw))
    except importer.ImportFailed as e:
        raise AppError(422, "Can't import this file", str(e)) from e

    safety = None
    if not dry_run:
        safety = backup.create(settings, "pre_import").name
    report = importer.run(session, format, data, dry_run=dry_run)
    if not dry_run:
        session.commit()
    report.backup = safety
    return report


@router.get("/backups", response_model=list[BackupOut])
def list_backups(settings: SettingsDep):
    return [BackupOut(**{k: v for k, v in vars(b).items() if k != "sha256"}) for b in backup.list_backups(settings)]


@router.post("/backups", response_model=BackupOut, status_code=201)
def create_backup(settings: SettingsDep):
    b = backup.create(settings, "manual")
    return BackupOut(**{k: v for k, v in vars(b).items() if k != "sha256"})


@router.post("/backups/{name}/restore", response_model=RestoreOut)
def restore_backup(settings: SettingsDep, name: str):
    safety = backup.restore(settings, name)
    return RestoreOut(restored=name, safety_backup=safety.name)
