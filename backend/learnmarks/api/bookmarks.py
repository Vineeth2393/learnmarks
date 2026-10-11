from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from learnmarks.core.db import get_session
from learnmarks.schemas import BookmarkCreate, BookmarkList, BookmarkOut, BookmarkUpdate, BulkResult, BulkUpdate, CheckUrlOut
from learnmarks.services import bookmarks as svc
from learnmarks.services.canonical import default_title

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])
SessionDep = Annotated[Session, Depends(get_session)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


@router.get("", response_model=BookmarkList)
def list_bookmarks(
    session: SessionDep,
    q: str | None = None,
    topic: str | None = None,
    tag: Annotated[list[str], Query()] = [],
    tag_mode: Literal["any", "all"] = "any",
    source: Annotated[list[Literal["x", "linkedin", "other"]], Query()] = [],
    status: Annotated[list[Literal["saved", "to_learn", "in_progress", "learned"]], Query()] = [],
    priority: Annotated[list[int], Query()] = [],
    saved_from: date | None = None,
    saved_to: date | None = None,
    no_topic: bool = False,
    sort: Literal["relevance", "order", "date_saved", "title", "priority", "status", "updated"] | None = None,
    dir: Literal["asc", "desc"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lq = svc.ListQuery(q=q, topic=topic, tags=tag, tag_mode=tag_mode, sources=source, statuses=status,
                       priorities=priority, saved_from=saved_from, saved_to=saved_to, no_topic=no_topic,
                       sort=sort, dir=dir, limit=limit, offset=offset)
    ids = svc.list_ids(session, lq)
    page = svc.load_many(session, ids[offset:offset + limit])
    return BookmarkList(items=svc.to_out(session, page), total=len(ids))


@router.get("/check-url", response_model=CheckUrlOut)
def check_url(session: SessionDep, url: str):
    c = svc.parse_url(url)
    existing = svc.find_live_by_canonical(session, c.canonical_url)
    return CheckUrlOut(canonical_url=c.canonical_url, source_platform=c.source_platform, author_handle=c.author_handle,
                       suggested_title=default_title(c), existing_id=existing.id if existing else None,
                       existing_title=existing.title if existing else None)


@router.post("", response_model=BookmarkOut, status_code=201)
def create_bookmark(session: SessionDep, body: BookmarkCreate):
    b = svc.create(session, body)
    session.commit()
    return svc.one_out(session, b)


@router.post("/bulk", response_model=BulkResult)
def bulk_update(session: SessionDep, body: BulkUpdate):
    n = svc.bulk(session, body)
    session.commit()
    return BulkResult(updated=n)


@router.get("/{bookmark_id}", response_model=BookmarkOut)
def get_bookmark(session: SessionDep, bookmark_id: str):
    return svc.one_out(session, svc.get_live(session, bookmark_id, include_deleted=True))


@router.patch("/{bookmark_id}", response_model=BookmarkOut)
def update_bookmark(session: SessionDep, bookmark_id: str, body: BookmarkUpdate, if_match: IfMatch = None):
    b = svc.update(session, svc.get_live(session, bookmark_id), body, if_match)
    session.commit()
    return svc.one_out(session, b)


@router.delete("/{bookmark_id}", status_code=204)
def delete_bookmark(session: SessionDep, bookmark_id: str):
    svc.delete(session, svc.get_live(session, bookmark_id))
    session.commit()
    return Response(status_code=204)


@router.post("/{bookmark_id}/restore", response_model=BookmarkOut)
def restore_bookmark(session: SessionDep, bookmark_id: str):
    b = svc.restore(session, svc.get_live(session, bookmark_id, include_deleted=True))
    session.commit()
    return svc.one_out(session, b)
