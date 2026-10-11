def urls(n):
    return [f"https://x.com/u/status/{1000 + i}" for i in range(n)]


def order(api, topic_id):
    items = api.get("/bookmarks", params={"topic": topic_id, "sort": "order", "limit": 100})["items"]
    return [b["title"] for b in items]


def make_topic_with(api, n, name="RAG"):
    t = api.topic(name, color="#efd98a")
    for i, u in enumerate(urls(n)):
        api.bookmark(u, title=f"b{i + 1}", topic_ids=[t["id"]])
    return t


def test_topic_crud_and_counts(api):
    t = api.topic("RAG", color="#efd98a", level="intermediate", description="Retrieval")
    assert t["color"] == "#EFD98A" and t["counts"]["total"] == 0
    api.post("/topics", {"name": "rag"}, expect=409)  # case-insensitive unique
    api.post("/topics", {"name": "Bad", "color": "red"}, expect=422)
    api.bookmark(urls(1)[0], topic_ids=[t["id"]], status="learned")
    got = api.get(f"/topics/{t['id']}")
    assert got["counts"]["learned"] == 1 and got["counts"]["total"] == 1
    renamed = api.patch(f"/topics/{t['id']}", {"name": "Retrieval-augmented generation"}, t["version"])
    assert renamed["version"] == 2


def test_new_bookmarks_append_in_learning_order(api):
    t = make_topic_with(api, 3)
    assert order(api, t["id"]) == ["b1", "b2", "b3"]
    detail = api.get("/bookmarks", params={"topic": t["id"], "sort": "order"})["items"]
    assert [b["topics"][0]["position"] for b in detail] == [1, 2, 3]


def test_move_and_set_order(api):
    t = make_topic_with(api, 4)
    ids = {b["title"]: b["id"] for b in api.get("/bookmarks", params={"topic": t["id"]})["items"]}
    api.post(f"/topics/{t['id']}/move", {"bookmark_id": ids["b4"], "before_id": ids["b1"]}, expect=204)
    assert order(api, t["id"]) == ["b4", "b1", "b2", "b3"]
    api.post(f"/topics/{t['id']}/move", {"bookmark_id": ids["b4"]}, expect=204)  # to the end
    assert order(api, t["id"]) == ["b1", "b2", "b3", "b4"]
    api.put(f"/topics/{t['id']}/order", {"bookmark_ids": [ids[k] for k in ("b3", "b1", "b4", "b2")]})
    assert order(api, t["id"]) == ["b3", "b1", "b4", "b2"]
    # A stale full order (missing an item) is refused rather than silently applied.
    api.put(f"/topics/{t['id']}/order", {"bookmark_ids": [ids["b1"]]}, expect=409)


def test_move_bumps_only_the_moved_bookmark(api):
    t = make_topic_with(api, 3)
    before = {b["title"]: b for b in api.get("/bookmarks", params={"topic": t["id"]})["items"]}
    api.post(f"/topics/{t['id']}/move", {"bookmark_id": before["b3"]["id"], "before_id": before["b2"]["id"]}, expect=204)
    after = {b["title"]: b for b in api.get("/bookmarks", params={"topic": t["id"]})["items"]}
    assert after["b3"]["version"] == before["b3"]["version"] + 1
    assert after["b1"]["version"] == before["b1"]["version"]
    assert after["b2"]["version"] == before["b2"]["version"]


def test_repeated_moves_eventually_renumber(api):
    t = make_topic_with(api, 3)
    ids = {b["title"]: b["id"] for b in api.get("/bookmarks", params={"topic": t["id"]})["items"]}
    # Keep squeezing items between b1 and b2 until gaps run out; order must stay correct throughout.
    for i in range(60):
        mover = "b3" if i % 2 == 0 else "b2"
        target = "b2" if mover == "b3" else "b3"
        api.post(f"/topics/{t['id']}/move", {"bookmark_id": ids[mover], "before_id": ids[target]}, expect=204)
        expected = ["b1", mover, target]
        assert order(api, t["id"]) == expected


def test_delete_topic_keeps_bookmarks(api):
    t = make_topic_with(api, 2)
    api.delete(f"/topics/{t['id']}")
    items = api.get("/bookmarks")["items"]
    assert len(items) == 2 and all(b["topics"] == [] for b in items)
    assert all(b["version"] == 2 for b in items)  # association change bumps the bookmark
    api.get(f"/topics/{t['id']}", expect=404)
    assert api.get("/bookmarks", params={"no_topic": True})["total"] == 2
    api.topic("RAG")  # the name is free again


def test_groups(api):
    g = api.post("/topic-groups", {"name": "AI Engineering path"}, expect=201)
    t = api.topic("RAG", group_id=g["id"])
    assert t["group_id"] == g["id"]
    api.post("/topics", {"name": "X", "group_id": "11111111-1111-4111-8111-111111111111"}, expect=422)
    api.delete(f"/topic-groups/{g['id']}")
    assert api.get(f"/topics/{t['id']}")["group_id"] is None
    assert api.get("/topic-groups") == []
