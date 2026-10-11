from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        # Let SQLAlchemy (not pysqlite) decide when transactions begin.
        dbapi_conn.isolation_level = None
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    # Take the write lock up front so concurrent writers wait instead of failing mid-transaction,
    # and so server_seq order always equals commit order.
    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def init_db(db_path: Path) -> Engine:
    """Create the engine, run migrations and remember the session factory."""
    global _engine, _session_factory
    from learnmarks.core.migrate import upgrade

    _engine = make_engine(db_path)
    upgrade(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def close_db() -> None:
    """Release every pooled connection (needed before swapping the database file)."""
    if _engine is not None:
        _engine.dispose()


def get_engine() -> Engine:
    assert _engine is not None, "init_db() has not been called"
    return _engine


def get_session() -> Iterator[Session]:
    assert _session_factory is not None, "init_db() has not been called"
    with _session_factory() as session:
        yield session
