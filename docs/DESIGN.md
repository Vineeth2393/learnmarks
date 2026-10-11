# Learnmarks — Design

A private, single-user app for collecting learning bookmarks from X and LinkedIn,
organising them into topics with a learning order, finding them fast, and
tracking progress. A laptop web app is the primary data source; an Android
app (Pixel 9) works offline and exchanges changes with the laptop **only over
a USB cable**.

- UI mockup (8 screens): https://claude.ai/artifact/PYEJyGFJbW7voZqU4R63Bf
- Status: design approved 2026-10-10; Phases 1–4 built and verified end to end on the emulator (web MVP; import/export/backups; Android app; USB sync). Next: Phase 5 — real-device run on the Pixel 9, sync property tests, docs.

---

## 1. Decisions

| Topic | Decision |
|---|---|
| Where the web app runs | Laptop only, bound to `127.0.0.1`. No phone-browser access; the Android app is the only phone interface. No HTTPS or hosting needed. |
| Server database | **SQLite** now (WAL mode, FTS5). PostgreSQL later (Phase 6), kept cheap by SQLAlchemy + Alembic and a search interface. |
| Sync transport | **`adb reverse` tunnel over USB**: the phone calls the laptop's sync API at `127.0.0.1:8765`. USB debugging is enabled on the Pixel 9. Fallback: the same JSON messages as files. |
| Laptop sync helper | Built into the backend (`POST /api/v1/sync/usb/start`), runs fixed `adb` arguments only. |
| Phone edits to existing bookmarks | Status, priority, takeaway (single-field ops) + add/remove topics and tags (set ops). Everything else is web-only. |
| Phone capture | **Share-to-save in the first mobile release.** Creates bookmarks offline; server de-duplicates by canonical URL. |
| Topic creation | Web only. Phone picks existing topics; may create tags. |
| Learning order | `sort_order` per bookmark-in-topic; drag-and-drop on web; phone shows order but cannot reorder (v1). |
| Existing data | Phase 2 imports `ai-learning-path/path.json` (modules → topics, tracks → topic groups, order kept) plus progress exported from the old artifact's database. |
| UI style | Inspired by fanout.sh: off-white canvas, grotesk + mono pairing (Hanken Grotesk + JetBrains Mono), pastel topic cards, mono pill labels. No copied branding or artwork. |
| Conflicts | Field-level three-way merge. Only real both-sides changes become conflicts; nothing is overwritten silently. |

---

## 2. Architecture

```text
 LAPTOP (macOS)                                         PIXEL 9
┌──────────────────────────────────────────────┐      ┌───────────────────────────────────┐
│ Browser → React SPA (served by backend)      │      │ Kotlin + Jetpack Compose UI       │
│              │ http://127.0.0.1:8000         │      │   Home · Topics · Search · Add    │
│              ▼                               │      │   Bookmark · Sync                 │
│ FastAPI  /api/v1/*   (web, session/local)    │      │        │                          │
│          /sync/v1/*  (device token)          │      │ Room/SQLite  + FTS5 + outbox      │
│              │                               │      │        │                          │
│              ▼                               │      │ SyncClient → http://127.0.0.1:8765│
│ SQLite (learnmarks.db, WAL) + backups/       │      │        │                          │
│                                              │      └────────┼──────────────────────────┘
│ adb reverse tcp:8765 tcp:8000  ══════ USB cable ═════════════╛
└──────────────────────────────────────────────┘
```

One backend process serves the API and the built SPA. The phone never uses
Wi-Fi or mobile data for sync; it only uses the network to open a post.

### Repository layout

```text
learnmarks/
  docs/DESIGN.md
  backend/                FastAPI app (uv project)
    learnmarks/
      api/                routers: bookmarks, topics, tags, dashboard, io, sync
      core/               config, db session, security
      models.py           SQLAlchemy models
      schemas.py          Pydantic request/response models
      services/           canonical_url, search, bookmarks, importer, sync
    migrations/           Alembic
    tests/
  web/                    React + TypeScript + Vite + Tailwind
  android/                Kotlin app (Phase 3)
  shared/
    url-cases.json        canonical-URL test vectors used by Python AND Kotlin tests
```

---

## 3. Technology

