X1 = "https://x.com/_avichawla/status/2093962020962083139"
X2 = "https://x.com/techyoutbe/status/2104104409378762800"
LI = "https://www.linkedin.com/posts/jane_rag-activity-7245123456789012345-AbCd"


def test_create_defaults(api):
    b = api.bookmark(X1)
    assert b["title"] == "X post by @_avichawla"
    assert b["source_platform"] == "x"
    assert b["canonical_url"] == "x:status:2093962020962083139"
    assert b["status"] == "saved" and b["priority"] == 2 and b["version"] == 1
    assert b["topics"] == [] and b["tags"] == []


def test_duplicate_detected_across_url_variants(api):
    first = api.bookmark(X1, title="KV cache, and the 4 caching layers")
    r = api.post("/bookmarks", {"url": "https://twitter.com/_avichawla/status/2093962020962083139?s=20"}, expect=409)
    assert r["existing_id"] == first["id"]
    assert r["existing_title"] == "KV cache, and the 4 caching layers"
    check = api.get("/bookmarks/check-url", params={"url": "mobile.twitter.com/x/status/2093962020962083139"})
    assert check["existing_id"] == first["id"]


def test_check_url_new_and_invalid(api):
    c = api.get("/bookmarks/check-url", params={"url": LI})
    assert c == {"canonical_url": "linkedin:activity:7245123456789012345", "source_platform": "linkedin",
                 "author_handle": None, "suggested_title": "LinkedIn post", "existing_id": None, "existing_title": None}
    r = api.get("/bookmarks/check-url", params={"url": "javascript:alert(1)"}, expect=422)
    assert r["title"] == "Invalid URL"


def test_validation_rejects_unknown_fields_and_bad_values(api):
    api.post("/bookmarks", {"url": X1, "hack": 1}, expect=422)
    api.post("/bookmarks", {"url": X1, "status": "done"}, expect=422)
    api.post("/bookmarks", {"url": X1, "priority": 5}, expect=422)
    api.post("/bookmarks", {"url": X1, "topic_ids": ["11111111-1111-4111-8111-111111111111"]}, expect=422)


def test_update_requires_matching_version(api):
    b = api.bookmark(X1)
    assert api.c.patch(f"/api/v1/bookmarks/{b['id']}", json={"title": "x"}).status_code == 428
    r = api.patch(f"/bookmarks/{b['id']}", {"status": "in_progress", "tag_names": ["kv-cache", "KV-Cache", "article"]}, 1)
    assert r["version"] == 2 and r["status"] == "in_progress"
    assert [t["name"] for t in r["tags"]] == ["article", "kv-cache"]
    stale = api.patch(f"/bookmarks/{b['id']}", {"title": "old"}, 1, expect=412)
    assert stale["current_version"] == 2


def test_noop_update_keeps_version(api):
    b = api.bookmark(X1, title="Same")
    r = api.patch(f"/bookmarks/{b['id']}", {"title": "Same"}, 1)
    assert r["version"] == 1


def test_changing_url_to_existing_one_is_rejected(api):
    a = api.bookmark(X1)
    b = api.bookmark(X2)
    r = api.patch(f"/bookmarks/{b['id']}", {"url": X1}, 1, expect=409)
    assert r["existing_id"] == a["id"]


def test_delete_and_restore(api):
    b = api.bookmark(X1)
    api.delete(f"/bookmarks/{b['id']}")
    assert api.get("/bookmarks")["total"] == 0
    assert api.get(f"/bookmarks/{b['id']}")["deleted"] is True
    # Once deleted, the same URL can be saved again …
    again = api.bookmark(X1)
    # … and restoring the old copy would now be a duplicate.
    r = api.post(f"/bookmarks/{b['id']}/restore", expect=409)
    assert r["existing_id"] == again["id"]
    api.delete(f"/bookmarks/{again['id']}")
    restored = api.post(f"/bookmarks/{b['id']}/restore", expect=200)
    assert restored["deleted"] is False and restored["version"] == 3


