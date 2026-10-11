"""SQLAlchemy models. See docs/DESIGN.md §4 for the data model."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STATUSES = ("saved", "to_learn", "in_progress", "learned")
PLATFORMS = ("x", "linkedin", "other")
LEVELS = ("beginner", "intermediate", "advanced", "any")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, always returns aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


class SyncMixin:
    """Columns every syncable entity carries (DESIGN §4)."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    server_seq: Mapped[int] = mapped_column(Integer, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ChangeCounter(Base):
    __tablename__ = "change_counter"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


class TopicGroup(SyncMixin, Base):
    __tablename__ = "topic_groups"
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[float] = mapped_column(Float, default=0)

    __table_args__ = (
        Index("uq_topic_groups_name", text("name COLLATE NOCASE"), unique=True, sqlite_where=text("deleted_at IS NULL")),
    )


class Topic(SyncMixin, Base):
    __tablename__ = "topics"
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(7), default="#D9D9DC")
    group_id: Mapped[str | None] = mapped_column(ForeignKey("topic_groups.id"), nullable=True, index=True)
    sort_order: Mapped[float] = mapped_column(Float, default=0)
    level: Mapped[str | None] = mapped_column(String(16), nullable=True)

    group: Mapped[TopicGroup | None] = relationship()

    __table_args__ = (
        Index("uq_topics_name", text("name COLLATE NOCASE"), unique=True, sqlite_where=text("deleted_at IS NULL")),
        CheckConstraint("level IS NULL OR level IN ('beginner','intermediate','advanced','any')", name="ck_topics_level"),
    )


class Tag(SyncMixin, Base):
    __tablename__ = "tags"
    name: Mapped[str] = mapped_column(String(60))

    __table_args__ = (
        Index("uq_tags_name", text("name COLLATE NOCASE"), unique=True, sqlite_where=text("deleted_at IS NULL")),
    )


class Bookmark(SyncMixin, Base):
    __tablename__ = "bookmarks"
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(300))
    source_platform: Mapped[str] = mapped_column(String(16))
    author_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_saved: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="saved", index=True)
    status_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    priority: Mapped[int] = mapped_column(Integer, default=2)

    topic_links: Mapped[list["BookmarkTopic"]] = relationship(
        back_populates="bookmark", cascade="all, delete-orphan"
    )
    tag_links: Mapped[list["BookmarkTag"]] = relationship(back_populates="bookmark", cascade="all, delete-orphan")

    __table_args__ = (
        Index("uq_bookmarks_canonical_url", "canonical_url", unique=True, sqlite_where=text("deleted_at IS NULL")),
        CheckConstraint("status IN ('saved','to_learn','in_progress','learned')", name="ck_bookmarks_status"),
        CheckConstraint("source_platform IN ('x','linkedin','other')", name="ck_bookmarks_platform"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="ck_bookmarks_priority"),
    )


class BookmarkTopic(Base):
    __tablename__ = "bookmark_topics"
    bookmark_id: Mapped[str] = mapped_column(ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True, index=True)
    sort_order: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    bookmark: Mapped[Bookmark] = relationship(back_populates="topic_links")
    topic: Mapped[Topic] = relationship()


class BookmarkTag(Base):
    __tablename__ = "bookmark_tags"
    bookmark_id: Mapped[str] = mapped_column(ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    bookmark: Mapped[Bookmark] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship()


# ---------- USB sync (DESIGN §8–9) ----------

class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # chosen by the phone
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of a 256-bit random token
    paired_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acked_seq: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class PairingCode(Base):
    __tablename__ = "pairing_codes"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class SyncSession(Base):
    """The sync log: one row per Sync Now."""

    __tablename__ = "sync_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    transport: Mapped[str] = mapped_column(String(16), default="adb_tunnel")
    app_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="running")  # running | success | partial | failed
    ops_received: Mapped[int] = mapped_column(Integer, default=0)
    ops_applied: Mapped[int] = mapped_column(Integer, default=0)
    ops_conflicted: Mapped[int] = mapped_column(Integer, default=0)
    ops_rejected: Mapped[int] = mapped_column(Integer, default=0)
    rows_sent: Mapped[int] = mapped_column(Integer, default=0)
    from_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppliedOp(Base):
    """Every phone op ever received, with its result: a repeated op gets the same answer (idempotency)."""

    __tablename__ = "applied_ops"
    op_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entity: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    op: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(16))  # applied | noop | merged | conflict | rejected | resolved
    canonical_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conflict_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SyncConflict(Base):
    __tablename__ = "sync_conflicts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    op_id: Mapped[str] = mapped_column(String(36), index=True)
    bookmark_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # field | edit_vs_delete | duplicate_create
    field: Mapped[str | None] = mapped_column(String(20), nullable=True)
    base_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    mobile_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_version: Mapped[int] = mapped_column(Integer)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)  # keep_server | take_mobile | keep_both
    resolved_value: Mapped[str | None] = mapped_column(Text, nullable=True)
