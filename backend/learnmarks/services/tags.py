"""Tags: list with counts, create, rename, delete, merge."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from learnmarks.core.errors import AppError, not_found
from learnmarks.models import Bookmark, BookmarkTag, Tag, utcnow
from learnmarks.schemas import TagOut
from learnmarks.services import search
from learnmarks.services.changes import stamp_new, touch


def list_tags(session: Session, q: str | None = None) -> list[TagOut]:
    counts = dict(session.execute(
        select(BookmarkTag.tag_id, func.count()).join(Bookmark, Bookmark.id == BookmarkTag.bookmark_id)
        .where(Bookmark.deleted_at.is_(None)).group_by(BookmarkTag.tag_id)
    ).all())
    stmt = select(Tag).where(Tag.deleted_at.is_(None)).order_by(func.lower(Tag.name))
    if q:
        stmt = stmt.where(func.lower(Tag.name).contains(q.lower().strip()))
    return [TagOut(id=t.id, name=t.name, count=counts.get(t.id, 0), version=t.version) for t in session.scalars(stmt)]


def get_tag(session: Session, tag_id: str) -> Tag:
    t = session.get(Tag, tag_id)
    if t is None or t.deleted_at is not None:
        raise not_found("Tag")
    return t


def _taken(session: Session, name: str, exclude_id: str | None = None) -> bool:
    stmt = select(Tag.id).where(func.lower(Tag.name) == name.lower(), Tag.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(Tag.id != exclude_id)
    return session.scalar(stmt) is not None


def create_tag(session: Session, name: str) -> Tag:
    name = " ".join(name.split())
    if _taken(session, name):
        raise AppError(409, "Tag exists")
    t = Tag(name=name)
    stamp_new(session, t)
    session.add(t)
    session.flush()
    return t


def _members(session: Session, tag_id: str) -> list[str]:
    return list(session.scalars(select(BookmarkTag.bookmark_id).where(BookmarkTag.tag_id == tag_id)))


def rename_tag(session: Session, t: Tag, name: str) -> Tag:
    name = " ".join(name.split())
    if name == t.name:
        return t
    if _taken(session, name, exclude_id=t.id):
        raise AppError(409, "Tag exists", "Use merge to combine two tags.")
    t.name = name
    touch(session, t)
    search.reindex(session, _members(session, t.id))
    return t


def delete_tag(session: Session, t: Tag) -> None:
    members = _members(session, t.id)
    session.query(BookmarkTag).filter(BookmarkTag.tag_id == t.id).delete(synchronize_session=False)
    t.deleted_at = utcnow()
    touch(session, t)
    for b in session.scalars(select(Bookmark).where(Bookmark.id.in_(members))):
        touch(session, b)
    session.expire_all()
    search.reindex(session, members)


def merge_tag(session: Session, source: Tag, target: Tag) -> Tag:
    if source.id == target.id:
        raise AppError(422, "Cannot merge a tag into itself")
    members = _members(session, source.id)
    already = set(_members(session, target.id))
    for bid in members:
        if bid not in already:
            session.add(BookmarkTag(bookmark_id=bid, tag_id=target.id))
    session.flush()
    delete_tag(session, source)
    return target