def test_filters_and_sorting(api):
    api.bookmark(X1, title="B title", status="learned", priority=3, date_saved="2026-09-01")
    api.bookmark(X2, title="a title", status="to_learn", priority=1, date_saved="2026-09-20")
    api.bookmark(LI, title="C title", status="in_progress", date_saved="2026-08-01")

    def titles(**params):
        return [b["title"] for b in api.get("/bookmarks", params=params)["items"]]

    assert titles() == ["a title", "B title", "C title"]  # newest date_saved first
    assert titles(sort="title") == ["a title", "B title", "C title"]
    assert titles(sort="priority") == ["B title", "C title", "a title"]
    assert titles(sort="status", dir="asc") == ["a title", "C title", "B title"]
    assert titles(source="linkedin") == ["C title"]
    assert titles(status=["learned", "in_progress"]) == ["B title", "C title"]
    assert titles(saved_from="2026-08-15", saved_to="2026-09-10") == ["B title"]
    assert titles(priority=1) == ["a title"]
    page = api.get("/bookmarks", params={"limit": 2, "offset": 2})
    assert page["total"] == 3 and [b["title"] for b in page["items"]] == ["C title"]
    api.get("/bookmarks", params={"sort": "order"}, expect=422)


def test_tag_filter_any_and_all(api):
    a = api.bookmark(X1, tag_names=["rag", "llm"])
    api.bookmark(X2, tag_names=["rag"])
    tags = {t["name"]: t["id"] for t in api.get("/tags")}
    any_ = api.get("/bookmarks", params={"tag": [tags["rag"], tags["llm"]]})
    all_ = api.get("/bookmarks", params={"tag": [tags["rag"], tags["llm"]], "tag_mode": "all"})
    assert any_["total"] == 2
    assert [b["id"] for b in all_["items"]] == [a["id"]]


def test_search_covers_title_description_url_topic_tag(api):
    t = api.topic("Inference, GPUs & the KV cache")
    a = api.bookmark(X1, title="Caching layers", description="Prefill and decode explained",
                     topic_ids=[t["id"]], tag_names=["vLLM"])
    api.bookmark(X2, title="Unrelated thing")

    def found(q):
        return [b["id"] for b in api.get("/bookmarks", params={"q": q})["items"]]

    for q in ("caching", "cach", "PREFILL decode", "_avichawla", "inference gpus", "vllm", "2093962020962083139"):
        assert found(q) == [a["id"]], q
    assert found("caching unrelated") == []
    assert found('"); DROP TABLE bookmarks; --') == []
    # Renaming a topic updates search.
    api.patch(f"/topics/{t['id']}", {"name": "Serving"}, t["version"])
    assert found("serving") == [a["id"]]
    assert found("inference") == []


def test_bulk(api):
    t = api.topic("RAG")
    ids = [api.bookmark(u)["id"] for u in (X1, X2, LI)]
    assert api.post("/bookmarks/bulk", {"ids": ids[:2], "status": "to_learn", "add_topic_id": t["id"], "add_tag": "rag"},
                    expect=200) == {"updated": 2}
    got = {b["id"]: b for b in api.get("/bookmarks")["items"]}
    assert got[ids[0]]["status"] == "to_learn" and got[ids[0]]["topics"][0]["name"] == "RAG"
    assert [x["topics"][0]["position"] for x in (got[ids[0]], got[ids[1]])] == [1, 2]
    assert got[ids[2]]["status"] == "saved"
    api.post("/bookmarks/bulk", {"ids": ids, "delete": True}, expect=200)
    assert api.get("/bookmarks")["total"] == 0


def test_checklist_item_without_link(api):
    b = api.post("/bookmarks", {"title": "Two Sum", "status": "to_learn"}, expect=201)
    assert b["url"] == "" and b["canonical_url"] == "note:two sum" and b["source_platform"] == "other"
    dup = api.post("/bookmarks", {"title": "  two   sum "}, expect=409)
    assert dup["existing_id"] == b["id"]
    api.post("/bookmarks", {"url": ""}, expect=422)  # no link and no title
    # Renaming a checklist item renames its duplicate key too.
    r = api.patch(f"/bookmarks/{b['id']}", {"title": "Two Sum (hash map)"}, 1)
    assert r["canonical_url"] == "note:two sum (hash map)"
    api.post("/bookmarks", {"title": "Two Sum"}, expect=201)  # the old name is free again
    # Adding a link later turns it into a normal bookmark.
    r = api.patch(f"/bookmarks/{b['id']}", {"url": "https://leetcode.com/problems/two-sum/"}, r["version"])
    assert r["canonical_url"] == "url:leetcode.com/problems/two-sum"
