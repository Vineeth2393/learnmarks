"""FTS5 index maintenance and querying (DESIGN §4 "Search")."""

import json
import re
from collections.abc import Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from learnmarks.models import Bookmark, BookmarkTag, BookmarkTopic, Tag, Topic

_TOKEN = re.compile(r"\w+", re.UNICODE)


def reindex(session: Session, bookmark_ids: Iterable[str]) -> None:
    ids = list(dict.fromkeys(bookmark_ids))
    if not ids:
        return
    session.flush()
    session.execute(text("DELETE FROM bookmark_fts WHERE bookmark_id IN (SELECT value FROM json_each(:ids))"),
                    {"ids": json.dumps(ids)})
    rows = session.execute(
        select(Bookmark.id, Bookmark.title, Bookmark.description, Bookmark.url, Bookmark.author_handle)
        .where(Bookmark.id.in_(ids), Bookmark.deleted_at.is_(None))
    ).all()
    if not rows:
        return
    live = [r.id for r in rows]
    topics = _names_by_bookmark(session, select(BookmarkTopic.bookmark_id, Topic.name)
                                .join(Topic, Topic.id == BookmarkTopic.topic_id)
                                .where(BookmarkTopic.bookmark_id.in_(live), Topic.deleted_at.is_(None)))
    tags = _names_by_bookmark(session, select(BookmarkTag.bookmark_id, Tag.name)
                              .join(Tag, Tag.id == BookmarkTag.tag_id)
                              .where(BookmarkTag.bookmark_id.in_(live), Tag.deleted_at.is_(None)))
    session.execute(
        text("INSERT INTO bookmark_fts (bookmark_id, title, description, url, author, topics, tags) "
             "VALUES (:id, :title, :description, :url, :author, :topics, :tags)"),
        [
            {"id": r.id, "title": r.title, "description": r.description or "", "url": r.url,
             "author": r.author_handle or "", "topics": " ".join(topics.get(r.id, [])),
             "tags": " ".join(tags.get(r.id, []))}
            for r in rows
        ],
    )


def rebuild(session: Session) -> None:
    session.execute(text("DELETE FROM bookmark_fts"))
    ids = session.scalars(select(Bookmark.id).where(Bookmark.deleted_at.is_(None))).all()
    for i in range(0, len(ids), 500):
        reindex(session, ids[i:i + 500])


def match_query(q: str) -> str | None:
    """Turn free text into a safe FTS5 query: every word must match, as a prefix."""
    tokens = _TOKEN.findall(q or "")
    if not tokens:
        return None
    return " ".join(f'"{t}"*' for t in tokens[:12])


def search_ids(session: Session, q: str, limit: int = 5000) -> list[str]:
    fts = match_query(q)
    if fts is None:
        return []
    return list(session.scalars(
        text("SELECT bookmark_id FROM bookmark_fts WHERE bookmark_fts MATCH :q ORDER BY bm25(bookmark_fts, 0, 10, 4, 1, 2, 6, 6) LIMIT :n"),
        {"q": fts, "n": limit},
    ))


def _names_by_bookmark(session: Session, stmt) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for bid, name in session.execute(stmt):
        out.setdefault(bid, []).append(name)
    return out

