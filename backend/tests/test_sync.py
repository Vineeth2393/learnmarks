import uuid

import pytest

from learnmarks.services import sync

PHONE = "aaaaaaaa-1111-4111-8111-111111111111"


def uid() -> str:
    return str(uuid.uuid4())


class Phone:
    """Plays the Android app: talks to /sync/v1 the way it does through the adb tunnel."""

    def __init__(self, client, token=None):
        self.c, self.token, self.session = client, token, None

    def call(self, method, path, json=None, expect=200, **params):
        headers = {"host": "127.0.0.1:8765"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        r = self.c.request(method, f"/sync/v1{path}", json=json, headers=headers, params=params or None)
        assert r.status_code == expect, r.text
        return r.json() if r.content else None

    def start(self):
        self.session = self.call("POST", "/sessions", {"protocol_version": 1})["session_id"]

    def push(self, *ops):
        return self.call("POST", "/push", {"session_id": self.session, "batch_id": uid(), "ops": list(ops)})["results"]

    def pull_all(self, since=0, limit=500):
        pages, cur = [], since
        while True:
            p = self.call("GET", "/pull", since=cur, limit=limit, session_id=self.session)
            pages.append(p)
            cur = p["next_seq"]
            if not p["has_more"]:
                return pages, cur


@pytest.fixture
def phone(client):
    code = client.post("/api/v1/sync/pairing-codes").json()["code"]
    token = Phone(client).call("POST", "/pair", {"code": code, "device_id": PHONE, "device_name": "Pixel 9"})["device_token"]
    p = Phone(client, token)
    p.start()
    return p


def set_field(bookmark, field, base, new, op_id=None):
    return {"op_id": op_id or uid(), "entity": "bookmark", "entity_id": bookmark["id"], "op": "set_field",
            "field": field, "base_value": base, "new_value": new, "base_version": bookmark["version"]}


def link(bookmark, kind, field, target):
    return {"op_id": uid(), "entity": "bookmark", "entity_id": bookmark["id"], "op": kind, "field": field,
            "new_value": target, "base_version": bookmark["version"]}


# ---------- pairing & auth ----------

def test_pairing_and_auth(client):
    anon = Phone(client)
    anon.call("GET", "/status", expect=401)
    code = client.post("/api/v1/sync/pairing-codes").json()["code"]
    assert len(code) == 9 and code[4] == "-"
    anon.call("POST", "/pair", {"code": "WRONG-CODE", "device_id": PHONE, "device_name": "Pixel"}, expect=401)
    token = anon.call("POST", "/pair", {"code": code.lower(), "device_id": PHONE, "device_name": "Pixel 9"})["device_token"]
    anon.call("POST", "/pair", {"code": code, "device_id": PHONE, "device_name": "Pixel 9"}, expect=401)  # single use
    p = Phone(client, token)
    assert p.call("GET", "/status")["device_name"] == "Pixel 9"
    assert [d["name"] for d in client.get("/api/v1/sync/devices").json()] == ["Pixel 9"]
    client.delete(f"/api/v1/sync/devices/{PHONE}")
    p.call("GET", "/status", expect=401)
    Phone(client, "made-up-token").call("GET", "/status", expect=401)


def test_too_many_wrong_codes_burns_open_codes(client):
    sync._failed_pairs = 0
    code = client.post("/api/v1/sync/pairing-codes").json()["code"]
    anon = Phone(client)
    for _ in range(sync.MAX_FAILED_PAIRS):
        anon.call("POST", "/pair", {"code": "AAAA-AAAA", "device_id": PHONE, "device_name": "x"}, expect=401)
    anon.call("POST", "/pair", {"code": code, "device_id": PHONE, "device_name": "x"}, expect=429)
    code2 = client.post("/api/v1/sync/pairing-codes").json()["code"]  # a fresh code works again
    anon.call("POST", "/pair", {"code": code2, "device_id": PHONE, "device_name": "x"})


def test_protocol_mismatch_is_refused(phone):
    phone.call("POST", "/sessions", {"protocol_version": 99}, expect=426)


# ---------- set_field ----------

def test_set_field_applied_noop_conflict(api, phone):
    b = api.bookmark("https://x.com/a/status/1", status="to_learn")
    r = phone.push(set_field(b, "status", "to_learn", "in_progress"))
    assert r[0]["result"] == "applied"
    assert api.get(f"/bookmarks/{b['id']}")["status"] == "in_progress"

    # Both sides made the same change → noop
    assert phone.push(set_field(b, "status", "to_learn", "in_progress"))[0]["result"] == "noop"

    # Laptop changed priority meanwhile; phone changes status: different fields never conflict.
    cur = api.get(f"/bookmarks/{b['id']}")
    api.patch(f"/bookmarks/{b['id']}", {"priority": 3}, cur["version"])
    assert phone.push(set_field(b, "status", "in_progress", "learned"))[0]["result"] == "applied"

    # Laptop and phone both change status to different values → conflict, laptop value kept for now.
    cur = api.get(f"/bookmarks/{b['id']}")
    api.patch(f"/bookmarks/{b['id']}", {"status": "saved"}, cur["version"])
    r = phone.push(set_field(b, "status", "learned", "to_learn"))[0]
    assert r["result"] == "conflict" and r["conflict_id"]
    assert api.get(f"/bookmarks/{b['id']}")["status"] == "saved"
    c = api.get("/sync/conflicts")
    assert [(x["field"], x["base_value"], x["mobile_value"], x["server_value"], x["device_name"]) for x in c] == \
        [("status", "learned", "to_learn", "saved", "Pixel 9")]


def test_repeated_push_is_idempotent(api, phone):
    b = api.bookmark("https://x.com/a/status/1", status="to_learn", priority=2)
    op = set_field(b, "priority", "2", "3")
    first = phone.push(op)
    v = api.get(f"/bookmarks/{b['id']}")["version"]
    for _ in range(3):
        assert phone.push(op) == first
    assert api.get(f"/bookmarks/{b['id']}")["version"] == v


def test_invalid_values_are_rejected_not_applied(api, phone):
    b = api.bookmark("https://x.com/a/status/1")
    r = phone.push(set_field(b, "status", "saved", "finished"), set_field(b, "title", "x", "y"))
    assert [x["result"] for x in r] == ["rejected", "rejected"]
    unknown = {**set_field(b, "status", "saved", "learned"), "entity_id": uid()}
    assert phone.push(unknown)[0]["result"] == "rejected"
    assert api.get(f"/bookmarks/{b['id']}")["status"] == "saved"


def test_edit_vs_delete_conflict_and_restore(api, phone):
    b = api.bookmark("https://x.com/a/status/1", status="to_learn")
    api.delete(f"/bookmarks/{b['id']}")
    r = phone.push(set_field(b, "status", "to_learn", "learned"))[0]
    assert r["result"] == "conflict"
    c = api.get("/sync/conflicts")[0]
    assert c["kind"] == "edit_vs_delete"
    api.post(f"/sync/conflicts/{c['id']}/resolve", {"choice": "take_mobile"}, expect=204)
    restored = api.get(f"/bookmarks/{b['id']}")
    assert restored["deleted"] is False and restored["status"] == "learned"
    assert api.get("/sync/conflicts") == []


# ---------- resolution reaches the phone ----------

def test_resolved_conflict_is_dropped_by_phone_on_next_push(api, phone):
    b = api.bookmark("https://x.com/a/status/1", description="laptop note")
    api.patch(f"/bookmarks/{b['id']}", {"description": "laptop edit"}, 1)
    op = set_field(b, "description", "laptop note", "phone edit")
    assert phone.push(op)[0]["result"] == "conflict"
    assert phone.push(op)[0]["result"] == "conflict"  # still waiting for a decision
    c = api.get("/sync/conflicts")[0]
    api.post(f"/sync/conflicts/{c['id']}/resolve", {"choice": "keep_both"}, expect=204)
    assert api.get(f"/bookmarks/{b['id']}")["description"] == "laptop edit\n\nphone edit"
    assert phone.push(op)[0]["result"] == "resolved"
    api.post(f"/sync/conflicts/{c['id']}/resolve", {"choice": "keep_server"}, expect=409)


def test_keep_both_only_for_takeaways(api, phone):
    b = api.bookmark("https://x.com/a/status/1", status="to_learn")
    api.patch(f"/bookmarks/{b['id']}", {"status": "learned"}, 1)
    phone.push(set_field(b, "status", "to_learn", "in_progress"))
    c = api.get("/sync/conflicts")[0]
    api.post(f"/sync/conflicts/{c['id']}/resolve", {"choice": "keep_both"}, expect=422)
    api.post(f"/sync/conflicts/{c['id']}/resolve", {"choice": "keep_server"}, expect=204)
    assert api.get(f"/bookmarks/{b['id']}")["status"] == "learned"


# ---------- links ----------

def test_topic_and_tag_links(api, phone):
    t = api.topic("RAG")
    gone = api.topic("Old")
    b = api.bookmark("https://x.com/a/status/1", tag_names=["llm"])
    tag = api.get("/tags")[0]
    api.delete(f"/topics/{gone['id']}")
    r = phone.push(
        link(b, "add_link", "topics", t["id"]),
        link(b, "add_link", "topics", t["id"]),       # repeat → noop
        link(b, "add_link", "topics", gone["id"]),    # deleted topic → rejected
        link(b, "remove_link", "tags", tag["id"]),
        link(b, "remove_link", "topics", gone["id"]),  # already gone → noop
    )
    assert [x["result"] for x in r] == ["applied", "noop", "rejected", "applied", "noop"]
    got = api.get(f"/bookmarks/{b['id']}")
    assert [x["name"] for x in got["topics"]] == ["RAG"] and got["tags"] == []


# ---------- creations from the phone ----------

def test_create_tag_and_bookmark(api, phone):
    t = api.topic("Evals")
    api.bookmark("https://x.com/a/status/1", tag_names=["LLM"])
    tag_new, tag_dup, bm = uid(), uid(), uid()
    r = phone.push(
        {"op_id": uid(), "entity": "tag", "entity_id": tag_new, "op": "create_tag", "payload": {"id": tag_new, "name": "judge models"}},
        {"op_id": uid(), "entity": "tag", "entity_id": tag_dup, "op": "create_tag", "payload": {"id": tag_dup, "name": "llm"}},
        {"op_id": uid(), "entity": "bookmark", "entity_id": bm, "op": "create_bookmark", "payload": {
            "id": bm, "url": "https://www.linkedin.com/posts/x_evals-activity-7381234567890123456-AbCd?utm_source=share",
            "title": "Cheaper LLM evals", "date_saved": "2026-10-11", "status": "to_learn", "priority": 3,
            "description": "Small judge", "topic_ids": [t["id"]], "tag_ids": [tag_new, tag_dup]}},
    )
    assert [x["result"] for x in r] == ["applied", "merged", "applied"]
    assert "canonical_id" not in r[0] and r[1]["canonical_id"] and "canonical_id" not in r[2]
    got = api.get(f"/bookmarks/{bm}")  # the phone's id is kept
    assert (got["title"], got["status"], got["priority"], got["source_platform"]) == ("Cheaper LLM evals", "to_learn", 3, "linkedin")
    assert [x["name"] for x in got["topics"]] == ["Evals"]
    assert sorted(x["name"] for x in got["tags"]) == ["LLM", "judge models"]
    assert api.get("/bookmarks", params={"q": "judge"})["total"] == 1


def test_new_tag_is_created_before_the_bookmark_that_uses_it(api, phone):
    tag, bm = uid(), uid()
    r = phone.push(  # sent in the "wrong" order, as can happen when both were made in the same millisecond
        {"op_id": uid(), "entity": "bookmark", "entity_id": bm, "op": "create_bookmark",
         "payload": {"id": bm, "url": "https://x.com/a/status/77", "tag_ids": [tag]}},
        {"op_id": uid(), "entity": "tag", "entity_id": tag, "op": "create_tag", "payload": {"id": tag, "name": "fresh"}},
    )
    assert [x["result"] for x in r] == ["applied", "applied"]
    assert [t["name"] for t in api.get(f"/bookmarks/{bm}")["tags"]] == ["fresh"]


def test_same_post_saved_on_both_devices_is_merged(api, phone):
    t1, t2 = api.topic("RAG"), api.topic("Evals")
    mine = api.bookmark("https://x.com/carol/status/201", title="Laptop title", status="learned", topic_ids=[t1["id"]])
    bm = uid()
    r = phone.push({"op_id": uid(), "entity": "bookmark", "entity_id": bm, "op": "create_bookmark", "payload": {
        "id": bm, "url": "https://twitter.com/carol/status/201?s=20", "title": "Phone title", "status": "saved",
        "priority": 1, "description": "Phone takeaway", "topic_ids": [t2["id"]], "tag_ids": []}})[0]
    assert r == {"op_id": r["op_id"], "result": "merged", "canonical_id": mine["id"]}
    got = api.get(f"/bookmarks/{mine['id']}")
    assert (got["title"], got["status"], got["description"]) == ("Laptop title", "learned", "Phone takeaway")
    assert sorted(x["name"] for x in got["topics"]) == ["Evals", "RAG"]
    # A later edit the phone made to its own copy lands on the merged bookmark.
    phone_copy = {"id": bm, "version": 0}
    assert phone.push(set_field(phone_copy, "priority", "1", "3"))[0]["result"] == "conflict"  # laptop has 2, not 1


def test_merge_with_different_takeaways_records_a_conflict(api, phone):
    mine = api.bookmark("https://x.com/carol/status/201", description="Laptop takeaway")
    bm = uid()
    phone.push({"op_id": uid(), "entity": "bookmark", "entity_id": bm, "op": "create_bookmark", "payload": {
        "id": bm, "url": "https://x.com/carol/status/201", "description": "Phone takeaway"}})
    c = api.get("/sync/conflicts")
    assert [(x["kind"], x["server_value"], x["mobile_value"]) for x in c] == [("duplicate_create", "Laptop takeaway", "Phone takeaway")]
    assert api.get(f"/bookmarks/{mine['id']}")["description"] == "Laptop takeaway"


# ---------- pull & ack ----------

def test_pull_pages_include_tombstones_and_links(api, phone):
    g = api.post("/topic-groups", {"name": "AI path"}, expect=201)
    t = api.topic("RAG", group_id=g["id"])
    ids = [api.bookmark(f"https://x.com/a/status/{i}", topic_ids=[t["id"]], tag_names=["rag"])["id"] for i in range(5)]
    api.delete(f"/bookmarks/{ids[0]}")
    pages, cursor = phone.pull_all(limit=3)
    assert len(pages) > 1 and all(len(p["groups"]) + len(p["topics"]) + len(p["tags"]) + len(p["bookmarks"]) <= 3 for p in pages)
    bookmarks = {b["id"]: b for p in pages for b in p["bookmarks"]}
    assert bookmarks[ids[0]]["deleted"] is True
    live = bookmarks[ids[1]]
    assert live["topics"][0]["topic_id"] == t["id"] and len(live["tag_ids"]) == 1 and live["version"] >= 1
    assert cursor == pages[-1]["high_water_seq"]
    # Nothing new → empty page; one change → exactly that change.
    empty = phone.call("GET", "/pull", since=cursor)
    assert empty["bookmarks"] == [] and empty["has_more"] is False and empty["next_seq"] == cursor
    api.patch(f"/bookmarks/{ids[2]}", {"status": "learned"}, 1)
    delta = phone.call("GET", "/pull", since=cursor)
    assert [b["id"] for b in delta["bookmarks"]] == [ids[2]] and delta["bookmarks"][0]["status"] == "learned"

    phone.call("POST", "/ack", {"session_id": phone.session, "acked_seq": delta["next_seq"]}, expect=204)
    assert phone.call("GET", "/status")["pending_for_device"] == 0
    phone.call("POST", f"/sessions/{phone.session}/finish", {"outcome": "success"}, expect=204)
    log = api.get("/sync/log")[0]
    assert log["outcome"] == "success" and log["rows_sent"] > 0 and log["device_name"] == "Pixel 9"


def test_push_counts_in_session_log(api, phone):
    b = api.bookmark("https://x.com/a/status/1")
    phone.push(set_field(b, "status", "saved", "learned"), set_field(b, "status", "x", "y"))
    log = api.get("/sync/log")[0]
    assert (log["ops_received"], log["ops_applied"], log["ops_rejected"]) == (2, 1, 1)


# ---------- adb control (with a fake adb) ----------

def test_usb_tunnel_uses_fixed_adb_commands(client, settings, monkeypatch, tmp_path):
    from learnmarks.services import usb

    fake = tmp_path / "adb"
    fake.write_text("")
    settings.adb_path = str(fake)
    calls = []
    state = {"reverse": False}

    class R:
        def __init__(self, out="", rc=0):
            self.stdout, self.stderr, self.returncode = out, "", rc

    def fake_run(args, **kw):
        calls.append(args[1:])
        if args[1:3] == ["devices", "-l"]:
            return R("List of devices attached\nABC123 device usb:1 product:tokay model:Pixel_9\n")
        if "reverse" in args and "--list" in args:
            return R("UsbFfs tcp:8765 tcp:8000\n" if state["reverse"] else "")
        if "reverse" in args and "--remove" in args:
            state["reverse"] = False
            return R()
        if "reverse" in args:
            state["reverse"] = True
            return R()
        return R()

    monkeypatch.setattr(usb.subprocess, "run", fake_run)
    s = client.get("/api/v1/sync/usb").json()
    assert s["adb_found"] and s["devices"][0]["model"] == "Pixel_9" and s["tunnel_open"] is False
    s = client.post("/api/v1/sync/usb/start").json()
    assert s["tunnel_open"] is True
    assert ["-s", "ABC123", "reverse", "tcp:8765", "tcp:8000"] in calls
    s = client.post("/api/v1/sync/usb/stop").json()
    assert s["tunnel_open"] is False and ["-s", "ABC123", "reverse", "--remove", "tcp:8765"] in calls


def test_usb_start_explains_unauthorized_phone(client, settings, monkeypatch, tmp_path):
    from learnmarks.services import usb

    fake = tmp_path / "adb"
    fake.write_text("")
    settings.adb_path = str(fake)

    class R:
        stdout, stderr, returncode = "List of devices attached\nABC123 unauthorized usb:1\n", "", 0

    monkeypatch.setattr(usb.subprocess, "run", lambda args, **kw: R())
    r = client.post("/api/v1/sync/usb/start")
    assert r.status_code == 409 and "Allow" in r.json()["detail"]
