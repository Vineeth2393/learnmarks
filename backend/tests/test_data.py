import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from learnmarks.core.config import Settings
from learnmarks.main import create_app
from tests.conftest import BASE

REAL_PATH = Path(__file__).resolve().parents[3] / "ai-learning-path" / "path.json"

PATH = {
    "tracks": [
        {"id": "ai", "name": "AI Engineering path", "modules": [
            {"id": "m0", "name": "Start here: the map", "level": "beginner", "why": "The landscape first.", "items": [
                {"id": "101", "handle": "alice", "date": "2026-09-13", "level": "beginner", "kind": "visual",
                 "title": "GenAI cheat sheets", "summary": "Four sheets.", "learn": "The whole field."},
                {"id": "102", "handle": "bob", "date": "2026-09-27", "level": "beginner", "kind": "thread",
                 "title": "The AI engineering stack", "summary": "Stage by stage.", "learn": "An order."},
            ]},
            {"id": "m2", "name": "RAG", "level": "intermediate", "why": "Your data at query time.", "items": [
                {"id": "201", "handle": "carol", "date": "2026-09-24", "level": "beginner", "kind": "visual",
                 "title": "RAG pipelines", "summary": "Chunking etc.", "learn": "The parts."},
                {"id": "202", "handle": "dave", "date": "2026-09-27", "level": "intermediate", "kind": "visual",
                 "title": "RAG decisions", "summary": "Six knobs.", "learn": "Where quality is won."},
                {"id": "203", "handle": "erin", "date": "2026-09-29", "level": "intermediate", "kind": "visual",
                 "title": "RAG stack", "summary": "Tools.", "learn": "Which tool where."},
            ]},
        ]},
        {"id": "support", "name": "Supporting skills", "modules": [
            {"id": "s1", "name": "Python", "level": "beginner", "why": "The language.", "items": [
                {"id": "301", "handle": "frank", "date": "2026-07-27", "level": "beginner", "kind": "thread",
                 "title": "Get good at Python", "summary": "A plan.", "learn": "Fluency."},
            ]},
        ]},
    ],
    "review": [{"id": "901", "handle": "grace", "author": "Grace", "date": "2026-09-27", "note": "No text captured"}],
}


def do_import(client: TestClient, fmt: str, body, dry_run: bool, expect=200):
    content = body if isinstance(body, (bytes, str)) else json.dumps(body)
    r = client.post(f"/api/v1/import?format={fmt}&dry_run={'true' if dry_run else 'false'}", content=content)
    assert r.status_code == expect, r.text
    return r.json()


def order(api, topic_name):
    tid = next(t["id"] for t in api.get("/topics") if t["name"] == topic_name)
    return [b["title"] for b in api.get("/bookmarks", params={"topic": tid, "sort": "order", "limit": 100})["items"]]


def test_dry_run_reports_and_changes_nothing(client, api):
    r = do_import(client, "ai-learning-path", PATH, dry_run=True)
    assert r["dry_run"] is True and r["backup"] is None
    s = r["summary"]
    assert (s["groups_created"], s["topics_created"], s["bookmarks_created"], s["links_added"]) == (2, 3, 7, 6)
    assert s["rows_total"] == 7 and s["rows_skipped"] == 0
    assert api.get("/dashboard")["counts"]["total"] == 0
    assert api.get("/topics") == [] and api.get("/tags") == []


def test_apply_learning_path(client, api, settings):
    r = do_import(client, "ai-learning-path", PATH, dry_run=False)
    assert r["backup"].endswith("-pre_import.db")
    assert (settings.backups_dir / r["backup"]).is_file()

    d = api.get("/dashboard")
    assert d["counts"]["total"] == 7 and d["counts"]["to_learn"] == 6 and d["counts"]["saved"] == 1
    assert [g["name"] for g in d["groups"]] == ["AI Engineering path", "Supporting skills"]
    assert [t["name"] for t in d["groups"][0]["topics"]] == ["Start here: the map", "RAG"]
    assert order(api, "RAG") == ["RAG pipelines", "RAG decisions", "RAG stack"]

    rag = next(t for t in api.get("/topics") if t["name"] == "RAG")
    assert rag["level"] == "intermediate" and rag["description"] == "Your data at query time."

    b = api.get("/bookmarks", params={"q": "cheat sheets"})["items"][0]
    assert b["url"] == "https://x.com/alice/status/101" and b["date_saved"] == "2026-09-13"
    assert b["description"] == "Four sheets.\n\nThe whole field."
    assert {t["name"] for t in b["tags"]} == {"beginner", "visual"}

    review = api.get("/bookmarks", params={"no_topic": True})["items"]
    assert [(x["title"], x["status"], [t["name"] for t in x["tags"]]) for x in review] == \
        [("X post by @grace", "saved", ["needs-review"])]
    assert d["needs_review"] == 1