| Layer | Choice |
|---|---|
| Web | React 19, TypeScript, Vite, Tailwind CSS, TanStack Query, React Router, dnd-kit (reorder) |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, uvicorn; managed with `uv` |
| Database | SQLite 3.5x with FTS5 and WAL; one file `data/learnmarks.db` |
| Android | Kotlin, Jetpack Compose (Material 3, custom styling), Room, kotlinx.serialization, OkHttp |
| Sync | `adb` from Homebrew `android-platform-tools` (Phase 4) |
| No Docker | Not needed: SQLite is a file; everything runs natively. |

---

## 4. Data model (SQLite)

Common columns on **syncable** tables (`bookmarks`, `topics`, `tags`):

| Column | Notes |
|---|---|
| `id` TEXT PK | UUID v4, generated by whichever side creates the row; never reused. |
| `created_at`, `updated_at` TEXT | UTC ISO-8601. Display/audit only — never used to decide conflicts. |
| `version` INTEGER | Starts at 1; +1 on every change. Web edits send `If-Match`. |
| `server_seq` INTEGER | Value of the global change counter at last change. Drives incremental pull. |
| `deleted_at` TEXT NULL | Soft delete (tombstone). |

`server_seq` comes from a one-row table `change_counter(value)`, incremented
inside the same write transaction. SQLite allows one writer at a time, so
sequence order equals commit order.

### Tables

**topic_groups** — `id`, `name`, `sort_order`, common columns. (Tracks: "AI Engineering path", "Supporting skills".)

**topics** — `name` (unique among non-deleted, `COLLATE NOCASE`, 1–80 chars), `description` NULL, `color` (`#RRGGBB`), `group_id` NULL → topic_groups, `sort_order`, `level` NULL (`beginner|intermediate|advanced|any`), common columns.

**tags** — `name` (unique among non-deleted, `COLLATE NOCASE`, 1–60 chars), common columns.

**bookmarks**

| Column | Notes |
|---|---|
| `url` | As pasted; `http`/`https` only; ≤ 2048 chars. |
| `canonical_url` | Duplicate key (§4.1). Unique among non-deleted rows. |
| `title` | 1–300 chars. |
| `source_platform` | `x`, `linkedin`, `other` (CHECK). |
| `author_handle` | NULL; e.g. `_avichawla` (from URL or import). |
| `date_saved` | `YYYY-MM-DD`; user-editable. |
| `description` | NULL; personal takeaway, ≤ 2000 chars. |
| `status` | `saved`, `to_learn`, `in_progress`, `learned` (CHECK). Any transition allowed. |
| `status_changed_at` | For future revision scheduling. |
| `priority` | 1 low, 2 medium (default), 3 high. |

**bookmark_topics** — `bookmark_id`, `topic_id`, `sort_order` REAL, `created_at`; PK (bookmark_id, topic_id).
`sort_order` uses gaps (1000, 2000, …; midpoint on insert-between) so a move touches one row; the server renumbers a topic when gaps run out.

**bookmark_tags** — `bookmark_id`, `tag_id`, `created_at`; PK (bookmark_id, tag_id).

Association changes (topics, tags, order) bump the **bookmark's** `version` and `server_seq`;
the bookmark record carries its links when synced. Deleting a topic/tag soft-deletes it,
removes its links and bumps affected bookmarks in one transaction.

**Sync tables**

| Table | Purpose |
|---|---|
| `devices` | `id`, `name`, `token_hash` (sha256 of a 256-bit random token — high-entropy, so a slow password hash adds nothing), `paired_at`, `last_seen_at`, `acked_seq`, `revoked_at` |
| `pairing_codes` | `code_hash`, `expires_at` (5 min), `used_at` |
| `sync_sessions` | the sync log: device, transport, start/end, outcome, op counts, `from_seq`/`to_seq`, error |
| `applied_ops` | `op_id` PK → stored result (`applied`, `noop`, `merged`, `conflict`, `rejected`, later `resolved`) and `canonical_id`; makes pushes idempotent and tells a re-sent conflict op when it has been settled |
| `sync_conflicts` | op, bookmark, field, base/mobile/server values, kind (`field`, `edit_vs_delete`, `duplicate_create`), resolution |
| *(backups)* | not a table: the `data/backups/` folder is the catalogue — each `.db` copy has a sidecar `.json` with kind, sha256 and row counts, so restoring an old database never loses track of newer backups |

**Search** — FTS5 table `bookmark_fts(title, description, url, author, topics, tags)`
kept in sync by the service layer on every bookmark/topic/tag change. It is an index,
not a second source of truth, and can be rebuilt from the tables at any time.

