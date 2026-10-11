from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from learnmarks.core.db import get_session
from learnmarks.schemas import TagCreate, TagMerge, TagOut, TagUpdate
from learnmarks.services import tags as svc

router = APIRouter(prefix="/tags", tags=["tags"])
SessionDep = Annotated[Session, Depends(get_session)]


def _out(session: Session, tag_id: str) -> TagOut:
    return next(t for t in svc.list_tags(session) if t.id == tag_id)


@router.get("", response_model=list[TagOut])
def list_tags(session: SessionDep, q: str | None = None):
    return svc.list_tags(session, q)


@router.post("", response_model=TagOut, status_code=201)
def create_tag(session: SessionDep, body: TagCreate):
    t = svc.create_tag(session, body.name)
    session.commit()
    return _out(session, t.id)


@router.patch("/{tag_id}", response_model=TagOut)
def rename_tag(session: SessionDep, tag_id: str, body: TagUpdate):
    t = svc.rename_tag(session, svc.get_tag(session, tag_id), body.name)
    session.commit()
    return _out(session, t.id)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(session: SessionDep, tag_id: str):
    svc.delete_tag(session, svc.get_tag(session, tag_id))
    session.commit()
    return Response(status_code=204)


@router.post("/{tag_id}/merge", response_model=TagOut)
def merge_tag(session: SessionDep, tag_id: str, body: TagMerge):
    target = svc.merge_tag(session, svc.get_tag(session, tag_id), svc.get_tag(session, body.into_id))
    session.commit()
    return _out(session, target.id)
