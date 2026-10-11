"""Backups of the SQLite file (DESIGN §10).

Each backup is a consistent copy made with `VACUUM INTO`, plus a small sidecar JSON with
its kind and row counts. The backups folder itself is the catalogue, so restoring an old
database never loses track of the other backups.
"""

import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from learnmarks.core import db
from learnmarks.core.config import Settings
from learnmarks.core.errors import AppError
from learnmarks.services import export

KINDS = ("auto", "manual", "pre_import", "pre_restore")
KEEP = {"auto": 14, "pre_import": 10, "pre_restore": 10}  # manual backups are never pruned
# learnmarks-YYYYmmdd-HHMMSS[mmm]-kind.db (older names have no milliseconds)
NAME_RE = re.compile(r"^learnmarks-(\d{8}-\d{6})(\d{3})?-(auto|manual|pre_import|pre_restore)\.db$")
REQUIRED_TABLES = {"bookmarks", "topics", "tags", "bookmark_topics", "bookmark_tags", "alembic_version"}


@dataclass
class BackupInfo:
    name: str
    kind: str
    created_at: str
    size_bytes: int
    sha256: str
    counts: dict[str, int]


def _sidecar(path: Path) -> Path:
    return path.with_suffix(".json")


def create(settings: Settings, kind: str) -> BackupInfo:
    assert kind in KINDS
    folder = settings.backups_dir
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    name = f"learnmarks-{now:%Y%m%d-%H%M%S}{now.microsecond // 1000:03d}-{kind}.db"
    path = folder / name
    if path.exists():  # two backups in the same millisecond
        raise AppError(429, "A backup was just taken", "Try again in a moment.")

    engine = db.get_engine()
    # VACUUM cannot run inside a transaction, so use a raw connection (autocommit mode).
    raw = engine.raw_connection()
    try:
        raw.cursor().execute("VACUUM INTO ?", (str(path),))
    finally:
        raw.close()
    with Session(engine) as s:
        counts = export.counts(s)
    info = BackupInfo(name=name, kind=kind, created_at=now.isoformat().replace("+00:00", "Z"),
                      size_bytes=path.stat().st_size, sha256=_sha256(path), counts=counts)
    _sidecar(path).write_text(json.dumps(asdict(info), indent=2))
    prune(settings)
    return info


def list_backups(settings: Settings) -> list[BackupInfo]:
    folder = settings.backups_dir
    if not folder.exists():
        return []
    out = []
    for path in folder.glob("learnmarks-*.db"):
        m = NAME_RE.match(path.name)
        if not m:
            continue
        side = _sidecar(path)
        try:
            meta = json.loads(side.read_text())
            out.append(BackupInfo(**meta))
        except (OSError, ValueError, TypeError):
            stamp = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
            out.append(BackupInfo(name=path.name, kind=m.group(3), created_at=stamp.isoformat().replace("+00:00", "Z"),
                                  size_bytes=path.stat().st_size, sha256="", counts={}))
    out.sort(key=lambda b: NAME_RE.match(b.name).group(1) + (NAME_RE.match(b.name).group(2) or "000"), reverse=True)
    return out


def prune(settings: Settings) -> None:
    by_kind: dict[str, list[BackupInfo]] = {}
    for b in list_backups(settings):
        by_kind.setdefault(b.kind, []).append(b)
    for kind, keep in KEEP.items():
        for old in by_kind.get(kind, [])[keep:]:
            path = settings.backups_dir / old.name
            path.unlink(missing_ok=True)
            _sidecar(path).unlink(missing_ok=True)


def latest_auto_age(settings: Settings) -> timedelta | None:
    autos = [b for b in list_backups(settings) if b.kind == "auto"]
    if not autos:
        return None
    newest = datetime.fromisoformat(autos[0].created_at.replace("Z", "+00:00"))
    return datetime.now(UTC) - newest


def resolve(settings: Settings, name: str) -> Path:
    """Map a backup name to its file, refusing anything that isn't one of ours."""
    if not NAME_RE.match(name):
        raise AppError(422, "Not a backup name")
    path = settings.backups_dir / name
    if not path.is_file():
        raise AppError(404, "Backup not found")
    return path


def validate_file(path: Path) -> None:
    """Make sure a file is a healthy Learnmarks database before it replaces the live one."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise AppError(422, "Backup is not a readable database", str(e)) from e
    if ok != "ok":
        raise AppError(422, "Backup failed its integrity check", ok)
    missing = REQUIRED_TABLES - tables
    if missing:
        raise AppError(422, "Backup is missing tables", ", ".join(sorted(missing)))


def restore(settings: Settings, name: str) -> BackupInfo:
    """Replace the live database with a backup. A pre_restore backup is taken first."""
    source = resolve(settings, name)
    validate_file(source)
    safety = create(settings, "pre_restore")

    live = settings.db_path
    staging = live.with_name(live.name + ".restoring")
    shutil.copyfile(source, staging)
    db.close_db()
    for suffix in ("-wal", "-shm"):
        Path(str(live) + suffix).unlink(missing_ok=True)
    staging.replace(live)
    db.init_db(live)  # reconnect and bring an older backup up to the current schema
    with db.get_engine().begin() as conn:
        conn.execute(text("SELECT 1"))
    return safety


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
