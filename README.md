# Learnmarks

A private learning-bookmark manager for posts saved from X and LinkedIn: topics with a
learning order, fast search, and progress tracking. Runs only on this laptop.
Design: [docs/DESIGN.md](docs/DESIGN.md).

## Status

| Phase | State |
|---|---|
| 1. Web MVP | ✅ bookmarks, topics, tracks, tags, search, filters, learning order, dashboard |
| 2. Import, export, backups | ✅ path.json / export / CSV import with preview, JSON export, daily + manual backups, restore |
| 3. Android app | ✅ offline browse/search, topics in learning order, status/priority/takeaway/topic/tag edits with pending-change queue, Share-to-save, load laptop export, dark mode |
| 4. USB sync | ✅ pairing, Sync Now (push/pull/ack), merge + conflicts resolved on the laptop, adb tunnel from the web page, verified end to end on the emulator |

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cd web && npm install && npm run build      # build the UI once (and after UI changes)
cd ../backend && uv run learnmarks serve    # http://127.0.0.1:8000
```

Data lives in `data/learnmarks.db` (SQLite). Set `LEARNMARKS_DATA_DIR` to use another folder.
The server only listens on 127.0.0.1 and rejects requests from other sites.

### Developing

```bash
cd backend && uv run learnmarks serve --reload   # API on :8000
cd web && npm run dev                            # UI on :5173 with hot reload, proxies /api
cd backend && uv run pytest                      # backend tests
cd web && npm run typecheck
```

To load your learning path, open **Import · Backup · Sync**, choose “AI learning path”, pick
`ai-learning-path/path.json`, press **Preview import**, then **Import now**.

A throwaway database filled from `path.json` with random sample statuses (for UI testing only):

```bash
cd backend && LEARNMARKS_DATA_DIR=../data-dev uv run python scripts/seed_dev.py ../../ai-learning-path/path.json
```

## Android app

Requirements: Android Studio (its bundled JDK is enough) and the Android SDK.

```bash
cd android
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
./gradlew testDebugUnitTest      # unit tests (canonical URLs share vectors with the backend)
./gradlew assembleDebug          # APK in app/build/outputs/apk/debug/
./gradlew installDebug           # install on a connected phone (USB debugging on)
```

First data: on the laptop press **Download export**, copy the file to the phone, then in the app
open **Sync → Load laptop export**. Changes made on the phone are kept and shown under Sync until
USB sync (Phase 4) delivers them.

## USB sync (laptop ↔ Pixel)

One-time setup:
1. `brew install android-platform-tools` (gives `adb`; the app also finds Android Studio's copy).
2. On the Pixel: Settings → About phone → tap **Build number** 7 times → System → Developer options → **USB debugging** on.
3. Connect the cable, tap **Allow** on the phone's “Allow USB debugging?” prompt (tick “Always allow from this computer”).
4. Install the app: `cd android && ./gradlew installDebug`.
5. Laptop: **USB sync** page → **Start USB sync session** → **Pair a phone**. Phone: **Sync → Pair** with the code.

Each time: plug in → **Start USB sync session** on the laptop → **Sync Now** on the phone.
Conflicts appear on the laptop's USB sync page; nothing is overwritten until you choose.

## Layout

```text
backend/   FastAPI + SQLAlchemy + Alembic (SQLite, FTS5 search)
web/       React + TypeScript + Tailwind (Vite)
android/   Kotlin + Jetpack Compose + Room (offline app, Share-to-save)
shared/    test vectors shared by backend and Android (canonical URLs)
docs/      design
```
