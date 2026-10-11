from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from learnmarks.core.db import get_session
from learnmarks.schemas import (
    GroupCreate,
    GroupOut,
    GroupUpdate,
    TopicCreate,
    TopicMove,
    TopicOrder,
    TopicOut,
    TopicUpdate,
)
from learnmarks.services import topics as svc

router = APIRouter(tags=["topics"])
SessionDep = Annotated[Session, Depends(get_session)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _out(session: Session, topic_id: str) -> TopicOut:
    t = svc.get_topic(session, topic_id)
    return svc.topic_out(t, svc.status_counts(session, [t.id]).get(t.id))


@router.get("/topics", response_model=list[TopicOut])
def list_topics(session: SessionDep):
    return svc.list_topics(session)


@router.post("/topics", response_model=TopicOut, status_code=201)
def create_topic(session: SessionDep, body: TopicCreate):
    t = svc.create_topic(session, body)
    session.commit()
    return _out(session, t.id)


@router.get("/topics/{topic_id}", response_model=TopicOut)
def get_topic(session: SessionDep, topic_id: str):
    return _out(session, topic_id)


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(session: SessionDep, topic_id: str, body: TopicUpdate, if_match: IfMatch = None):
    svc.update_topic(session, svc.get_topic(session, topic_id), body, if_match)
    session.commit()
    return _out(session, topic_id)


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(session: SessionDep, topic_id: str):
    svc.delete_topic(session, svc.get_topic(session, topic_id))
    session.commit()
    return Response(status_code=204)


@router.put("/topics/{topic_id}/order", status_code=204)
def set_order(session: SessionDep, topic_id: str, body: TopicOrder):
    svc.set_order(session, svc.get_topic(session, topic_id), body.bookmark_ids)
    session.commit()
    return Response(status_code=204)


@router.post("/topics/{topic_id}/move", status_code=204)
def move(session: SessionDep, topic_id: str, body: TopicMove):
    svc.move(session, svc.get_topic(session, topic_id), body)
    session.commit()
    return Response(status_code=204)


@router.get("/topic-groups", response_model=list[GroupOut])
def list_groups(session: SessionDep):
    return svc.list_groups(session)


@router.post("/topic-groups", response_model=GroupOut, status_code=201)
def create_group(session: SessionDep, body: GroupCreate):
    g = svc.create_group(session, body)
    session.commit()
    return svc.group_out(g)


@router.patch("/topic-groups/{group_id}", response_model=GroupOut)
def update_group(session: SessionDep, group_id: str, body: GroupUpdate, if_match: IfMatch = None):
    g = svc.update_group(session, svc.get_group(session, group_id), body, if_match)
    session.commit()
    return svc.group_out(g)


@router.delete("/topic-groups/{group_id}", status_code=204)
def delete_group(session: SessionDep, group_id: str):
    svc.delete_group(session, svc.get_group(session, group_id))
    session.commit()
    return Response(status_code=204)
