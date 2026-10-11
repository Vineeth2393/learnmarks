"""Imports (DESIGN §11).

Three formats are parsed into one neutral shape (`ImportData`), then `run()` applies it.
A dry run executes exactly the same code inside the transaction and rolls it back, so the
report you preview is the report you get.

Rules: matching is by canonical URL (bookmarks) and case-insensitive name (topics, tracks,
tags). An import never overwrites what you already have: existing bookmarks only gain
missing topics/tags and an empty takeaway is filled. Re-running an import changes nothing.
"""

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from learnmarks.models import Bookmark, BookmarkTag, BookmarkTopic, Tag, Topic, TopicGroup
from learnmarks.services import search
from learnmarks.services.bookmarks import ORDER_GAP, append_position, get_or_create_tags
from learnmarks.services.canonical import InvalidURL, default_title, for_item
from learnmarks.services.changes import stamp_new, touch

FORMATS = ("ai-learning-path", "learnmarks", "csv")
MAX_ROWS = 50_000
MAX_MESSAGES = 300
PALETTE = ["#C9CDBB", "#E9C9C3", "#EFD98A", "#BCC6D6", "#D5C6E6", "#A9CCC9", "#E6D3B8", "#D9D9DC"]
LEVELS = {"beginner", "intermediate", "advanced", "any"}
STATUS_ALIASES = {
    "saved": "saved", "to learn": "to_learn", "to_learn": "to_learn", "todo": "to_learn",
    "in progress": "in_progress", "in_progress": "in_progress", "doing": "in_progress",
    "learned": "learned", "done": "learned",
}
PRIORITY_ALIASES = {"1": 1, "low": 1, "2": 2, "medium": 2, "med": 2, "3": 3, "high": 3}
REVIEW_TAG = "needs-review"


class ImportFailed(ValueError):
    """The file as a whole can't be imported (wrong format, broken JSON, too big)."""


# ---------- neutral shape ----------

@dataclass
class GroupRow:
    name: str
    id: str | None = None


@dataclass
class TopicRow:
    name: str
    description: str | None = None
    color: str | None = None
    level: str | None = None
    group: str | None = None
    id: str | None = None


@dataclass
class BookmarkRow:
    ref: str  # where it came from, for messages ("row 12", "m3 item 4")
    url: str
    title: str | None = None
    date_saved: date | None = None
    description: str | None = None
    status: str = "saved"
    priority: int = 2
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    id: str | None = None
    created_at: datetime | None = None
    status_changed_at: datetime | None = None


@dataclass
class ImportData:
    groups: list[GroupRow] = field(default_factory=list)
    topics: list[TopicRow] = field(default_factory=list)
    bookmarks: list[BookmarkRow] = field(default_factory=list)
    # topic name → indexes into `bookmarks`, in learning order
    members: dict[str, list[int]] = field(default_factory=dict)
    # tag name → id to keep (Learnmarks exports), so a round trip keeps tag ids
    tag_ids: dict[str, str] = field(default_factory=dict)
    messages: list["Message"] = field(default_factory=list)

    def note(self, level: str, ref: str, text: str) -> None:
        self.messages.append(Message(level=level, ref=ref, text=text))


class Message(BaseModel):
    level: str  # info | warn | error
    ref: str
    text: str


class Summary(BaseModel):
    rows_total: int = 0
    rows_skipped: int = 0
    groups_created: int = 0
    topics_created: int = 0
    topics_matched: int = 0
    tags_created: int = 0
    bookmarks_created: int = 0
    bookmarks_matched: int = 0
    bookmarks_updated: int = 0
    links_added: int = 0


class Report(BaseModel):
    format: str
    dry_run: bool
    summary: Summary
    messages: list[Message]
    messages_truncated: int = 0
    backup: str | None = None


# ---------- parsers ----------

