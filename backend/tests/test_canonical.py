import json
from pathlib import Path

import pytest

from learnmarks.services.canonical import InvalidURL, canonicalize, default_title

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "url-cases.json").read_text())


@pytest.mark.parametrize("case", CASES["valid"], ids=lambda c: c["in"].strip()[:60])
def test_valid(case):
    c = canonicalize(case["in"])
    assert c.canonical_url == case["canonical"]
    assert c.source_platform == case["platform"]
    assert c.author_handle == case["handle"]


@pytest.mark.parametrize("raw", CASES["invalid"])
def test_invalid(raw):
    with pytest.raises(InvalidURL):
        canonicalize(raw)


def test_too_long():
    with pytest.raises(InvalidURL):
        canonicalize("https://example.com/" + "a" * 2100)


def test_default_titles():
    assert default_title(canonicalize("https://x.com/kmeanskaran/status/1")) == "X post by @kmeanskaran"
    assert default_title(canonicalize("https://x.com/i/status/1")) == "X post"
    assert default_title(canonicalize("https://www.linkedin.com/feed/update/urn:li:activity:7245123456789012345")) == "LinkedIn post"
    assert default_title(canonicalize("https://blog.example.com/a")) == "blog.example.com"