### 4.1 Canonical URL (duplicate detection)

1. Only `http`/`https`. Lower-case host; strip `www.`, `mobile.`, `m.`.
2. X: hosts `x.com`, `twitter.com`, `mobile.twitter.com`, `fxtwitter.com`, `vxtwitter.com`; path `/{handle}/status/{id}` or `/i/status/{id}` (also `/i/web/status/{id}`) → **`x:status:{id}`**; handle captured into `author_handle`.
3. LinkedIn: `/feed/update/urn:li:activity:{id}`, `/feed/update/urn:li:share:{id}`, `/posts/…-activity-{id}-…` → **`linkedin:activity:{id}`** (or `linkedin:share:{id}`).
4. Others: drop fragment, trailing slash and tracking params (`utm_*`, `s`, `t`, `ref`, `ref_src`, `si`, `fbclid`, `gclid`); sort remaining params → `url:{host}{path}?{query}`.

Test vectors live in `shared/url-cases.json` so Python and Kotlin agree.

---

## 5. Web API (`/api/v1`)

Local-only: the server checks `Host` ∈ {`127.0.0.1:8000`, `localhost:8000`} and, on
state-changing requests, `Origin` matches. Optional passphrase lock later.
Errors: `application/problem+json`. Updates require `If-Match: <version>` → `412` with
the current record on mismatch.

| Method & path | Purpose |
|---|---|
| `GET /dashboard` | totals, by status, by source, topic groups with per-topic counts, continue item, recent 10, needs-review count |
| `GET /bookmarks` | `q`, `topic`, `tag[]`, `tag_mode=any|all`, `source[]`, `status[]`, `priority[]`, `saved_from`, `saved_to`, `sort=order|date_saved|title|priority|status`, `dir`, `limit` ≤ 100, `offset` → `{items, total}` (`sort=order` requires `topic`) |
| `GET /bookmarks/check-url?url=` | `{canonical_url, source_platform, author_handle, existing_id?}` |
| `POST /bookmarks` | create; `409` + `existing_id` on duplicate; unknown tag names created |
| `GET /bookmarks/{id}` | detail with topics (+ position) and tags |
| `PATCH /bookmarks/{id}` | partial update (`If-Match`) incl. `topic_ids`, `tag_names` |
| `DELETE /bookmarks/{id}` | soft delete · `POST /bookmarks/{id}/restore` undo |
| `POST /bookmarks/bulk` | status change / add or remove topic or tag for many ids |
| `GET /topics` · `POST` · `PATCH /topics/{id}` · `DELETE` | with counts by status; delete never deletes bookmarks |
| `PUT /topics/{id}/order` | `{bookmark_ids: [...]}` full order, or `POST /topics/{id}/move` `{bookmark_id, before_id?}` |
| `GET /topic-groups` · `POST` · `PATCH` · `DELETE` | tracks |
| `GET /tags?q=` · `POST` · `PATCH /tags/{id}` · `DELETE` · `POST /tags/{id}/merge` | tags with counts |
| `GET /export` | full JSON backup (no secrets) |
| `POST /import?dry_run=true|false&format=learnmarks|ai-learning-path|csv` | validate → diff report; apply after automatic backup |
| `GET /backups` · `POST /backups` · `POST /backups/{id}/restore` | backup & restore |
| `GET /sync/devices` · `DELETE /sync/devices/{id}` · `POST /sync/pairing-codes` | devices |
| `GET /sync/log` · `GET /sync/conflicts` · `POST /sync/conflicts/{id}/resolve` | sync admin |
| `POST /sync/usb/start` · `POST /sync/usb/stop` | run fixed `adb reverse` commands |
| `GET /sync/bundles/export?device_id=` · `POST /sync/bundles/import` | file fallback |

### Device API (`/sync/v1`, bearer device token)

| Method & path | Body → response |
|---|---|
| `POST /pair` | `{code, device_id, device_name}` → `{device_token}` (shown once) |
| `GET /status` | `{server_time, protocol_version, high_water_seq, pending_for_device, open_conflicts}` |
| `POST /sessions` | `{transport, app_version, protocol_version}` → `{session_id}` |
| `POST /push` | `{session_id, batch_id, ops[≤500]}` → `{results[{op_id, result, server_version?, canonical_id?, conflict_id?, error?}]}` |
| `GET /pull?since=&limit=500` | `{topic_groups[], topics[], tags[], bookmarks[], next_seq, has_more, high_water_seq}` |
| `POST /ack` | `{session_id, acked_seq}` |
| `POST /sessions/{id}/finish` | `{outcome, summary}` |

