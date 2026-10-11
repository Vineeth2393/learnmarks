"""USB sync API.

`/sync/v1/*` is what the phone calls through the adb tunnel (device token required).
`/api/v1/sync/*` is what the laptop's web page calls (pairing codes, devices, conflicts, adb).
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from learnmarks.core.config import Settings
from learnmarks.core.db import get_session
from learnmarks.core.errors import AppError
from learnmarks.models import Bookmark, Device, SyncConflict, SyncSession, utcnow
from learnmarks.services import sync, usb

SessionDep = Annotated[Session, Depends(get_session)]
Uuid = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]


def _settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(_settings)]


def _device(session: SessionDep, authorization: Annotated[str | None, Header()] = None) -> Device:
    device = sync.authenticate(session, authorization)
    session.commit()
    return device


DeviceDep = Annotated[Device, Depends(_device)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ======================= phone-facing =======================

device_router = APIRouter(prefix="/sync/v1", tags=["sync (phone)"])


class PairIn(In):
    code: Annotated[str, Field(min_length=4, max_length=20)]
    device_id: Uuid
    device_name: Annotated[str, Field(min_length=1, max_length=80)]


class SessionIn(In):
    transport: Literal["adb_tunnel", "file"] = "adb_tunnel"
    app_version: Annotated[str, Field(max_length=40)] | None = None
    protocol_version: int


class Op(In):
    op_id: Uuid
    entity: Literal["bookmark", "tag"]
    entity_id: Uuid
    op: Literal["set_field", "add_link", "remove_link", "create_bookmark", "create_tag"]
    field: Annotated[str, Field(max_length=20)] | None = None
    base_value: Annotated[str, Field(max_length=2000)] | None = None
    new_value: Annotated[str, Field(max_length=2000)] | None = None
    payload: dict | None = None
    base_version: int = 0
    client_time: str | None = None


class PushIn(In):
    session_id: Uuid
    batch_id: Uuid
    ops: Annotated[list[Op], Field(max_length=500)]


class AckIn(In):
    session_id: Uuid
    acked_seq: Annotated[int, Field(ge=0)]


class FinishIn(In):
    outcome: Literal["success", "partial", "failed"]
    error: Annotated[str, Field(max_length=500)] | None = None


@device_router.post("/pair")
def pair(session: SessionDep, body: PairIn):
    token = sync.pair(session, body.code, body.device_id, body.device_name.strip())
    session.commit()
    return {"device_token": token, "protocol_version": sync.PROTOCOL_VERSION}


@device_router.get("/status")
def status(session: SessionDep, device: DeviceDep):
    hw = sync.high_water(session)
    return {"server_time": utcnow().isoformat(), "protocol_version": sync.PROTOCOL_VERSION, "device_name": device.name,
            "high_water_seq": hw, "pending_for_device": max(0, hw - device.acked_seq), "open_conflicts": sync.open_conflicts(session)}


@device_router.post("/sessions")
def start_session(session: SessionDep, device: DeviceDep, body: SessionIn):
    if body.protocol_version != sync.PROTOCOL_VERSION:
        raise AppError(426, "Update needed", f"The laptop speaks sync protocol {sync.PROTOCOL_VERSION}; update the app.")
    s = SyncSession(device_id=device.id, transport=body.transport, app_version=body.app_version, from_seq=device.acked_seq)
    session.add(s)
    session.commit()
    return {"session_id": s.id}


@device_router.post("/push")
def push(session: SessionDep, device: DeviceDep, body: PushIn):
    _owned(session, device, body.session_id)
    results = sync.push(session, device, body.session_id, [op.model_dump() for op in body.ops])
    return {"results": results}


@device_router.get("/pull")
def pull(session: SessionDep, device: DeviceDep, since: Annotated[int, Query(ge=0)] = 0,
         limit: Annotated[int, Query(ge=1, le=1000)] = 500, session_id: str | None = None):
    page = sync.pull(session, since, limit)
    if session_id:
        s = _owned(session, device, session_id)
        s.rows_sent += sum(len(page[k]) for k in ("groups", "topics", "tags", "bookmarks"))
        s.to_seq = page["next_seq"]
        session.commit()
    return page


@device_router.post("/ack", status_code=204)
def ack(session: SessionDep, device: DeviceDep, body: AckIn):
    _owned(session, device, body.session_id)
    device.acked_seq = max(device.acked_seq, min(body.acked_seq, sync.high_water(session)))
    session.commit()
    return Response(status_code=204)


@device_router.post("/sessions/{session_id}/finish", status_code=204)
def finish(session: SessionDep, device: DeviceDep, session_id: str, body: FinishIn):
    s = _owned(session, device, session_id)
    s.finished_at, s.outcome, s.error = utcnow(), body.outcome, body.error
    session.commit()
    return Response(status_code=204)


def _owned(session: Session, device: Device, session_id: str) -> SyncSession:
    s = session.get(SyncSession, session_id)
    if s is None or s.device_id != device.id:
        raise AppError(404, "Unknown sync session")
    return s


# ======================= laptop-facing =======================

admin_router = APIRouter(prefix="/sync", tags=["sync (laptop)"])


class DeviceOut(BaseModel):
    id: str
    name: str
    paired_at: datetime
    last_seen_at: datetime | None
    acked_seq: int
    pending_for_device: int


class ConflictOut(BaseModel):
    id: str
    bookmark_id: str
    bookmark_title: str
    kind: str
    field: str | None
    base_value: str | None
    mobile_value: str | None
    server_value: str | None
    detected_at: datetime
    device_name: str


class LogOut(BaseModel):
    id: str
    device_name: str
    started_at: datetime
    finished_at: datetime | None
    outcome: str
    ops_received: int
    ops_applied: int
    ops_conflicted: int
    ops_rejected: int
    rows_sent: int
    error: str | None


class ResolveIn(In):
    choice: Literal["keep_server", "take_mobile", "keep_both"]


@admin_router.post("/pairing-codes", status_code=201)
def pairing_code(session: SessionDep):
    code, expires = sync.new_pairing_code(session)
    session.commit()
    return {"code": code, "expires_at": expires}


@admin_router.get("/devices", response_model=list[DeviceOut])
def devices(session: SessionDep):
    hw = sync.high_water(session)
    rows = session.scalars(select(Device).where(Device.revoked_at.is_(None)).order_by(Device.paired_at)).all()
    return [DeviceOut(id=d.id, name=d.name, paired_at=d.paired_at, last_seen_at=d.last_seen_at, acked_seq=d.acked_seq,
                      pending_for_device=max(0, hw - d.acked_seq)) for d in rows]


@admin_router.delete("/devices/{device_id}", status_code=204)
def revoke(session: SessionDep, device_id: str):
    d = session.get(Device, device_id)
    if d is None or d.revoked_at is not None:
        raise AppError(404, "Device not found")
    d.revoked_at = utcnow()
    session.commit()
    return Response(status_code=204)


@admin_router.get("/conflicts", response_model=list[ConflictOut])
def conflicts(session: SessionDep):
    rows = session.execute(
        select(SyncConflict, Bookmark.title, Device.name)
        .join(Bookmark, Bookmark.id == SyncConflict.bookmark_id).join(Device, Device.id == SyncConflict.device_id)
        .where(SyncConflict.resolved_at.is_(None)).order_by(SyncConflict.detected_at)
    ).all()
    return [ConflictOut(id=c.id, bookmark_id=c.bookmark_id, bookmark_title=title, kind=c.kind, field=c.field,
                        base_value=c.base_value, mobile_value=c.mobile_value, server_value=c.server_value,
                        detected_at=c.detected_at, device_name=name) for c, title, name in rows]


@admin_router.post("/conflicts/{conflict_id}/resolve", status_code=204)
def resolve(session: SessionDep, conflict_id: str, body: ResolveIn):
    sync.resolve(session, conflict_id, body.choice)
    session.commit()
    return Response(status_code=204)


@admin_router.get("/log", response_model=list[LogOut])
def log(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    rows = session.execute(select(SyncSession, Device.name).join(Device, Device.id == SyncSession.device_id)
                           .order_by(SyncSession.started_at.desc()).limit(limit)).all()
    return [LogOut(id=s.id, device_name=name, started_at=s.started_at, finished_at=s.finished_at, outcome=s.outcome,
                   ops_received=s.ops_received, ops_applied=s.ops_applied, ops_conflicted=s.ops_conflicted,
                   ops_rejected=s.ops_rejected, rows_sent=s.rows_sent, error=s.error) for s, name in rows]


@admin_router.get("/usb")
def usb_status(settings: SettingsDep):
    return usb.status(settings)


@admin_router.post("/usb/start")
def usb_start(settings: SettingsDep):
    return usb.start(settings)


@admin_router.post("/usb/stop")
def usb_stop(settings: SettingsDep):
    return usb.stop(settings)
