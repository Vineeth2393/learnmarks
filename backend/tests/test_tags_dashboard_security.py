import time

from learnmarks.core.db import get_session
from learnmarks.schemas import BookmarkCreate
from learnmarks.services import bookmarks as bsvc
from learnmarks.services import search


def test_tag_rename_merge_delete(api):
    a = api.bookmark("https://x.com/a/status/1", tag_names=["LLM", "rag"])
    b = api.bookmark("https://x.com/a/status/2", tag_names=["llms"])
    tags = {t["name"]: t for t in api.get("/tags")}
    assert tags["LLM"]["count"] == 1
    assert api.c.patch(f"/api/v1/tags/{tags['llms']['id']}", json={"name": "llm"}).status_code == 409
    merged = api.post(f"/tags/{tags['llms']['id']}/merge", {"into_id": tags["LLM"]["id"]}, expect=200)
    assert merged["count"] == 2
    assert {t["name"] for t in api.get("/tags")} == {"LLM", "rag"}
    api.delete(f"/tags/{tags['rag']['id']}")
    got = api.get(f"/bookmarks/{a['id']}")
    assert [t["name"] for t in got["tags"]] == ["LLM"]
    assert [t["name"] for t in api.get(f"/bookmarks/{b['id']}")["tags"]] == ["LLM"]
    assert api.get("/tags", params={"q": "ll"})[0]["name"] == "LLM"


def test_dashboard(api):
    g = api.post("/topic-groups", {"name": "AI Engineering path"}, expect=201)
    t1 = api.topic("Start here", group_id=g["id"], color="#C9CDBB")
    t2 = api.topic("Inference", group_id=g["id"], color="#A9CCC9")
    api.bookmark("https://x.com/a/status/1", title="Map", topic_ids=[t1["id"]], status="learned")
    for i in range(2, 6):
        api.bookmark(f"https://x.com/a/status/{i}", title=f"Inf {i}", topic_ids=[t2["id"]], status="to_learn")
    kv = api.bookmark("https://x.com/a/status/9", title="KV cache", topic_ids=[t2["id"]], status="to_learn")
    api.patch(f"/bookmarks/{kv['id']}", {"status": "in_progress"}, 1)
    api.bookmark("https://www.linkedin.com/feed/update/urn:li:activity:7245123456789012345", title="Loose")
    api.bookmark("https://x.com/a/status/10", title="Review me", topic_ids=[t1["id"]], tag_names=["needs-review"])

    d = api.get("/dashboard")
    assert d["counts"] == {"saved": 2, "to_learn": 4, "in_progress": 1, "learned": 1, "total": 8}
    assert d["by_source"] == {"x": 7, "linkedin": 1, "other": 0}
    assert d["topic_count"] == 2
    grp = d["groups"][0]
    assert grp["name"] == "AI Engineering path" and grp["bookmark_count"] == 7
    assert [(t["number"], t["name"]) for t in grp["topics"]] == [("01", "Start here"), ("02", "Inference")]
    assert grp["topics"][1]["preview"] == ["Inf 2", "Inf 3", "Inf 4"]
    c = d["continue_item"]
    assert c["bookmark"]["title"] == "KV cache" and c["topic_number"] == "02"
    assert (c["position"], c["topic_total"]) == (5, 5)
    assert d["needs_review"] == 2  # one without a topic, one tagged needs-review
    assert d["recent"][0]["title"] in {"Review me", "Loose"}


def test_host_and_origin_guard(client):
    assert client.get("/api/v1/topics").status_code == 200
    assert client.get("/api/v1/topics", headers={"host": "evil.example:8000"}).status_code == 421
    r = client.post("/api/v1/topics", json={"name": "A"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/v1/topics", json={"name": "A"}, headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    r = client.post("/api/v1/topics", json={"name": "A"}, headers={"origin": "http://127.0.0.1:8000"})
    assert r.status_code == 201
    assert r.headers["content-type"].startswith("application/json")
    bad = client.post("/api/v1/topics", json={})
    assert bad.status_code == 422 and bad.headers["content-type"] == "application/problem+json"


def test_search_is_fast_with_5000_bookmarks(client, api):
    session = next(get_session())
    words = ["rag", "agents", "kv", "cache", "gpu", "python", "system", "design", "eval", "quantization"]
    for i in range(5000):
        bsvc.create(session, BookmarkCreate(url=f"https://x.com/u/status/{10_000 + i}",
                                            title=f"Post {i} about {words[i % 10]} and {words[(i * 7) % 10]}",
                                            description=f"Takeaway {i} {words[(i * 3) % 10]}"))
        if i % 500 == 499:
            session.commit()
    session.commit()
    search.rebuild(session)
    session.commit()
    session.close()

    timings = []
    for q in ["rag", "kv cache", "gpu design", "quant", "post 42", "python eval", "agents"] * 4:
        start = time.perf_counter()
        api.get("/bookmarks", params={"q": q, "limit": 50})
        timings.append(time.perf_counter() - start)
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    assert p95 < 0.2, f"p95 search latency {p95 * 1000:.0f} ms"
    assert api.get("/bookmarks", params={"q": "quantization"})["total"] > 0
