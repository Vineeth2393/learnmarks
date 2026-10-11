"""Version and change-sequence bookkeeping shared by every write (DESIGN §4)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from learnmarks.models import SyncMixin, utcnow


def next_seq(session: Session) -> int:
    return session.execute(text("UPDATE change_counter SET value = value + 1 WHERE id = 1 RETURNING value")).scalar_one()


def stamp_new(session: Session, row: SyncMixin) -> None:
    """Give a freshly created row its first server_seq."""
    row.server_seq = next_seq(session)
    row.version = 1


def touch(session: Session, row: SyncMixin) -> None:
    """Record that a row changed: bump version, server_seq and updated_at."""
    row.version = (row.version or 0) + 1
    row.server_seq = next_seq(session)
    row.updated_at = utcnow()
