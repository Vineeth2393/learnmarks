"""Dashboard summary (DESIGN §5 GET /dashboard)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from learnmarks.models import Bookmark, BookmarkTag, BookmarkTopic, Tag, Topic, TopicGroup
from learnmarks.schemas import ContinueItem, Dashboard, DashGroup, DashTopic, StatusCounts
from learnmarks.services import bookmarks as bsvc
from learnmarks.services.topics import status_counts

REVIEW_TAG = "needs-review"


def build(session: Session) -> Dashboard:
    live = Bookmark.deleted_at.is_(None)

    counts = StatusCounts()
    for status, n in session.execute(select(Bookmark.status, func.count()).where(live).group_by(Bookmark.status)):
        setattr(counts, status, n)
        counts.total += n
    by_source = {"x": 0, "linkedin": 0, "other": 0}
    by_source.update(dict(session.execute(
        select(Bookmark.source_platform, func.count()).where(live).group_by(Bookmark.source_platform)).all()))

    topics = session.scalars(select(Topic).where(Topic.deleted_at.is_(None))
                             .order_by(Topic.sort_order, func.lower(Topic.name))).all()
    groups = session.scalars(select(TopicGroup).where(TopicGroup.deleted_at.is_(None))
                             .order_by(TopicGroup.sort_order)).all()
    tcounts = status_counts(session)
    previews = _previews(session)

    dash_groups: list[DashGroup] = []
    for g in [*groups, None]:
        members = [t for t in topics if t.group_id == (g.id if g else None)]
        if not members:
            continue
        dts = [DashTopic(id=t.id, name=t.name, color=t.color, level=t.level, number=f"{i:02d}",
                         counts=tcounts.get(t.id, StatusCounts()), preview=previews.get(t.id, []))
               for i, t in enumerate(members, start=1)]
        member_ids = [t.id for t in members]
        n = session.scalar(select(func.count(func.distinct(BookmarkTopic.bookmark_id)))
                           .join(Bookmark, Bookmark.id == BookmarkTopic.bookmark_id)
                           .where(BookmarkTopic.topic_id.in_(member_ids), live))
        dash_groups.append(DashGroup(id=g.id if g else None, name=g.name if g else "Other topics",
                                     topics=dts, bookmark_count=n or 0))

    recent_ids = list(session.scalars(select(Bookmark.id).where(live)
                                      .order_by(Bookmark.date_saved.desc(), Bookmark.created_at.desc()).limit(8)))
    recent = bsvc.to_out(session, bsvc.load_many(session, recent_ids))

    linked = (select(BookmarkTopic.bookmark_id).join(Topic, Topic.id == BookmarkTopic.topic_id)
              .where(Topic.deleted_at.is_(None)))
    review_tagged = (select(BookmarkTag.bookmark_id).join(Tag, Tag.id == BookmarkTag.tag_id)
                     .where(func.lower(Tag.name) == REVIEW_TAG, Tag.deleted_at.is_(None)))
    needs_review = session.scalar(select(func.count()).select_from(Bookmark)
                                  .where(live, or_(Bookmark.id.not_in(linked), Bookmark.id.in_(review_tagged)))) or 0

    return Dashboard(counts=counts, by_source=by_source, topic_count=len(topics), groups=dash_groups,
                     continue_item=_continue(session, topics), recent=recent, needs_review=needs_review)


def _previews(session: Session, per_topic: int = 3) -> dict[str, list[str]]:
    rn = func.row_number().over(partition_by=BookmarkTopic.topic_id,
                                order_by=(BookmarkTopic.sort_order, BookmarkTopic.bookmark_id)).label("rn")
    sub = (select(BookmarkTopic.topic_id, Bookmark.title, rn)
           .join(Bookmark, Bookmark.id == BookmarkTopic.bookmark_id)
           .where(Bookmark.deleted_at.is_(None)).subquery())
    out: dict[str, list[str]] = {}
    for tid, title, _ in session.execute(select(sub).where(sub.c.rn <= per_topic).order_by(sub.c.topic_id, sub.c.rn)):
        out.setdefault(tid, []).append(title)
    return out


def _continue(session: Session, topics) -> ContinueItem | None:
    bid = session.scalar(select(Bookmark.id).where(Bookmark.deleted_at.is_(None), Bookmark.status == "in_progress")
                         .order_by(Bookmark.status_changed_at.desc()).limit(1))
    if bid is None:
        return None
    out = bsvc.to_out(session, bsvc.load_many(session, [bid]))[0]
    if not out.topics:
        return ContinueItem(bookmark=out, topic_name=None, topic_number=None, position=None, topic_total=None)
    ref = out.topics[0]
    topic = next(t for t in topics if t.id == ref.id)
    siblings = [t for t in topics if t.group_id == topic.group_id]
    number = f"{siblings.index(topic) + 1:02d}"
    total = status_counts(session, [ref.id]).get(ref.id, StatusCounts()).total
    return ContinueItem(bookmark=out, topic_name=ref.name, topic_number=number, position=ref.position, topic_total=total)
