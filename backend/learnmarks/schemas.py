"""Request/response models. Strict: unknown fields are rejected, strings are trimmed."""

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Status = Literal["saved", "to_learn", "in_progress", "learned"]
Platform = Literal["x", "linkedin", "other"]
Level = Literal["beginner", "intermediate", "advanced", "any"]


def _hex_color(v: str) -> str:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        raise ValueError("color must look like #A9CCC9")
    return v.upper()


Color = Annotated[str, AfterValidator(_hex_color)]
Title = Annotated[str, Field(min_length=1, max_length=300)]
TagName = Annotated[str, Field(min_length=1, max_length=60)]
TopicName = Annotated[str, Field(min_length=1, max_length=80)]
Description = Annotated[str, Field(max_length=2000)]
Uuid = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------- bookmarks ----------

class TopicRef(BaseModel):
    id: str
    name: str
    color: str
    position: int  # 1-based place in the topic's learning order


class TagRef(BaseModel):
    id: str
    name: str


class BookmarkOut(BaseModel):
    id: str
    url: str
    canonical_url: str
    title: str
    source_platform: Platform
    author_handle: str | None
    date_saved: date
    description: str | None
    status: Status
    status_changed_at: datetime
    priority: int
    created_at: datetime
    updated_at: datetime
    version: int
    deleted: bool
    topics: list[TopicRef]
    tags: list[TagRef]


class BookmarkList(BaseModel):
    items: list[BookmarkOut]
    total: int


class BookmarkCreate(In):
    url: Annotated[str, Field(max_length=2048)] = ""  # empty = checklist item without a link (needs a title)
    title: Title | None = None
    date_saved: date | None = None
    description: Description | None = None
    status: Status = "saved"
    priority: Annotated[int, Field(ge=1, le=3)] = 2
    source_platform: Platform | None = None
    topic_ids: Annotated[list[Uuid], Field(max_length=50)] = []
    tag_names: Annotated[list[TagName], Field(max_length=50)] = []


class BookmarkUpdate(In):
    url: Annotated[str, Field(max_length=2048)] | None = None
    title: Title | None = None
    date_saved: date | None = None
    description: Description | None = None
    status: Status | None = None
    priority: Annotated[int, Field(ge=1, le=3)] | None = None
    source_platform: Platform | None = None
    topic_ids: Annotated[list[Uuid], Field(max_length=50)] | None = None
    tag_names: Annotated[list[TagName], Field(max_length=50)] | None = None


class BulkUpdate(In):
    ids: Annotated[list[Uuid], Field(min_length=1, max_length=500)]
    status: Status | None = None
    priority: Annotated[int, Field(ge=1, le=3)] | None = None
    add_topic_id: Uuid | None = None
    remove_topic_id: Uuid | None = None
    add_tag: TagName | None = None
    remove_tag: TagName | None = None
    delete: bool = False


class BulkResult(BaseModel):
    updated: int


class CheckUrlOut(BaseModel):
    canonical_url: str
    source_platform: Platform
    author_handle: str | None
    suggested_title: str
    existing_id: str | None
    existing_title: str | None


# ---------- topics, groups, tags ----------

class StatusCounts(BaseModel):
    saved: int = 0
    to_learn: int = 0
    in_progress: int = 0
    learned: int = 0
    total: int = 0


class TopicOut(BaseModel):
    id: str
    name: str
    description: str | None
    color: str
    group_id: str | None
    sort_order: float
    level: Level | None
    version: int
    counts: StatusCounts


class TopicCreate(In):
    name: TopicName
    description: Description | None = None
    color: Color = "#D9D9DC"
    group_id: Uuid | None = None
    level: Level | None = None


class TopicUpdate(In):
    name: TopicName | None = None
    description: Description | None = None
    color: Color | None = None
    group_id: Uuid | None = None
    level: Level | None = None
    sort_order: float | None = None


class TopicOrder(In):
    bookmark_ids: Annotated[list[Uuid], Field(max_length=5000)]


class TopicMove(In):
    bookmark_id: Uuid
    before_id: Uuid | None = None  # None = move to the end


class GroupOut(BaseModel):
    id: str
    name: str
    sort_order: float
    version: int


class GroupCreate(In):
    name: TopicName


class GroupUpdate(In):
    name: TopicName | None = None
    sort_order: float | None = None


class TagOut(BaseModel):
    id: str
    name: str
    count: int
    version: int


class TagCreate(In):
    name: TagName


class TagUpdate(In):
    name: TagName


class TagMerge(In):
    into_id: Uuid


# ---------- dashboard ----------

class DashTopic(BaseModel):
    id: str
    name: str
    color: str
    level: Level | None
    number: str
    counts: StatusCounts
    preview: list[str]


class DashGroup(BaseModel):
    id: str | None
    name: str
    topics: list[DashTopic]
    bookmark_count: int


class ContinueItem(BaseModel):
    bookmark: BookmarkOut
    topic_name: str | None
    topic_number: str | None
    position: int | None
    topic_total: int | None


class Dashboard(BaseModel):
    counts: StatusCounts
    by_source: dict[str, int]
    topic_count: int
    groups: list[DashGroup]
    continue_item: ContinueItem | None
    recent: list[BookmarkOut]
    needs_review: int
