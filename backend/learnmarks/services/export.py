"""Full JSON export ("learnmarks" format v1). Contains data only — never secrets."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from learnmarks.models import Bookmark, BookmarkTag, BookmarkTopic, Tag, Topic, TopicGroup

FORMAT = "learnmarks"
VERSION = 1


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def build(session: Session) -> dict:
    groups = session.scalars(select(TopicGroup).where(TopicGroup.deleted_at.is_(None)).order_by(TopicGroup.sort_order)).all()
    topics = session.scalars(select(Topic).where(Topic.deleted_at.is_(None)).order_by(Topic.sort_order)).all()
    tags = session.scalars(select(Tag).where(Tag.deleted_at.is_(None)).order_by(func.lower(Tag.name))).all()
    bookmarks = session.scalars(select(Bookmark).where(Bookmark.deleted_at.is_(None))
                                .order_by(Bookmark.date_saved, Bookmark.created_at)).all()
    live_topics = {t.id for t in topics}
    live_tags = {t.id for t in tags}

    links: dict[str, list[dict]] = {}
    for bid, tid, order in session.execute(select(BookmarkTopic.bookmark_id, BookmarkTopic.topic_id, BookmarkTopic.sort_order)):
        if tid in live_topics:
            links.setdefault(bid, []).append({"topic_id": tid, "sort_order": order})
    tag_links: dict[str, list[str]] = {}
    for bid, tid in session.execute(select(BookmarkTag.bookmark_id, BookmarkTag.tag_id)):
        if tid in live_tags:
            tag_links.setdefault(bid, []).append(tid)

    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": _iso(datetime.now(UTC)),
        "groups": [{"id": g.id, "name": g.name, "sort_order": g.sort_order} for g in groups],
        "topics": [{"id": t.id, "name": t.name, "description": t.description, "color": t.color, "level": t.level,
                    "group_id": t.group_id, "sort_order": t.sort_order, "version": t.version} for t in topics],
        "tags": [{"id": t.id, "name": t.name} for t in tags],
        "bookmarks": [{
            "id": b.id, "url": b.url, "title": b.title, "source_platform": b.source_platform,
            "author_handle": b.author_handle, "date_saved": b.date_saved.isoformat(), "description": b.description,
            "status": b.status, "status_changed_at": _iso(b.status_changed_at), "priority": b.priority,
            "created_at": _iso(b.created_at), "updated_at": _iso(b.updated_at), "version": b.version,
            "topics": sorted(links.get(b.id, []), key=lambda l: l["topic_id"]),
            "tag_ids": sorted(tag_links.get(b.id, [])),
        } for b in bookmarks],
    }


def counts(session: Session) -> dict[str, int]:
    def n(model) -> int:
        return session.scalar(select(func.count()).select_from(model).where(model.deleted_at.is_(None))) or 0
    return {"bookmarks": n(Bookmark), "topics": n(Topic), "tags": n(Tag), "groups": n(TopicGroup)}