---

## 6. UI

See the mockup. Screens: Dashboard · Topic (learning order, drag to reorder, status
filters) · Bookmark detail/edit · All bookmarks (search + filter drawer + sort) ·
Tags · Import · Backups · USB sync (session, conflicts, log) · Settings.
Laptop-first layout; still usable down to ~768 px.

Design tokens:

| Token | Value |
|---|---|
| canvas / ink / muted | `#F7F7F8` / `#272727` / `#5F5F66` |
| line | `#E4E4E7` |
| status pills | saved: white; to learn `#F3E2A0`/`#4A3B00`; in progress `#272727`/white; learned `#DCEFE2`/`#1F5C36` |
| warn | `#FCE3D6` / `#8A2E0C` |
| topic palette | sage `#C9CDBB`, rose `#E9C9C3`, mustard `#EFD98A`, slate `#BCC6D6`, lavender `#D5C6E6`, teal `#A9CCC9`, sand `#E6D3B8`, grey `#D9D9DC` |
| type | Hanken Grotesk (UI, headings), JetBrains Mono (labels, numbers, topic titles) |

**Dark mode**: every colour is a token with a light and a dark value (`web/src/styles.css`).
The header toggle cycles System → Light → Dark; System follows the OS setting, and the
choice is remembered in the browser. In dark mode the inverse panels (Continue card,
primary buttons) become light, and pastel topic colours are softened while their text
stays dark. Android follows the phone's system theme with the same token values.

Android uses the same tokens in Compose. Fonts are bundled with the apps (no
runtime font requests).

---

## 7. Android local storage

