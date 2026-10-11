"""Topics, topic groups (tracks) and learning order."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from learnmarks.core.errors import AppError, not_found
from learnmarks.models import Bookmark, BookmarkTopic, Topic, TopicGroup, utcnow
from learnmarks.schemas import (
    GroupCreate,
    GroupOut,
    GroupUpdate,
    StatusCounts,
    TopicCreate,
    TopicMove,
    TopicOut,
    TopicUpdate,
)
from learnmarks.services import search
from learnmarks.services.bookmarks import ORDER_GAP, check_version
from learnmarks.services.changes import stamp_new, touch

MIN_GAP = 1e-6


def status_counts(session: Session, topic_ids: list[str] | None = None) -> dict[str, StatusCounts]:
    stmt = (select(BookmarkTopic.topic_id, Bookmark.status, func.count())
            .join(Bookmark, Bookmark.id == BookmarkTopic.bookmark_id)
            .where(Bookmark.deleted_at.is_(None))
            .group_by(BookmarkTopic.topic_id, Bookmark.status))
    if topic_ids is not None:
        stmt = stmt.where(BookmarkTopic.topic_id.in_(topic_ids))
    out: dict[str, StatusCounts] = {}
    for tid, status, n in session.execute(stmt):
        c = out.setdefault(tid, StatusCounts())
        setattr(c, status, n)
        c.total += n
    return out


def topic_out(t: Topic, counts: StatusCounts | None) -> TopicOut:
    return TopicOut(id=t.id, name=t.name, description=t.description, color=t.color, group_id=t.group_id,
                    sort_order=t.sort_order, level=t.level, version=t.version, counts=counts or StatusCounts())


def list_topics(session: Session) -> list[TopicOut]:
    topics = session.scalars(select(Topic).where(Topic.deleted_at.is_(None))
                             .order_by(Topic.sort_order, func.lower(Topic.name))).all()
    counts = status_counts(session)
    return [topic_out(t, counts.get(t.id)) for t in topics]


def get_topic(session: Session, topic_id: str) -> Topic:
    t = session.get(Topic, topic_id)
    if t is None or t.deleted_at is not None:
        raise not_found("Topic")
    return t


def _check_group(session: Session, group_id: str | None) -> None:
    if group_id is not None:
        g = session.get(TopicGroup, group_id)
        if g is None or g.deleted_at is not None:
            raise AppError(422, "Unknown topic group")


def _name_taken(session: Session, model, name: str, exclude_id: str | None = None) -> bool:
    stmt = select(model.id).where(func.lower(model.name) == name.lower(), model.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(model.id != exclude_id)
    return session.scalar(stmt) is not None


def create_topic(session: Session, data: TopicCreate) -> Topic:
    if _name_taken(session, Topic, data.name):
        raise AppError(409, "Topic exists", f"A topic called “{data.name}” already exists.")
    _check_group(session, data.group_id)
    same_group = Topic.group_id.is_(None) if data.group_id is None else Topic.group_id == data.group_id
    last = session.scalar(select(func.max(Topic.sort_order)).where(same_group, Topic.deleted_at.is_(None)))
    t = Topic(**data.model_dump(), sort_order=(last or 0) + ORDER_GAP)
    stamp_new(session, t)
    session.add(t)
    session.flush()
    return t


def update_topic(session: Session, t: Topic, data: TopicUpdate, if_match: str | None) -> Topic:
    check_version(t, if_match)
    fields = data.model_dump(exclude_unset=True)
    if "name" in fields and fields["name"] and _name_taken(session, Topic, fields["name"], exclude_id=t.id):
        raise AppError(409, "Topic exists", f"A topic called “{fields['name']}” already exists.")
    if "group_id" in fields:
        _check_group(session, fields["group_id"])
    renamed = "name" in fields and fields["name"] != t.name
    changed = False
    for k, v in fields.items():
        if k in ("name", "color", "sort_order") and v is None:
            continue
        if getattr(t, k) != v:
            setattr(t, k, v)
            changed = True
    if changed:
        touch(session, t)
    if renamed:
        search.reindex(session, _member_ids(session, t.id))
    return t


def delete_topic(session: Session, t: Topic) -> None:
    """Soft-delete the topic; its bookmarks stay, they just leave the topic."""
    members = _member_ids(session, t.id, include_deleted=True)
    session.query(BookmarkTopic).filter(BookmarkTopic.topic_id == t.id).delete(synchronize_session=False)
    t.deleted_at = utcnow()
    touch(session, t)
    for b in session.scalars(select(Bookmark).where(Bookmark.id.in_(members))):
        touch(session, b)
    session.expire_all()
    search.reindex(session, members)


def _member_ids(session: Session, topic_id: str, include_deleted: bool = False) -> list[str]:
    stmt = (select(BookmarkTopic.bookmark_id).join(Bookmark, Bookmark.id == BookmarkTopic.bookmark_id)
            .where(BookmarkTopic.topic_id == topic_id))
    if not include_deleted:
        stmt = stmt.where(Bookmark.deleted_at.is_(None))
    return list(session.scalars(stmt))


# ---------- learning order ----------

def _live_links(session: Session, topic_id: str) -> list[BookmarkTopic]:
    return list(session.scalars(
        select(BookmarkTopic).join(Bookmark, Bookmark.id == BookmarkTopic.bookmark_id)
        .where(BookmarkTopic.topic_id == topic_id, Bookmark.deleted_at.is_(None))
        .order_by(BookmarkTopic.sort_order, BookmarkTopic.bookmark_id)
    ))


def _bump(session: Session, bookmark_ids: list[str]) -> None:
    for b in session.scalars(select(Bookmark).where(Bookmark.id.in_(bookmark_ids))):
        touch(session, b)


def set_order(session: Session, t: Topic, bookmark_ids: list[str]) -> None:
    links = _live_links(session, t.id)
    by_id = {l.bookmark_id: l for l in links}
    if len(bookmark_ids) != len(set(bookmark_ids)) or set(bookmark_ids) != set(by_id):
        raise AppError(409, "Order is out of date",
                       "The list must contain exactly the bookmarks currently in this topic; reload and try again.")
    changed = []
    for i, bid in enumerate(bookmark_ids, start=1):
        new = i * ORDER_GAP
        if by_id[bid].sort_order != new:
            by_id[bid].sort_order = new
            changed.append(bid)
    _bump(session, changed)


def move(session: Session, t: Topic, data: TopicMove) -> None:
    links = _live_links(session, t.id)
    ids = [l.bookmark_id for l in links]
    if data.bookmark_id not in ids:
        raise AppError(422, "Bookmark is not in this topic")
    if data.before_id is not None and data.before_id not in ids:
        raise AppError(422, "before_id is not in this topic")
    if data.before_id == data.bookmark_id:
        return
    moving = next(l for l in links if l.bookmark_id == data.bookmark_id)
    rest = [l for l in links if l is not moving]
    idx = len(rest) if data.before_id is None else next(i for i, l in enumerate(rest) if l.bookmark_id == data.before_id)
    prev = rest[idx - 1].sort_order if idx > 0 else None
    nxt = rest[idx].sort_order if idx < len(rest) else None
    if prev is None and nxt is None:
        new = ORDER_GAP
    elif prev is None:
        new = nxt - ORDER_GAP
    elif nxt is None:
        new = prev + ORDER_GAP
    else:
        new = (prev + nxt) / 2
    if (prev is not None and new - prev < MIN_GAP) or (nxt is not None and nxt - new < MIN_GAP):
        # Gaps exhausted: renumber the whole topic.
        rest.insert(idx, moving)
        set_order(session, t, [l.bookmark_id for l in rest])
        return
    if moving.sort_order != new:
        moving.sort_order = new
        _bump(session, [moving.bookmark_id])


# ---------- groups ----------

def group_out(g: TopicGroup) -> GroupOut:
    return GroupOut(id=g.id, name=g.name, sort_order=g.sort_order, version=g.version)


def list_groups(session: Session) -> list[GroupOut]:
    rows = session.scalars(select(TopicGroup).where(TopicGroup.deleted_at.is_(None)).order_by(TopicGroup.sort_order)).all()
    return [group_out(g) for g in rows]


def get_group(session: Session, group_id: str) -> TopicGroup:
    g = session.get(TopicGroup, group_id)
    if g is None or g.deleted_at is not None:
        raise not_found("Topic group")
    return g


def create_group(session: Session, data: GroupCreate) -> TopicGroup:
    if _name_taken(session, TopicGroup, data.name):
        raise AppError(409, "Group exists")
    last = session.scalar(select(func.max(TopicGroup.sort_order)))
    g = TopicGroup(name=data.name, sort_order=(last or 0) + ORDER_GAP)
    stamp_new(session, g)
    session.add(g)
    session.flush()
    return g


def update_group(session: Session, g: TopicGroup, data: GroupUpdate, if_match: str | None) -> TopicGroup:
    check_version(g, if_match)
    if data.name and _name_taken(session, TopicGroup, data.name, exclude_id=g.id):
        raise AppError(409, "Group exists")
    changed = False
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None and getattr(g, k) != v:
            setattr(g, k, v)
            changed = True
    if changed:
        touch(session, g)
    return g


def delete_group(session: Session, g: TopicGroup) -> None:
    """Soft-delete a group; its topics become ungrouped."""
    for t in session.scalars(select(Topic).where(Topic.group_id == g.id, Topic.deleted_at.is_(None))):
        t.group_id = None
        touch(session, t)
    g.deleted_at = utcnow()
    touch(session, g)

