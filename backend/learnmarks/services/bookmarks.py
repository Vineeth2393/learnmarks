"""Bookmark use-cases: create, update, delete/restore, list/filter, bulk, and output mapping."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from learnmarks.core.errors import AppError, not_found
from learnmarks.models import Bookmark, BookmarkTag, BookmarkTopic, Tag, Topic, utcnow
from learnmarks.schemas import BookmarkCreate, BookmarkOut, BookmarkUpdate, BulkUpdate, TagRef, TopicRef
from learnmarks.services import search
from learnmarks.services.canonical import Canonical, InvalidURL, default_title, for_item
from learnmarks.services.changes import stamp_new, touch

ORDER_GAP = 1000.0
STATUS_RANK = {"saved": 0, "to_learn": 1, "in_progress": 2, "learned": 3}


# ---------- helpers ----------

def parse_url(raw: str | None, title: str | None = None) -> Canonical:
    try:
        return for_item(raw, title)
    except InvalidURL as e:
        raise AppError(422, "Invalid URL", str(e)) from e


def find_live_by_canonical(session: Session, canonical_url: str, exclude_id: str | None = None) -> Bookmark | None:
    stmt = select(Bookmark).where(Bookmark.canonical_url == canonical_url, Bookmark.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(Bookmark.id != exclude_id)
    return session.scalars(stmt).first()


def _duplicate(existing: Bookmark) -> AppError:
    return AppError(409, "Already saved", f"This post is already saved as “{existing.title}”.",
                    existing_id=existing.id, existing_title=existing.title)


def get_live(session: Session, bookmark_id: str, *, include_deleted: bool = False) -> Bookmark:
    b = session.get(Bookmark, bookmark_id)
    if b is None or (b.deleted_at is not None and not include_deleted):
        raise not_found("Bookmark")
    return b


def check_version(row, if_match: str | None) -> None:
    if if_match is None:
        raise AppError(428, "If-Match header required", "Send the version you edited, e.g. If-Match: 3")
    try:
        expected = int(if_match.strip().strip('"').removeprefix("W/").strip('"'))
    except ValueError as e:
        raise AppError(400, "Bad If-Match header") from e
    if row.version != expected:
        raise AppError(412, "Changed elsewhere",
                       f"This item is now at version {row.version}; reload and try again.", current_version=row.version)


def live_topics(session: Session, topic_ids: Sequence[str]) -> list[Topic]:
    ids = list(dict.fromkeys(topic_ids))
    if not ids:
        return []
    topics = session.scalars(select(Topic).where(Topic.id.in_(ids), Topic.deleted_at.is_(None))).all()
    missing = set(ids) - {t.id for t in topics}
    if missing:
        raise AppError(422, "Unknown topic", f"{len(missing)} topic id(s) do not exist", topic_ids=sorted(missing))
    by_id = {t.id: t for t in topics}
    return [by_id[i] for i in ids]


def get_or_create_tags(session: Session, names: Sequence[str]) -> list[Tag]:
    wanted: dict[str, str] = {}
    for n in names:
        n = " ".join(n.split())
        if n:
            wanted.setdefault(n.lower(), n)
    if not wanted:
        return []
    existing = session.scalars(
        select(Tag).where(func.lower(Tag.name).in_(list(wanted)), Tag.deleted_at.is_(None))
    ).all()
    by_lower = {t.name.lower(): t for t in existing}
    out = []
    for key, name in wanted.items():
        tag = by_lower.get(key)
        if tag is None:
            tag = Tag(name=name)
            stamp_new(session, tag)
            session.add(tag)
        out.append(tag)
    return out


def append_position(session: Session, topic_id: str) -> float:
    current = session.scalar(select(func.max(BookmarkTopic.sort_order)).where(BookmarkTopic.topic_id == topic_id))
    return (current or 0.0) + ORDER_GAP


def _set_topics(session: Session, b: Bookmark, topics: list[Topic]) -> bool:
    keep = {t.id for t in topics}
    changed = False
    for link in list(b.topic_links):
        if link.topic_id not in keep:
            b.topic_links.remove(link)
            changed = True
    have = {l.topic_id for l in b.topic_links}
    for t in topics:
        if t.id not in have:
            b.topic_links.append(BookmarkTopic(topic_id=t.id, sort_order=append_position(session, t.id)))
            session.flush()
            changed = True
    return changed


def _set_tags(session: Session, b: Bookmark, tags: list[Tag]) -> bool:
    keep = {t.id for t in tags}
    changed = False
    for link in list(b.tag_links):
        if link.tag_id not in keep:
            b.tag_links.remove(link)
            changed = True
    have = {l.tag_id for l in b.tag_links}
    for t in tags:
        if t.id not in have:
            b.tag_links.append(BookmarkTag(tag=t))
            changed = True
    return changed


# ---------- use-cases ----------

def create(session: Session, data: BookmarkCreate) -> Bookmark:
    c = parse_url(data.url, data.title)
    if (existing := find_live_by_canonical(session, c.canonical_url)) is not None:
        raise _duplicate(existing)
    topics = live_topics(session, data.topic_ids)
    now = utcnow()
    b = Bookmark(
        url=c.clean_url,
        canonical_url=c.canonical_url,
        title=data.title or default_title(c),
        source_platform=data.source_platform or c.source_platform,
        author_handle=c.author_handle,
        date_saved=data.date_saved or date.today(),
        description=data.description or None,
        status=data.status,
        status_changed_at=now,
        priority=data.priority,
    )
    stamp_new(session, b)
    session.add(b)
    session.flush()
    _set_topics(session, b, topics)
    _set_tags(session, b, get_or_create_tags(session, data.tag_names))
    search.reindex(session, [b.id])
    return b


def update(session: Session, b: Bookmark, data: BookmarkUpdate, if_match: str | None) -> Bookmark:
    check_version(b, if_match)
    fields = data.model_dump(exclude_unset=True)
    changed = False

    retitled_note = not b.url and fields.get("title") and fields["title"] != b.title and "url" not in fields
    if ("url" in fields and fields["url"] != b.url) or retitled_note:
        # A checklist item (no link) is identified by its title, so renaming it changes its key.
        c = parse_url(fields.get("url", b.url), fields.get("title") or b.title)
        if (existing := find_live_by_canonical(session, c.canonical_url, exclude_id=b.id)) is not None:
            raise _duplicate(existing)
        b.url, b.canonical_url, b.author_handle = c.clean_url, c.canonical_url, c.author_handle
        if "source_platform" not in fields:
            b.source_platform = c.source_platform
        changed = True

    for name in ("title", "date_saved", "priority", "source_platform"):
        if name in fields and fields[name] is not None and getattr(b, name) != fields[name]:
            setattr(b, name, fields[name])
            changed = True
    if "description" in fields:
        desc = fields["description"] or None
        if desc != b.description:
            b.description = desc
            changed = True
    if fields.get("status") and fields["status"] != b.status:
        b.status = fields["status"]
        b.status_changed_at = utcnow()
        changed = True
    if fields.get("topic_ids") is not None:
        changed |= _set_topics(session, b, live_topics(session, fields["topic_ids"]))
    if fields.get("tag_names") is not None:
        changed |= _set_tags(session, b, get_or_create_tags(session, fields["tag_names"]))

    if changed:
        touch(session, b)
        search.reindex(session, [b.id])
    return b


def delete(session: Session, b: Bookmark) -> None:
    b.deleted_at = utcnow()
    touch(session, b)
    search.reindex(session, [b.id])


def restore(session: Session, b: Bookmark) -> Bookmark:
    if b.deleted_at is None:
        return b
    if (existing := find_live_by_canonical(session, b.canonical_url, exclude_id=b.id)) is not None:
        raise _duplicate(existing)
    b.deleted_at = None
    touch(session, b)
    search.reindex(session, [b.id])
    return b


def bulk(session: Session, data: BulkUpdate) -> int:
    rows = session.scalars(select(Bookmark).where(Bookmark.id.in_(data.ids), Bookmark.deleted_at.is_(None))).all()
    # Process in the caller's order so bookmarks added to a topic land in that order.
    rank = {bid: i for i, bid in enumerate(data.ids)}
    rows = sorted(rows, key=lambda b: rank[b.id])
    add_topic = live_topics(session, [data.add_topic_id])[0] if data.add_topic_id else None
    add_tag = get_or_create_tags(session, [data.add_tag])[0] if data.add_tag else None
    count = 0
    for b in rows:
        changed = False
        if data.delete:
            delete(session, b)
            count += 1
            continue
        if data.status and b.status != data.status:
            b.status, b.status_changed_at, changed = data.status, utcnow(), True
        if data.priority and b.priority != data.priority:
            b.priority, changed = data.priority, True
        if add_topic and add_topic.id not in {l.topic_id for l in b.topic_links}:
            b.topic_links.append(BookmarkTopic(topic_id=add_topic.id, sort_order=append_position(session, add_topic.id)))
            session.flush()
            changed = True
        if data.remove_topic_id:
            for l in [l for l in b.topic_links if l.topic_id == data.remove_topic_id]:
                b.topic_links.remove(l)
                changed = True
        if add_tag and add_tag.id not in {l.tag_id for l in b.tag_links}:
            b.tag_links.append(BookmarkTag(tag=add_tag))
            changed = True
        if data.remove_tag:
            for l in [l for l in b.tag_links if l.tag.name.lower() == data.remove_tag.lower()]:
                b.tag_links.remove(l)
                changed = True
        if changed:
            touch(session, b)
            count += 1
    search.reindex(session, [b.id for b in rows])
    return count


# ---------- listing ----------

@dataclass
class ListQuery:
    q: str | None = None
    topic: str | None = None
    tags: list[str] = field(default_factory=list)
    tag_mode: str = "any"
    sources: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    priorities: list[int] = field(default_factory=list)
    saved_from: date | None = None
    saved_to: date | None = None
    no_topic: bool = False
    sort: str | None = None  # relevance | order | date_saved | title | priority | status | updated
    dir: str | None = None  # asc | desc
    limit: int = 50
    offset: int = 0


def list_ids(session: Session, lq: ListQuery) -> list[str]:
    stmt = select(Bookmark.id).where(Bookmark.deleted_at.is_(None))
    relevance: list[str] | None = None
    if lq.q and lq.q.strip():
        relevance = search.search_ids(session, lq.q)
        if not relevance:
            return []
        stmt = stmt.where(Bookmark.id.in_(relevance))
    if lq.topic:
        stmt = stmt.join(BookmarkTopic, BookmarkTopic.bookmark_id == Bookmark.id).where(BookmarkTopic.topic_id == lq.topic)
    if lq.tags:
        tagged = select(BookmarkTag.bookmark_id).where(BookmarkTag.tag_id.in_(lq.tags))
        if lq.tag_mode == "all":
            tagged = tagged.group_by(BookmarkTag.bookmark_id).having(
                func.count(func.distinct(BookmarkTag.tag_id)) == len(set(lq.tags)))
        stmt = stmt.where(Bookmark.id.in_(tagged))
    if lq.no_topic:
        linked = (select(BookmarkTopic.bookmark_id).join(Topic, Topic.id == BookmarkTopic.topic_id)
                  .where(Topic.deleted_at.is_(None)))
        stmt = stmt.where(Bookmark.id.not_in(linked))
    if lq.sources:
        stmt = stmt.where(Bookmark.source_platform.in_(lq.sources))
    if lq.statuses:
        stmt = stmt.where(Bookmark.status.in_(lq.statuses))
    if lq.priorities:
        stmt = stmt.where(Bookmark.priority.in_(lq.priorities))
    if lq.saved_from:
        stmt = stmt.where(Bookmark.date_saved >= lq.saved_from)
    if lq.saved_to:
        stmt = stmt.where(Bookmark.date_saved <= lq.saved_to)

    sort = lq.sort or ("relevance" if relevance else ("order" if lq.topic else "date_saved"))
    if sort == "order" and not lq.topic:
        raise AppError(422, "Learning order needs a topic", "Use sort=order together with topic=<id>")
    desc = (lq.dir or ("asc" if sort in ("order", "title", "relevance") else "desc")) == "desc"

    if sort == "relevance" and relevance is not None:
        ids = set(session.scalars(stmt))
        ordered = [i for i in relevance if i in ids]
        return list(reversed(ordered)) if desc else ordered

    key = {
        "order": BookmarkTopic.sort_order,
        "date_saved": Bookmark.date_saved,
        "title": func.lower(Bookmark.title),
        "priority": Bookmark.priority,
        "status": case(STATUS_RANK, value=Bookmark.status),
        "updated": Bookmark.updated_at,
    }.get(sort)
    if key is None:
        raise AppError(422, "Unknown sort", f"sort must be one of relevance, order, date_saved, title, priority, status, updated")
    stmt = stmt.order_by(key.desc() if desc else key.asc(), Bookmark.created_at.desc(), Bookmark.id)
    return list(session.scalars(stmt))


def load_many(session: Session, ids: Sequence[str]) -> list[Bookmark]:
    if not ids:
        return []
    rows = session.scalars(
        select(Bookmark).where(Bookmark.id.in_(ids))
        .options(selectinload(Bookmark.topic_links).selectinload(BookmarkTopic.topic),
                 selectinload(Bookmark.tag_links).selectinload(BookmarkTag.tag))
    ).all()
    by_id = {b.id: b for b in rows}
    return [by_id[i] for i in ids if i in by_id]


# ---------- output ----------

def positions(session: Session, topic_ids: set[str]) -> dict[tuple[str, str], int]:
    """1-based place of each live bookmark inside each topic's learning order."""
    if not topic_ids:
        return {}
    rn = func.row_number().over(partition_by=BookmarkTopic.topic_id, order_by=(BookmarkTopic.sort_order, BookmarkTopic.bookmark_id))
    rows = session.execute(
        select(BookmarkTopic.topic_id, BookmarkTopic.bookmark_id, rn)
        .join(Bookmark, Bookmark.id == BookmarkTopic.bookmark_id)
        .where(BookmarkTopic.topic_id.in_(topic_ids), Bookmark.deleted_at.is_(None))
    ).all()
    return {(t, b): n for t, b, n in rows}