Room tables: `bookmarks` (+ `serverVersion`; 0 = created on the phone), `topic_groups`, `topics`,
`tags` (+ `localOnly`), `bookmark_topics` (with `sortOrder`), `bookmark_tags`, `outbox`, `sync_state`
(singleton: device_id, pull cursor, last snapshot/success/result/error), `sync_log`,
`bookmark_fts` (**FTS4** — Room's annotations support FTS3/4, not FTS5; prefix queries work the same).

- **Displayed value**: the tables hold the laptop snapshot *with pending phone changes applied*. Each change also writes an outbox op carrying the value it replaced (`base_value`). When a new snapshot arrives (export file now, USB pull in Phase 4) the synced rows are replaced and every pending op is re-applied on top, so the result equals "snapshot + overlay" without a second copy of each row. Pending items show an "unsynced" dot.
- **Bootstrap before USB sync**: the phone can load a web “Download export” file (Sync → Load laptop export) through the system file picker; the export carries each bookmark's `version` so ops get the right `base_version`.
- **Outbox op**: `op_id`, `entity`, `entity_id`, `op` (`set_field`, `add_link`, `remove_link`, `create_bookmark`, `create_tag`), `field`, `base_value`, `new_value`, `payload`, `base_version`, `state` (`pending`, `in_flight`, `conflict`, `rejected`), `attempts`, `last_error`.
- **Coalescing**: a second change to the same field updates the pending op; returning to `base_value` deletes it. Edits to an unsynced phone-created bookmark rewrite its `create_bookmark` payload.
- **Pull never touches the outbox.**
- Database in app-private storage; **excluded from Android Auto Backup**; device token encrypted with an Android Keystore key.

---

## 8. Sync protocol (v1)

### Session

1. Laptop: *Start USB sync session* → backend runs `adb reverse tcp:8765 tcp:8000` (closes after 10 min or on finish).
2. Phone: **Sync Now** → `POST /sessions`.
3. **Push** outbox in order (`create_tag` before `create_bookmark`), batches ≤ 500.
4. Phone applies results: `applied`/`noop`/`merged` → op removed (remapping ids for `merged`); `conflict`/`rejected` → kept and shown.
5. **Pull** pages since cursor; each page applied in one transaction, then cursor advances.
6. `POST /ack {acked_seq}` → server records device position (tombstone GC).
7. `POST /sessions/{id}/finish`; phone records last success.

Push before pull, so the pull already contains the merged result.

As built: the server processes `create_tag` ops first, then `create_bookmark`, then edits
(stable within each group), so a new tag always exists before a bookmark that uses it. An op
that ended in `conflict` stays on the phone and is re-sent each sync; once the conflict is
resolved on the laptop the stored result becomes `resolved` and the phone drops it. The
high-water mark is the change counter itself. Tombstone purging is not implemented yet
(tombstones are kept), so no device ever needs a forced full resync.

### Messages

```json
{"op_id":"…","entity":"bookmark","entity_id":"…","op":"set_field",
 "field":"status","base_value":"to_learn","new_value":"in_progress",
 "base_version":4,"client_time":"2026-10-10T09:12:00Z"}
```

```json
{"op_id":"…","entity":"bookmark","entity_id":"<phone uuid>","op":"create_bookmark",
 "payload":{"url":"…","title":"X post by @handle","date_saved":"2026-10-10",
            "status":"saved","priority":2,"description":null,
            "topic_ids":["…"],"tag_ids":["…"]}}
```

Pulled bookmark records carry all fields plus `version`, `server_seq`, `deleted`,
`topics:[{topic_id, sort_order}]`, `tag_ids`.

File fallback wraps the same payloads in `{format:"lmsync", protocol_version, direction,
device_id, bundle_id, from_seq, to_seq, acked_seq, payload, sha256, hmac}`; written to a
temp name and renamed; checked (size ≤ 20 MB, schema, sha256, HMAC with the device token)
before any write; `bundle_id` recorded so re-import is a no-op.

### Idempotency and interruption

| Failure | Recovery |
|---|---|
| Response to push lost | Retry same `op_id`s → stored result returned, not re-applied. |
| Push half processed | Each op commits on its own; retry finishes the rest. |
| Cable pulled during pull | Cursor advances only after a page commits; next sync refetches. Upserts skip rows whose local `server_version` ≥ incoming. |
| App killed mid-apply | SQLite transaction rolls back. |
| Ack lost | Only delays tombstone GC. |
| Protocol mismatch | `POST /sessions` refuses with a clear message before data moves. |

Ops are removed from the outbox **only** after `applied`, `noop` or `merged`.

---

## 9. Conflict resolution

| Op | Server state | Result |
|---|---|---|
| `set_field` | current == base | **applied** (other fields may have changed — no conflict) |
| `set_field` | current == new | **noop** |
| `set_field` | current ≠ base and ≠ new | **conflict** (field) — server value stays until you choose |
| any edit | bookmark deleted on web | **conflict** (edit_vs_delete) — default keep deleted; *Restore* offered |
| `add_link` / `remove_link` | — | **applied** (set semantics; idempotent). If the topic/tag is deleted → **rejected** with reason. An add that re-adds something the web removed is applied and listed in the sync summary. |
| `create_tag` | name exists | **merged** → `canonical_id` of existing tag |
| `create_bookmark` | canonical URL new | **applied** (phone UUID kept) |
| `create_bookmark` | canonical URL exists | **merged** → `canonical_id`; topics and tags unioned; server title/status/priority kept; phone takeaway fills an empty description; differing takeaways → field conflict |
| unknown id / invalid value | — | **rejected**, kept on phone with error |

Resolution (web, USB sync screen): *Keep laptop*, *Use phone*, or for takeaway
*Keep both*. Suggested default for status is the further-along value, applied only
when you click. Resolving bumps `server_seq`; the phone clears the op on the next pull.

**Deletions** propagate web → phone as tombstones. The phone cannot delete synced
bookmarks in v1 (it can discard its own unsynced captures). Tombstones are purged after
90 days once every active device's `acked_seq` has passed them; a device behind the purge
horizon gets a full resync (its outbox is pushed first).

---

## 10. Security and privacy

- Backend binds to `127.0.0.1` only; `Host`/`Origin` checks block DNS-rebinding and cross-site requests from other tabs; optional passphrase lock.
- Device API needs a per-device token (argon2-hashed server-side); revocable; tunnel open only during a session.
- Strict Pydantic validation, unknown fields rejected, length caps, enum checks, URL scheme allowlist (`http`, `https`).
- Imports and bundles are untrusted: size cap, schema, checksum/HMAC, dry run, automatic pre-import backup, single transaction; file names never taken from content; nothing executed.
- React escaping; no raw HTML; external links `rel="noopener noreferrer"`.
- No outbound requests from the server in v1 (no scraping, no telemetry).
- Exports contain no secrets. Backups: a daily `VACUUM INTO` copy while the server runs (keep 14), plus automatic copies before every import and restore (keep 10 each); manual backups are never pruned. Restore checks integrity and schema, takes a safety copy, then swaps the file and re-runs migrations.
- USB debugging: only the laptop authorised; Wireless debugging off; `adb` run with fixed arguments.
- Android: app-private DB, excluded from cloud backup, Keystore-wrapped token.
- Any future AI provider key lives in a local environment variable, never in the DB, exports or chat.

---

## 11. Importing existing data

**`ai-learning-path/path.json`** (68 items in 12 modules + 2 review items):

| Source | Target |
|---|---|
| track (`ai`, `support`) | topic group |
| module (`m0`…`m7`, `s1`…`s4`) | topic; `name`, `why` → description, `level`, colour from palette, `sort_order` by position |
| item `id` + `handle` | `url = https://x.com/{handle}/status/{id}`, canonical `x:status:{id}`, `author_handle` |
| `title`, `date` | title, date_saved |
| `summary` + `learn` | description |
| `level`, `kind` | tags |
| position in module | `bookmark_topics.sort_order` |
| `review[]` | bookmark with tag `needs-review`, no topic |
| progress / notes (old artifact DB, keyed by tweet id) | status / appended to description — via a one-time JSON export |

Re-running the import is idempotent (matched on canonical URL). Imports never overwrite
existing bookmarks: they only add missing topic links and tags and fill an empty takeaway.
A dry run executes the import in a transaction and rolls it back, so the preview equals
the result. Other formats: a Learnmarks export (round-trips ids, tags and topic order) and
CSV (`url,title,date_saved,topics,tags,status,priority,description`; `;` or `|` between
topics/tags) for LinkedIn and manual lists.

Note (2026-10-11): the old syllabus page never saved progress to its database
(`progress/main` does not exist), so there is no progress to bring over unless a
`{done, notes}` file is exported from that browser's local storage.

---

## 12. Roadmap

| Phase | Deliverables | Acceptance criteria |
|---|---|---|
| **1. Web MVP** | Schema (incl. UUID, version, server_seq, soft delete, sort_order); canonical URL + duplicate check; bookmarks/topics/groups/tags CRUD; FTS search + filters + sort; learning order + drag reorder; dashboard; fanout-style UI | Add/edit/delete/restore; duplicate paste detected; filters combine; search over 5,000 seeded rows < 200 ms p95; reorder persists |
| **2. Data integrity** | `path.json` importer + generic CSV/JSON; dry-run reports; export; backups & restore; `If-Match` everywhere | Import of `path.json` reproduces 12 topics / 70 bookmarks with order; re-import changes nothing; restore round-trips; malformed files rejected with no partial write |
| **3. Android** | Room + FTS; first load from file bundle; Home, Topics, Search, Bookmark, Share-to-save; outbox; tokens | Fully usable in airplane mode; search < 100 ms on 5,000 rows; changes survive kill/reboot; Share from X and LinkedIn apps works |
| **4. USB sync** | Pairing; device API; `adb` session control; push/pull/ack; merge + conflicts; sync screens both sides; file fallback | Every scenario in §8–9 passes; repeated sync is a no-op; cable pull at any step loses nothing; conflicts visible and never auto-overwritten |
| **5. Test & docs** | Property-based sync tests, security tests, backup drill, setup guide | All suites green; documented restore drill; fresh setup < 30 min |
| **6. PostgreSQL** | Migrate via JSON export/import keeping `server_seq`; search via tsvector + pg_trgm; optional pgvector | Row counts + checksums match; phone continues without full resync |

Deferred: AI summaries/categorisation, scraping, vector search/RAG, recommendations,
spaced revision, browser extension, advanced analytics, multi-user.

---

## 13. Testing

| Area | Tests |
|---|---|
| Unit | canonical URL (shared vectors), merge rules (every row of §9), outbox coalescing, sort_order gap logic |
| API | contract tests from OpenAPI; 409/412 paths; Host/Origin checks |
| Sync | property-based: random edits both sides + random interruption point → convergence, no lost ops |
| Idempotency | same push ×3, same bundle ×2, same pull page ×2 → identical state |
| Offline | airplane-mode run of every phone feature; reboot with pending ops |
| Security | fuzzed/oversized bundles, bad HMAC, revoked token, `javascript:` URLs, exports free of secrets |
| UI | Playwright smoke at 1280 and 768 px |
| Backup | scripted backup → wipe → restore → compare counts + checksums |