def test_reimport_is_a_no_op(client, api):
    do_import(client, "ai-learning-path", PATH, dry_run=False)
    before = {b["id"]: b["version"] for b in api.get("/bookmarks", params={"limit": 100})["items"]}
    s = do_import(client, "ai-learning-path", PATH, dry_run=False)["summary"]
    assert (s["bookmarks_created"], s["bookmarks_matched"], s["bookmarks_updated"], s["links_added"]) == (0, 7, 0, 0)
    assert (s["groups_created"], s["topics_created"], s["topics_matched"], s["tags_created"]) == (0, 0, 3, 0)
    after = {b["id"]: b["version"] for b in api.get("/bookmarks", params={"limit": 100})["items"]}
    assert after == before


def test_import_never_overwrites_existing(client, api):
    mine = api.bookmark("https://twitter.com/carol/status/201?s=20", title="My own title", status="learned",
                        description="My takeaway")
    s = do_import(client, "ai-learning-path", PATH, dry_run=False)["summary"]
    assert s["bookmarks_created"] == 6 and s["bookmarks_matched"] == 1 and s["bookmarks_updated"] == 1
    got = api.get(f"/bookmarks/{mine['id']}")
    assert (got["title"], got["status"], got["description"]) == ("My own title", "learned", "My takeaway")
    assert [t["name"] for t in got["topics"]] == ["RAG"]  # but it joins the topic, in path order
    assert order(api, "RAG")[0] == "My own title"


def test_progress_file(client, api):
    body = {"path": PATH, "progress": {"done": {"201": True, "301": True}, "notes": {"202": "Re-read the reranking part"}}}
    r = do_import(client, "ai-learning-path", body, dry_run=False)
    assert any("2 learned, 1 notes" in m["text"] for m in r["messages"])
    items = {b["title"]: b for b in api.get("/bookmarks", params={"limit": 100})["items"]}
    assert items["RAG pipelines"]["status"] == "learned" and items["Get good at Python"]["status"] == "learned"
    assert items["RAG decisions"]["description"].endswith("Note: Re-read the reranking part")


def test_export_round_trip_preserves_everything(client, api, tmp_path):
    do_import(client, "ai-learning-path", PATH, dry_run=False)
    t = next(t for t in api.get("/topics") if t["name"] == "RAG")
    ids = [b["id"] for b in api.get("/bookmarks", params={"topic": t["id"], "sort": "order"})["items"]]
    api.put(f"/topics/{t['id']}/order", {"bookmark_ids": list(reversed(ids))})
    r = client.get("/api/v1/export")
    assert r.headers["content-disposition"].startswith('attachment; filename="learnmarks-export-')
    exported = r.json()
    assert exported["format"] == "learnmarks" and len(exported["bookmarks"]) == 7
    assert "token" not in json.dumps(exported).lower()

    other = TestClient(create_app(Settings(data_dir=tmp_path / "other", web_dist=tmp_path / "x", auto_backup=False)),
                       base_url=BASE)
    s = do_import(other, "learnmarks", exported, dry_run=False)["summary"]
    assert (s["bookmarks_created"], s["topics_created"], s["groups_created"]) == (7, 3, 2)
    again = other.get("/api/v1/export").json()
    for doc in (exported, again):
        doc.pop("exported_at")
        for t in doc["topics"]:
            t.pop("version")
        for b in doc["bookmarks"]:
            b.pop("updated_at")
            b.pop("version")
            for link in b["topics"]:
                link.pop("sort_order")  # renumbered on import; the order itself is checked below
    assert again == exported
    rag2 = next(t for t in other.get("/api/v1/topics").json() if t["name"] == "RAG")
    titles = [b["title"] for b in other.get("/api/v1/bookmarks", params={"topic": rag2["id"], "sort": "order"}).json()["items"]]
    assert titles == ["RAG stack", "RAG decisions", "RAG pipelines"]


def test_csv_import(client, api):
    csv_text = (
        "URL,Title,Topics,Tags,Status,Priority,date_saved,description\n"
        "https://www.linkedin.com/posts/jane_rag-activity-7245123456789012345-AbCd,LinkedIn RAG post,RAG; Evals,rag|linkedin,To learn,high,2026-09-01,Good one\n"
        "https://example.com/blog,A blog,Evals,,done,1,not-a-date,\n"
        "javascript:alert(1),Bad,,,,,,\n"
        "https://www.linkedin.com/feed/update/urn:li:activity:7245123456789012345,Dup,Python,,,,,\n"
        "https://example.com/x,Odd status,,,someday,urgent,,\n"
    )
    r = do_import(client, "csv", csv_text, dry_run=False)
    s = r["summary"]
    assert (s["rows_total"], s["rows_skipped"], s["bookmarks_created"], s["topics_created"]) == (5, 1, 3, 3)
    levels = {(m["ref"], m["level"]) for m in r["messages"]}
    assert ("row 4", "error") in levels and ("row 3", "warn") in levels and ("row 5", "info") in levels
    assert ("row 6", "warn") in levels
    post = api.get("/bookmarks", params={"q": "LinkedIn RAG"})["items"][0]
    assert post["status"] == "to_learn" and post["priority"] == 3 and post["date_saved"] == "2026-09-01"
    assert [t["name"] for t in post["topics"]] == ["RAG", "Evals", "Python"]
    assert order(api, "Evals") == ["LinkedIn RAG post", "A blog"]


