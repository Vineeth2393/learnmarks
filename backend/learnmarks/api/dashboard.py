from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from learnmarks.core.db import get_session
from learnmarks.schemas import Dashboard
from learnmarks.services import dashboard as svc

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=Dashboard)
def dashboard(session: Annotated[Session, Depends(get_session)]):
    return svc.build(session)
