from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from learnmarks.core.config import Settings
from learnmarks.main import create_app

BASE = "http://127.0.0.1:8000"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, web_dist=tmp_path / "no-web", auto_backup=False)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), base_url=BASE)


@pytest.fixture
def api(client: TestClient):
    """Small helper: api.post('/topics', {...}) -> parsed JSON, asserting the expected status."""

    class Api:
        def __init__(self, c: TestClient):
            self.c = c

        def _call(self, method, path, json=None, expect=None, headers=None, params=None):
            r = self.c.request(method, f"/api/v1{path}", json=json, headers=headers, params=params)
            if expect is not None:
                assert r.status_code == expect, r.text
            return r.json() if r.content else None

        def get(self, path, expect=200, **kw):
            return self._call("GET", path, expect=expect, **kw)

        def post(self, path, json=None, expect=None, **kw):
            return self._call("POST", path, json=json, expect=expect, **kw)

        def patch(self, path, json, version, expect=200):
            return self._call("PATCH", path, json=json, expect=expect, headers={"If-Match": str(version)})

        def put(self, path, json, expect=204):
            return self._call("PUT", path, json=json, expect=expect)

        def delete(self, path, expect=204):
            return self._call("DELETE", path, expect=expect)

        def bookmark(self, url, **fields):
            return self.post("/bookmarks", {"url": url, **fields}, expect=201)

        def topic(self, name, **fields):
            return self.post("/topics", {"name": name, **fields}, expect=201)

    return Api(client)
