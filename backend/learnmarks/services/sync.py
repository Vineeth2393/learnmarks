"""USB sync: pairing, push (merge phone ops), pull (changes since a cursor), conflicts.

DESIGN §8–9. Every phone op is applied in its own transaction and remembered in
`applied_ops`, so sending the same op again returns the same answer and changes nothing.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from learnmarks.core.errors import AppError
from learnmarks.models import (
    STATUSES,
    AppliedOp,
    Bookmark,
    BookmarkTag,
    BookmarkTopic,
    Device,
    PairingCode,
    SyncConflict,
    SyncSession,
    Tag,
    Topic,
    TopicGroup,
    utcnow,
)
from learnmarks.services import search
from learnmarks.services.bookmarks import append_position, find_live_by_canonical
from learnmarks.services.canonical import InvalidURL, default_title, for_item
from learnmarks.services.changes import stamp_new, touch

PROTOCOL_VERSION = 1
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O/1/I/L/U
CODE_TTL = timedelta(minutes=5)
MAX_FAILED_PAIRS = 5
FIELDS = {"status", "priority", "description"}
DONE_RESULTS = {"applied", "noop", "merged", "resolved"}

_failed_pairs = 0


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---------- pairing & auth ----------

def new_pairing_code(session: Session) -> tuple[str, datetime]:
    global _failed_pairs
    _failed_pairs = 0
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    expires = utcnow() + CODE_TTL
    session.add(PairingCode(code_hash=_hash(raw), expires_at=expires))
    return f"{raw[:4]}-{raw[4:]}", expires


def pair(session: Session, code: str, device_id: str, name: str) -> str:
    """Redeem a pairing code. Returns the device token — shown once, only its hash is kept."""
    global _failed_pairs
    if _failed_pairs >= MAX_FAILED_PAIRS:
        raise AppError(429, "Too many wrong codes", "Make a new pairing code on the laptop.")
    normalized = "".join(ch for ch in code.upper() if ch.isalnum())
    row = session.get(PairingCode, _hash(normalized))
    if row is None or row.used_at is not None or _aware(row.expires_at) < utcnow():
        _failed_pairs += 1
        if _failed_pairs >= MAX_FAILED_PAIRS:  # stop guessing: every open code becomes useless
            for open_code in session.scalars(select(PairingCode).where(PairingCode.used_at.is_(None))):
                open_code.used_at = utcnow()
            session.commit()
        raise AppError(401, "Wrong or expired code", "Check the code on the laptop's USB sync page.")
    row.used_at = utcnow()
    token = secrets.token_urlsafe(32)
    device = session.get(Device, device_id)
    if device is None:
        session.add(Device(id=device_id, name=name, token_hash=_hash(token)))
    else:  # re-pairing the same phone: new token, old one stops working
        device.name, device.token_hash, device.revoked_at = name, _hash(token), None
    return token


def authenticate(session: Session, authorization: str | None) -> Device:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(401, "Not paired", "Pair this phone on the laptop's USB sync page.")
    token_hash = _hash(authorization.removeprefix("Bearer ").strip())
    device = session.scalars(select(Device).where(Device.token_hash == token_hash)).first()
    if device is None or not hmac.compare_digest(device.token_hash, token_hash) or device.revoked_at is not None:
        raise AppError(401, "Not paired", "This phone was unpaired. Pair it again on the laptop.")
    device.last_seen_at = utcnow()
    return device


def high_water(session: Session) -> int:
    """The newest change number on the laptop."""
    return session.execute(text("SELECT value FROM change_counter WHERE id = 1")).scalar_one()


def open_conflicts(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(SyncConflict).where(SyncConflict.resolved_at.is_(None))) or 0


# ---------- push ----------

def _record(session: Session, device: Device, session_id: str | None, op: dict, result: str, *,
            canonical_id: str | None = None, conflict_id: str | None = None, error: str | None = None) -> dict:
    session.add(AppliedOp(op_id=op["op_id"], device_id=device.id, session_id=session_id, entity=op["entity"],
                          entity_id=op["entity_id"], op=op["op"], result=result, canonical_id=canonical_id,
                          conflict_id=conflict_id, error=error))
    return _result(op["op_id"], result, canonical_id, conflict_id, error)


def _result(op_id, result, canonical_id=None, conflict_id=None, error=None, server_version=None) -> dict:
    out: dict[str, Any] = {"op_id": op_id, "result": result}
    if canonical_id:
        out["canonical_id"] = canonical_id
    if conflict_id:
        out["conflict_id"] = conflict_id
    if error:
        out["error"] = error
    if server_version is not None:
        out["server_version"] = server_version
    return out


def push(session: Session, device: Device, session_id: str | None, ops: list[dict]) -> list[dict]:
    """Apply each op in its own transaction. Returns one result per op, in order."""
    # New tags before the bookmarks that use them, then new bookmarks, then edits (stable within each group).
    rank = {"create_tag": 0, "create_bookmark": 1}
    by_id = {op["op_id"]: i for i, op in enumerate(ops)}
    ordered = sorted(ops, key=lambda op: (rank.get(op["op"], 2), by_id[op["op_id"]]))
    out: dict[str, dict] = {}
    sess = session.get(SyncSession, session_id) if session_id else None
    for op in ordered:
        previous = session.get(AppliedOp, op["op_id"])
        if previous is not None:  # a repeat (lost response, interrupted sync, or a conflict being re-checked)
            out[op["op_id"]] = _result(op["op_id"], previous.result, previous.canonical_id, previous.conflict_id, previous.error)
            continue
        try:
            r = _apply(session, device, session_id, op)
            session.commit()
        except AppError as e:
            session.rollback()
            r = _record(session, device, session_id, op, "rejected", error=e.detail or e.title)
            session.commit()
        out[op["op_id"]] = r
        if sess is not None:
            sess = session.get(SyncSession, session_id)
            sess.ops_received += 1
            sess.ops_applied += r["result"] in ("applied", "noop", "merged")
            sess.ops_conflicted += r["result"] == "conflict"
            sess.ops_rejected += r["result"] == "rejected"
            session.commit()
    return [out[op["op_id"]] for op in ops]  # answers in the order they were sent


def _apply(session: Session, device: Device, session_id: str | None, op: dict) -> dict:
    kind = op["op"]
    if kind == "create_tag":
        return _create_tag(session, device, session_id, op)
    if kind == "create_bookmark":
        return _create_bookmark(session, device, session_id, op)

    b = session.get(Bookmark, op["entity_id"])
    if b is None:
        b = _merged_bookmark(session, op["entity_id"])
    if b is None:
        return _record(session, device, session_id, op, "rejected", error="This bookmark doesn't exist on the laptop")
    if b.deleted_at is not None:
        return _conflict(session, device, session_id, op, b, "edit_vs_delete", op.get("field"), None)

    if kind == "set_field":
        field = op.get("field")
        if field not in FIELDS:
            raise AppError(422, "Unknown field", f"Can't change “{field}” from the phone")
        new = _validate(field, op.get("new_value"))
        current = _current(b, field)
        if current == op.get("base_value"):
            if current != new:
                _set(b, field, new)
                touch(session, b)
                search.reindex(session, [b.id])
            return _record(session, device, session_id, op, "applied")
        if current == new:
            return _record(session, device, session_id, op, "noop")
        return _conflict(session, device, session_id, op, b, "field", field, current)

    if kind in ("add_link", "remove_link"):
        field, target = op.get("field"), op.get("new_value")
        if field == "topics":
            topic = session.get(Topic, target or "")
            if topic is None or topic.deleted_at is not None:
                if kind == "remove_link":
                    return _record(session, device, session_id, op, "noop")
                return _record(session, device, session_id, op, "rejected", error="That topic was deleted on the laptop")
            link = session.get(BookmarkTopic, (b.id, topic.id))
            if (link is not None) == (kind == "add_link"):
                return _record(session, device, session_id, op, "noop")
            if kind == "add_link":
                session.add(BookmarkTopic(bookmark_id=b.id, topic_id=topic.id, sort_order=append_position(session, topic.id)))
            else:
                session.delete(link)
        elif field == "tags":
            tag_id = _resolve_tag(session, target or "")
            if tag_id is None:
                if kind == "remove_link":
                    return _record(session, device, session_id, op, "noop")
                return _record(session, device, session_id, op, "rejected", error="That tag was deleted on the laptop")
            link = session.get(BookmarkTag, (b.id, tag_id))
            if (link is not None) == (kind == "add_link"):
                return _record(session, device, session_id, op, "noop")
            if kind == "add_link":
                session.add(BookmarkTag(bookmark_id=b.id, tag_id=tag_id))
            else:
                session.delete(link)
        else:
            raise AppError(422, "Unknown link type", str(field))
        session.flush()
        touch(session, b)
        search.reindex(session, [b.id])
        return _record(session, device, session_id, op, "applied")

    raise AppError(422, "Unknown operation", str(kind))


def _current(b: Bookmark, field: str) -> str | None:
    value = getattr(b, field)
    return None if value is None else str(value)


def _validate(field: str, value: str | None) -> str | None:
    if field == "status" and value not in STATUSES:
        raise AppError(422, "Invalid status", str(value))
    if field == "priority" and value not in ("1", "2", "3"):
        raise AppError(422, "Invalid priority", str(value))
    if field == "description":
        value = (value or "").strip()[:2000] or None
    return value


def _set(b: Bookmark, field: str, value: str | None) -> None:
    if field == "status":
        b.status, b.status_changed_at = value, utcnow()
    elif field == "priority":
        b.priority = int(value)
    else:
        b.description = value


def _conflict(session, device, session_id, op, b: Bookmark, kind: str, field: str | None, server_value: str | None) -> dict:
    c = SyncConflict(device_id=device.id, op_id=op["op_id"], bookmark_id=b.id, kind=kind, field=field,
                     base_value=op.get("base_value"), mobile_value=op.get("new_value"),
                     server_value=server_value, server_version=b.version)
    session.add(c)
    session.flush()
    return _record(session, device, session_id, op, "conflict", conflict_id=c.id)


def _merged_bookmark(session: Session, phone_id: str) -> Bookmark | None:
    """A bookmark the phone created that the laptop merged into an existing one."""
    prev = session.scalars(select(AppliedOp).where(AppliedOp.entity_id == phone_id, AppliedOp.op == "create_bookmark",
                                                   AppliedOp.result == "merged")).first()
    return session.get(Bookmark, prev.canonical_id) if prev and prev.canonical_id else None


def _resolve_tag(session: Session, tag_id: str) -> str | None:
    tag = session.get(Tag, tag_id)
    if tag is not None and tag.deleted_at is None:
        return tag.id
    prev = session.scalars(select(AppliedOp).where(AppliedOp.entity_id == tag_id, AppliedOp.op == "create_tag",
                                                   AppliedOp.result == "merged")).first()
    if prev and prev.canonical_id:
        t = session.get(Tag, prev.canonical_id)
        return t.id if t is not None and t.deleted_at is None else None
    return None


def _create_tag(session, device, session_id, op) -> dict:
    payload = op.get("payload") or {}
    name = " ".join(str(payload.get("name") or "").split())[:60]
    if not name:
        raise AppError(422, "Tag has no name")
    existing = session.scalars(select(Tag).where(func.lower(Tag.name) == name.lower(), Tag.deleted_at.is_(None))).first()
    if existing is not None:
        return _record(session, device, session_id, op, "merged", canonical_id=existing.id)
    tag = Tag(name=name)
    if session.get(Tag, op["entity_id"]) is None:
        tag.id = op["entity_id"]
    stamp_new(session, tag)
    session.add(tag)
    session.flush()
    return _record(session, device, session_id, op, "applied", canonical_id=tag.id if tag.id != op["entity_id"] else None)


def _create_bookmark(session, device, session_id, op) -> dict:
    p = op.get("payload") or {}
    try:
        c = for_item(str(p.get("url") or ""), str(p.get("title") or ""))
    except InvalidURL as e:
        raise AppError(422, "Invalid link", str(e)) from e
    status = p.get("status") if p.get("status") in STATUSES else "saved"
    priority = p.get("priority") if p.get("priority") in (1, 2, 3) else 2
    description = (str(p.get("description") or "").strip()[:2000]) or None
    topic_ids = [t for t in (p.get("topic_ids") or []) if isinstance(t, str)]
    tag_ids = [t for t in (p.get("tag_ids") or []) if isinstance(t, str)]

    existing = find_live_by_canonical(session, c.canonical_url)
    if existing is not None:
        # Saved on both devices: combine topics and tags, keep the laptop's title/status/priority.
        changed = _link_all(session, existing, topic_ids, tag_ids)
        if description and not existing.description:
            existing.description, changed = description, True
        elif description and existing.description and description != existing.description:
            session.add(SyncConflict(device_id=device.id, op_id=op["op_id"], bookmark_id=existing.id, kind="duplicate_create",
                                     field="description", mobile_value=description, server_value=existing.description,
                                     server_version=existing.version))
        if changed:
            touch(session, existing)
            search.reindex(session, [existing.id])
        return _record(session, device, session_id, op, "merged", canonical_id=existing.id)

    try:
        saved = date.fromisoformat(str(p.get("date_saved"))[:10])
    except ValueError:
        saved = date.today()
    now = utcnow()
    b = Bookmark(url=c.clean_url, canonical_url=c.canonical_url, title=str(p.get("title") or "").strip()[:300] or default_title(c),
                 source_platform=c.source_platform, author_handle=c.author_handle, date_saved=saved,
                 description=description, status=status, status_changed_at=now, priority=priority)
    if session.get(Bookmark, op["entity_id"]) is None:
        b.id = op["entity_id"]
    stamp_new(session, b)
    session.add(b)
    session.flush()
    _link_all(session, b, topic_ids, tag_ids)
    session.flush()
    search.reindex(session, [b.id])
    return _record(session, device, session_id, op, "applied", canonical_id=b.id if b.id != op["entity_id"] else None)


def _link_all(session: Session, b: Bookmark, topic_ids: list[str], tag_ids: list[str]) -> bool:
    changed = False
    for tid in dict.fromkeys(topic_ids):
        topic = session.get(Topic, tid)
        if topic is not None and topic.deleted_at is None and session.get(BookmarkTopic, (b.id, tid)) is None:
            session.add(BookmarkTopic(bookmark_id=b.id, topic_id=tid, sort_order=append_position(session, tid)))
            session.flush()
            changed = True
    for raw in dict.fromkeys(tag_ids):
        tid = _resolve_tag(session, raw)
        if tid is not None and session.get(BookmarkTag, (b.id, tid)) is None:
            session.add(BookmarkTag(bookmark_id=b.id, tag_id=tid))
            session.flush()
            changed = True
    return changed


# ---------- pull ----------

def _iso(dt: datetime | None) -> str | None:
    return _aware(dt).isoformat().replace("+00:00", "Z") if dt else None


def pull(session: Session, since: int, limit: int) -> dict:
    """Everything changed after `since`, oldest change first, at most `limit` rows (tombstones included)."""
    rows: list[tuple[int, str, Any]] = []
    for kind, model in (("groups", TopicGroup), ("topics", Topic), ("tags", Tag), ("bookmarks", Bookmark)):
        for r in session.scalars(select(model).where(model.server_seq > since).order_by(model.server_seq).limit(limit + 1)):
            rows.append((r.server_seq, kind, r))
    rows.sort(key=lambda x: x[0])
    page, has_more = rows[:limit], len(rows) > limit

    out: dict[str, list] = {"groups": [], "topics": [], "tags": [], "bookmarks": []}
    bookmark_ids = [r.id for _, kind, r in page if kind == "bookmarks"]
    links: dict[str, list[dict]] = {}
    tag_links: dict[str, list[str]] = {}
    if bookmark_ids:
        live_topic = select(Topic.id).where(Topic.deleted_at.is_(None))
        for bid, tid, order in session.execute(select(BookmarkTopic.bookmark_id, BookmarkTopic.topic_id, BookmarkTopic.sort_order)
                                               .where(BookmarkTopic.bookmark_id.in_(bookmark_ids), BookmarkTopic.topic_id.in_(live_topic))):
            links.setdefault(bid, []).append({"topic_id": tid, "sort_order": order})
        live_tag = select(Tag.id).where(Tag.deleted_at.is_(None))
        for bid, tid in session.execute(select(BookmarkTag.bookmark_id, BookmarkTag.tag_id)
                                        .where(BookmarkTag.bookmark_id.in_(bookmark_ids), BookmarkTag.tag_id.in_(live_tag))):
            tag_links.setdefault(bid, []).append(tid)

    for seq, kind, r in page:
        base = {"id": r.id, "version": r.version, "server_seq": seq, "deleted": r.deleted_at is not None}
        if kind == "groups":
            out[kind].append({**base, "name": r.name, "sort_order": r.sort_order})
        elif kind == "topics":
            out[kind].append({**base, "name": r.name, "description": r.description, "color": r.color, "level": r.level,
                              "group_id": r.group_id, "sort_order": r.sort_order})
        elif kind == "tags":
            out[kind].append({**base, "name": r.name})
        else:
            out[kind].append({**base, "url": r.url, "title": r.title, "source_platform": r.source_platform,
                              "author_handle": r.author_handle, "date_saved": r.date_saved.isoformat(),
                              "description": r.description, "status": r.status, "priority": r.priority,
                              "status_changed_at": _iso(r.status_changed_at), "created_at": _iso(r.created_at),
                              "topics": links.get(r.id, []), "tag_ids": tag_links.get(r.id, [])})
    next_seq = page[-1][0] if page else since
    return {**out, "next_seq": next_seq, "has_more": has_more, "high_water_seq": high_water(session)}


# ---------- conflicts (resolved on the laptop) ----------

def resolve(session: Session, conflict_id: str, choice: str) -> SyncConflict:
    c = session.get(SyncConflict, conflict_id)
    if c is None:
        raise AppError(404, "Conflict not found")
    if c.resolved_at is not None:
        raise AppError(409, "Already resolved")
    b = session.get(Bookmark, c.bookmark_id)
    if b is None:
        raise AppError(404, "Bookmark not found")
    allowed = {"keep_server", "take_mobile"} | ({"keep_both"} if c.field == "description" else set())
    if choice not in allowed:
        raise AppError(422, "Not an option for this conflict", f"Choose one of: {', '.join(sorted(allowed))}")

    if choice == "take_mobile":
        if b.deleted_at is not None:
            if find_live_by_canonical(session, b.canonical_url, exclude_id=b.id) is not None:
                raise AppError(409, "Can't restore", "The same post was saved again since; keep the laptop's version.")
            b.deleted_at = None
        if c.field:
            _set(b, c.field, _validate(c.field, c.mobile_value))
        c.resolved_value = c.mobile_value
    elif choice == "keep_both":
        both = "\n\n".join(v for v in (c.server_value, c.mobile_value) if v)
        b.description = both[:2000]
        c.resolved_value = b.description
    else:
        c.resolved_value = c.server_value
    c.resolved_at, c.resolution = utcnow(), choice
    touch(session, b)  # the phone pulls the outcome on its next sync
    search.reindex(session, [b.id])
    op = session.get(AppliedOp, c.op_id)
    if op is not None and op.result == "conflict":
        op.result = "resolved"  # when the phone re-sends this op it learns it's settled and drops it
    return c