@pytest.mark.parametrize("fmt,body,detail", [
    ("ai-learning-path", "{not json", "not valid JSON"),
    ("ai-learning-path", {"something": 1}, "no “tracks” list"),
    ("learnmarks", {"format": "other"}, "isn't a Learnmarks export"),
    ("learnmarks", {"format": "learnmarks", "version": 9}, "Unsupported export version"),
    ("csv", "notes\nabc\n", "needs a “url” or “title” column"),
    ("csv", b"\xff\xfe\x00bad", "not UTF-8"),
])
def test_bad_files_are_rejected_without_changes(client, api, fmt, body, detail):
    r = do_import(client, fmt, body, dry_run=False, expect=422)
    assert detail in r["detail"]
    assert api.get("/dashboard")["counts"]["total"] == 0


def test_backups_create_list_restore(client, api, settings):
    api.bookmark("https://x.com/a/status/1", title="Keep me")
    made = client.post("/api/v1/backups").json()
    assert made["kind"] == "manual" and made["counts"]["bookmarks"] == 1
    api.bookmark("https://x.com/a/status/2", title="Added after the backup")
    assert api.get("/dashboard")["counts"]["total"] == 2

    r = client.post(f"/api/v1/backups/{made['name']}/restore")
    assert r.status_code == 200, r.text
    assert [b["title"] for b in api.get("/bookmarks")["items"]] == ["Keep me"]
    kinds = [b["kind"] for b in client.get("/api/v1/backups").json()]
    assert "pre_restore" in kinds and "manual" in kinds
    # The safety copy holds the state from just before the restore.
    safety = r.json()["safety_backup"]
    client.post(f"/api/v1/backups/{safety}/restore")
    assert api.get("/dashboard")["counts"]["total"] == 2


def test_restore_refuses_bad_names_and_files(client, settings):
    assert client.post("/api/v1/backups/..%2Flearnmarks.db/restore").status_code in (404, 422)
    assert client.post("/api/v1/backups/evil.db/restore").status_code == 422
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    fake = settings.backups_dir / "learnmarks-20260101-000000-manual.db"
    fake.write_bytes(b"not a database")
    r = client.post(f"/api/v1/backups/{fake.name}/restore")
    assert r.status_code == 422


def test_auto_backups_are_pruned(client, settings):
    from learnmarks.services import backup

    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    for day in range(1, 20):
        (settings.backups_dir / f"learnmarks-202609{day:02d}-030000-auto.db").write_bytes(b"x")
    backup.create(settings, "manual")
    autos = [b for b in backup.list_backups(settings) if b.kind == "auto"]
    assert len(autos) == 14 and autos[0].name == "learnmarks-20260919-030000-auto.db"


@pytest.mark.skipif(not REAL_PATH.exists(), reason="ai-learning-path/path.json not present")
def test_real_learning_path_file(client, api):
    raw = REAL_PATH.read_bytes()
    r = client.post("/api/v1/import?format=ai-learning-path&dry_run=true", content=raw).json()
    s = r["summary"]
    assert s["rows_skipped"] == 0 and s["topics_created"] == 12 and s["groups_created"] == 2
    assert s["bookmarks_created"] == s["rows_total"]


def test_csv_checklist_items_without_links(client, api):
    csv_text = (
        "track,topics,title,status\n"
        "Coding interview prep,Arrays,Two Sum,To learn\n"
        "Coding interview prep,Arrays,Rotate an array,To learn\n"
        "Coding interview prep,Strings,Check anagram,\n"
        "Coding interview prep,Recursion,two  SUM,\n"     # same item again (title match) → joins a 2nd topic
        ",Arrays,,\n"                                      # neither url nor title → skipped
    )
    r = do_import(client, "csv", csv_text, dry_run=False)
    s = r["summary"]
    assert (s["bookmarks_created"], s["rows_skipped"], s["groups_created"], s["topics_created"]) == (3, 1, 1, 3)
    d = api.get("/dashboard")
    grp = next(g for g in d["groups"] if g["name"] == "Coding interview prep")
    assert [t["name"] for t in grp["topics"]] == ["Arrays", "Strings", "Recursion"]
    assert order(api, "Arrays") == ["Two Sum", "Rotate an array"]
    two = api.get("/bookmarks", params={"q": "two sum"})["items"][0]
    assert two["url"] == "" and two["canonical_url"] == "note:two sum" and two["status"] == "to_learn"
    assert sorted(t["name"] for t in two["topics"]) == ["Arrays", "Recursion"]
    # Re-import changes nothing.
    again = do_import(client, "csv", csv_text, dry_run=False)["summary"]
    assert again["bookmarks_created"] == 0 and again["links_added"] == 0