def to_out(session: Session, bookmarks: Sequence[Bookmark]) -> list[BookmarkOut]:
    topic_ids = {l.topic_id for b in bookmarks for l in b.topic_links}
    pos = positions(session, topic_ids)
    out = []
    for b in bookmarks:
        links = [l for l in b.topic_links if l.topic.deleted_at is None]
        links.sort(key=lambda l: (l.topic.sort_order, l.topic.name.lower()))
        out.append(BookmarkOut(
            id=b.id, url=b.url, canonical_url=b.canonical_url, title=b.title,
            source_platform=b.source_platform, author_handle=b.author_handle, date_saved=b.date_saved,
            description=b.description, status=b.status, status_changed_at=b.status_changed_at,
            priority=b.priority, created_at=b.created_at, updated_at=b.updated_at, version=b.version,
            deleted=b.deleted_at is not None,
            topics=[TopicRef(id=l.topic.id, name=l.topic.name, color=l.topic.color,
                             position=pos.get((l.topic_id, b.id), 0)) for l in links],
            tags=sorted((TagRef(id=l.tag.id, name=l.tag.name) for l in b.tag_links if l.tag.deleted_at is None),
                        key=lambda t: t.name.lower()),
        ))
    return out


def one_out(session: Session, b: Bookmark) -> BookmarkOut:
    session.flush()
    session.refresh(b)
    return to_out(session, load_many(session, [b.id]))[0]