def parse(fmt: str, raw: bytes) -> ImportData:
    if fmt not in FORMATS:
        raise ImportFailed(f"Unknown format “{fmt}”. Use one of: {', '.join(FORMATS)}.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ImportFailed("The file is not UTF-8 text.") from e
    if fmt == "csv":
        return parse_csv(text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ImportFailed(f"The file is not valid JSON (line {e.lineno}: {e.msg}).") from e
    if not isinstance(obj, dict):
        raise ImportFailed("Expected a JSON object at the top level.")
    return parse_learning_path(obj) if fmt == "ai-learning-path" else parse_learnmarks(obj)


def _clip(data: ImportData, ref: str, what: str, value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if len(value) > limit:
        data.note("warn", ref, f"{what} shortened to {limit} characters")
        value = value[:limit].rstrip()
    return value or None


def _date(data: ImportData, ref: str, value) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        data.note("warn", ref, f"Date “{value}” not understood; today's date used")
        return None


def _datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _tag(value) -> str | None:
    if not isinstance(value, str):
        return None
    t = " ".join(value.split())[:60]
    return t or None


def parse_learning_path(obj: dict) -> ImportData:
    """ai-learning-path/path.json, optionally wrapped as {"path": …, "progress": {done, notes}}."""
    path, progress = (obj.get("path"), obj.get("progress")) if "path" in obj else (obj, None)
    if not isinstance(path, dict) or not isinstance(path.get("tracks"), list):
        raise ImportFailed("This doesn't look like path.json: it has no “tracks” list.")
    done = (progress or {}).get("done") or {}
    notes = (progress or {}).get("notes") or {}
    if progress is not None and not isinstance(done, dict):
        raise ImportFailed("Progress file: “done” must be an object keyed by post id.")

    data = ImportData()
    colour = 0
    for ti, track in enumerate(path["tracks"]):
        tname = _clip(data, f"track {ti + 1}", "Track name", track.get("name"), 80)
        if not tname:
            data.note("error", f"track {ti + 1}", "Track has no name; skipped")
            continue
        data.groups.append(GroupRow(name=tname))
        for mi, module in enumerate(track.get("modules") or []):
            mref = f"{track.get('id', ti + 1)}/{module.get('id', mi + 1)}"
            mname = _clip(data, mref, "Topic name", module.get("name"), 80)
            if not mname:
                data.note("error", mref, "Module has no name; skipped")
                continue
            level = module.get("level") if module.get("level") in LEVELS else None
            data.topics.append(TopicRow(name=mname, description=_clip(data, mref, "Description", module.get("why"), 2000),
                                        color=PALETTE[colour % len(PALETTE)], level=level, group=tname))
            colour += 1
            members = data.members.setdefault(mname.lower(), [])
            for ii, item in enumerate(module.get("items") or []):
                ref = f"{mref} item {ii + 1}"
                row = _learning_path_item(data, ref, item, done, notes)
                if row:
                    members.append(len(data.bookmarks))
                    data.bookmarks.append(row)
    for ri, item in enumerate(path.get("review") or []):
        row = _learning_path_item(data, f"review {ri + 1}", item, done, notes, review=True)
        if row:
            data.bookmarks.append(row)
    if progress is not None:
        data.note("info", "progress", f"Progress file: {sum(1 for v in done.values() if v)} learned, {len(notes)} notes")
    return data


def _learning_path_item(data, ref, item, done, notes, review=False) -> BookmarkRow | None:
    pid, handle = str(item.get("id", "")), item.get("handle")
    if not re.fullmatch(r"\d{1,25}", pid) or not isinstance(handle, str) or not handle:
        data.note("error", ref, "Missing post id or handle; skipped")
        return None
    parts = [item.get("summary"), item.get("learn")]
    if notes.get(pid):
        parts.append(f"Note: {notes[pid]}")
    description = "\n\n".join(str(p).strip() for p in parts if p)
    tags = [] if review else [t for t in (_tag(item.get("level")), _tag(item.get("kind"))) if t]
    if review:
        tags.append(REVIEW_TAG)
    return BookmarkRow(
        ref=ref, url=f"https://x.com/{handle}/status/{pid}",
        title=_clip(data, ref, "Title", item.get("title"), 300),
        date_saved=_date(data, ref, item.get("date")),
        description=_clip(data, ref, "Takeaway", description, 2000),
        status="learned" if done.get(pid) else ("saved" if review else "to_learn"),
        source="x", tags=tags,
    )


def parse_learnmarks(obj: dict) -> ImportData:
    if obj.get("format") != "learnmarks":
        raise ImportFailed("This isn't a Learnmarks export (missing \"format\": \"learnmarks\").")
    if obj.get("version") != 1:
        raise ImportFailed(f"Unsupported export version {obj.get('version')!r}; this app reads version 1.")
    data = ImportData()
    group_names = {}
    for g in obj.get("groups") or []:
        name = _clip(data, "group", "Track name", g.get("name"), 80)
        if name:
            group_names[g.get("id")] = name
            data.groups.append(GroupRow(name=name, id=g.get("id")))
    topic_names = {}
    for t in sorted(obj.get("topics") or [], key=lambda t: t.get("sort_order") or 0):
        name = _clip(data, "topic", "Topic name", t.get("name"), 80)
        if not name:
            continue
        topic_names[t.get("id")] = name
        color = t.get("color") if isinstance(t.get("color"), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", t["color"]) else None
        data.topics.append(TopicRow(name=name, description=_clip(data, name, "Description", t.get("description"), 2000),
                                    color=color, level=t.get("level") if t.get("level") in LEVELS else None,
                                    group=group_names.get(t.get("group_id")), id=t.get("id")))
    tag_names = {t.get("id"): _tag(t.get("name")) for t in obj.get("tags") or []}
    data.tag_ids = {name.lower(): tid for tid, name in tag_names.items() if name and isinstance(tid, str)}

    ordered: dict[str, list[tuple[float, int]]] = {}
    for i, b in enumerate(obj.get("bookmarks") or []):
        ref = f"bookmark {i + 1}"
        status = b.get("status") if b.get("status") in STATUS_ALIASES.values() else "saved"
        priority = b.get("priority") if b.get("priority") in (1, 2, 3) else 2
        row = BookmarkRow(
            ref=ref, url=str(b.get("url") or ""), title=_clip(data, ref, "Title", b.get("title"), 300),
            date_saved=_date(data, ref, b.get("date_saved")),
            description=_clip(data, ref, "Takeaway", b.get("description"), 2000),
            status=status, priority=priority,
            source=b.get("source_platform") if b.get("source_platform") in ("x", "linkedin", "other") else None,
            tags=[n for n in (tag_names.get(tid) for tid in b.get("tag_ids") or []) if n],
            id=b.get("id"), created_at=_datetime(b.get("created_at")),
            status_changed_at=_datetime(b.get("status_changed_at")),
        )
        idx = len(data.bookmarks)
        data.bookmarks.append(row)
        for link in b.get("topics") or []:
            name = topic_names.get(link.get("topic_id"))
            if name:
                ordered.setdefault(name.lower(), []).append((float(link.get("sort_order") or 0), idx))
    for key, pairs in ordered.items():
        data.members[key] = [idx for _, idx in sorted(pairs)]
    return data


def _split(cell: str | None) -> list[str]:
    return [p.strip() for p in re.split(r"[;|]", cell or "") if p.strip()]


def parse_csv(text: str) -> ImportData:
    """Columns (header row, any order, case-insensitive): url, title, date_saved, topics, tags,
    status, priority, description, track. Each row needs a url or a title (a title alone makes a
    checklist item without a link). Topics and tags are separated by ; or |. `track` puts the
    row's new topics in that track."""
    data = ImportData()
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportFailed("The CSV file is empty.")
    cols = {c.strip().lower(): c for c in reader.fieldnames if c}
    if "url" not in cols and "title" not in cols:
        raise ImportFailed("The CSV needs a “url” or “title” column. Found: " + ", ".join(reader.fieldnames))

    def get(r, name):
        return (r.get(cols[name]) or "").strip() if name in cols else ""

    known_topics: set[str] = set()
    for n, r in enumerate(reader, start=2):
        ref = f"row {n}"
        status_raw = get(r, "status").lower()
        status = STATUS_ALIASES.get(status_raw, "saved")
        if status_raw and status_raw not in STATUS_ALIASES:
            data.note("warn", ref, f"Status “{get(r, 'status')}” not recognised; Saved used")
        prio_raw = get(r, "priority").lower()
        priority = PRIORITY_ALIASES.get(prio_raw, 2)
        if prio_raw and prio_raw not in PRIORITY_ALIASES:
            data.note("warn", ref, f"Priority “{get(r, 'priority')}” not recognised; Medium used")
        idx = len(data.bookmarks)
        data.bookmarks.append(BookmarkRow(
            ref=ref, url=get(r, "url"), title=_clip(data, ref, "Title", get(r, "title"), 300),
            date_saved=_date(data, ref, get(r, "date_saved") or get(r, "date")),
            description=_clip(data, ref, "Takeaway", get(r, "description"), 2000),
            status=status, priority=priority, tags=[t for t in (_tag(x) for x in _split(get(r, "tags"))) if t],
        ))
        track = get(r, "track")[:80] or None
        if track and track.lower() not in {g.name.lower() for g in data.groups}:
            data.groups.append(GroupRow(name=track))
        for tname in _split(get(r, "topics")):
            tname = tname[:80]
            if tname.lower() not in known_topics:
                known_topics.add(tname.lower())
                data.topics.append(TopicRow(name=tname, group=track))
            data.members.setdefault(tname.lower(), []).append(idx)
        if len(data.bookmarks) > MAX_ROWS:
            raise ImportFailed(f"Too many rows (over {MAX_ROWS}).")
    return data


# ---------- apply ----------

def run(session: Session, fmt: str, data: ImportData, *, dry_run: bool) -> Report:
    """Apply `data` in the current transaction. The caller commits; dry runs are rolled back here."""
    s = Summary(rows_total=len(data.bookmarks))
    msgs = list(data.messages)

    groups = _match_or_create_groups(session, data, s)
    topics = _match_or_create_topics(session, data, groups, s)
    tags_before = session.scalar(select(func.count()).select_from(Tag).where(Tag.deleted_at.is_(None)))
    _create_tags_with_ids(session, data)

    rows: list[Bookmark | None] = []
    touched: dict[str, Bookmark] = {}
    seen: dict[str, Bookmark] = {}
    for row in data.bookmarks:
        b = _bookmark(session, row, seen, s, msgs)
        rows.append(b)
        if b is not None:
            touched[b.id] = b

    # Topic links, in the file's learning order; links that already exist keep their place.
    for key, idxs in data.members.items():
        topic = topics.get(key)
        if topic is None:
            continue
        have = set(session.scalars(select(BookmarkTopic.bookmark_id).where(BookmarkTopic.topic_id == topic.id)))
        nxt = append_position(session, topic.id)
        for i in idxs:
            b = rows[i]
            if b is None or b.id in have:
                continue
            b.topic_links.append(BookmarkTopic(topic_id=topic.id, sort_order=nxt))
            nxt += ORDER_GAP
            have.add(b.id)
            s.links_added += 1
            _mark_updated(session, b, s)

    session.flush()
    s.tags_created = (session.scalar(select(func.count()).select_from(Tag).where(Tag.deleted_at.is_(None))) or 0) - (tags_before or 0)
    search.reindex(session, touched.keys())

    report = Report(format=fmt, dry_run=dry_run, summary=s, messages=msgs[:MAX_MESSAGES],
                    messages_truncated=max(0, len(msgs) - MAX_MESSAGES))
    if dry_run:
        session.rollback()
    return report


def _create_tags_with_ids(session: Session, data: ImportData) -> None:
    wanted = {name.lower(): name for row in data.bookmarks for name in row.tags}
    for key, tid in data.tag_ids.items():
        if key not in wanted:
            continue
        exists = session.scalars(select(Tag).where(func.lower(Tag.name) == key, Tag.deleted_at.is_(None))).first()
        if exists is None and (fid := _free_id(session, Tag, tid)):
            tag = Tag(id=fid, name=wanted[key])
            stamp_new(session, tag)
            session.add(tag)
    session.flush()


def _free_id(session: Session, model, wanted: str | None) -> str | None:
    if wanted and re.fullmatch(r"[0-9a-f-]{36}", wanted) and session.get(model, wanted) is None:
        return wanted
    return None


def _match_or_create_groups(session: Session, data: ImportData, s: Summary) -> dict[str, TopicGroup]:
    out: dict[str, TopicGroup] = {}
    for g in data.groups:
        key = g.name.lower()
        if key in out:
            continue
        found = session.scalars(select(TopicGroup).where(func.lower(TopicGroup.name) == key, TopicGroup.deleted_at.is_(None))).first()
        if found is None:
            last = session.scalar(select(func.max(TopicGroup.sort_order)).where(TopicGroup.deleted_at.is_(None))) or 0
            found = TopicGroup(name=g.name, sort_order=last + ORDER_GAP)
            if (fid := _free_id(session, TopicGroup, g.id)):
                found.id = fid
            stamp_new(session, found)
            session.add(found)
            session.flush()
            s.groups_created += 1
        out[key] = found
    return out


def _match_or_create_topics(session: Session, data: ImportData, groups: dict[str, TopicGroup], s: Summary) -> dict[str, Topic]:
    out: dict[str, Topic] = {}
    existing_count = session.scalar(select(func.count()).select_from(Topic).where(Topic.deleted_at.is_(None))) or 0
    for t in data.topics:
        key = t.name.lower()
        if key in out:
            continue
        found = session.scalars(select(Topic).where(func.lower(Topic.name) == key, Topic.deleted_at.is_(None))).first()
        if found is not None:
            s.topics_matched += 1
        else:
            group = groups.get(t.group.lower()) if t.group else None
            same_group = Topic.group_id.is_(None) if group is None else Topic.group_id == group.id
            last = session.scalar(select(func.max(Topic.sort_order)).where(same_group, Topic.deleted_at.is_(None))) or 0
            found = Topic(name=t.name, description=t.description, level=t.level,
                          color=t.color or PALETTE[(existing_count + s.topics_created) % len(PALETTE)],
                          group_id=group.id if group else None, sort_order=last + ORDER_GAP)
            if (fid := _free_id(session, Topic, t.id)):
                found.id = fid
            stamp_new(session, found)
            session.add(found)
            session.flush()
            s.topics_created += 1
        out[key] = found
    return out


def _bookmark(session: Session, row: BookmarkRow, seen: dict[str, Bookmark], s: Summary, msgs: list[Message]) -> Bookmark | None:
    try:
        c = for_item(row.url, row.title)
    except InvalidURL as e:
        msgs.append(Message(level="error", ref=row.ref, text=f"Skipped: {e}"))
        s.rows_skipped += 1
        return None

    tags = get_or_create_tags(session, row.tags) if row.tags else []
    b = seen.get(c.canonical_url)
    if b is not None:
        msgs.append(Message(level="info", ref=row.ref, text=f"Same post appears earlier in the file; merged into “{b.title}”"))
    else:
        b = session.scalars(select(Bookmark).where(Bookmark.canonical_url == c.canonical_url, Bookmark.deleted_at.is_(None))).first()
        if b is not None:
            s.bookmarks_matched += 1
        else:
            now = datetime.now(UTC)
            b = Bookmark(url=c.clean_url, canonical_url=c.canonical_url, title=row.title or default_title(c),
                         source_platform=row.source or c.source_platform, author_handle=c.author_handle,
                         date_saved=row.date_saved or date.today(), description=row.description, status=row.status,
                         status_changed_at=row.status_changed_at or now, priority=row.priority)
            if row.created_at:
                b.created_at = row.created_at
            if (fid := _free_id(session, Bookmark, row.id)):
                b.id = fid
            stamp_new(session, b)
            session.add(b)
            session.flush()
            s.bookmarks_created += 1
            b._lm_new = True  # type: ignore[attr-defined]
        seen[c.canonical_url] = b

    if row.description and not b.description:
        b.description = row.description
        _mark_updated(session, b, s)
    have = {l.tag_id for l in b.tag_links}
    for t in tags:
        if t.id not in have:
            b.tag_links.append(BookmarkTag(tag=t))
            have.add(t.id)
            _mark_updated(session, b, s)
    return b


def _mark_updated(session: Session, b: Bookmark, s: Summary) -> None:
    """Bump an existing bookmark once per import (new ones are already at version 1)."""
    if getattr(b, "_lm_new", False) or getattr(b, "_lm_touched", False):
        return
    touch(session, b)
    b._lm_touched = True  # type: ignore[attr-defined]
    s.bookmarks_updated += 1
