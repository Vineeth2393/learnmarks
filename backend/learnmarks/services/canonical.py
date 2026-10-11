"""URL canonicalisation for duplicate detection (DESIGN §4.1).

The same rules are implemented in Kotlin on the phone; both are tested against
shared/url-cases.json so they never disagree.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

MAX_URL_LENGTH = 2048

X_HOSTS = {"x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com"}
LINKEDIN_HOSTS = {"linkedin.com"}
TRACKING_PARAMS = {"s", "t", "ref", "ref_src", "ref_url", "si", "fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}

_X_STATUS = re.compile(r"^/(?:(?P<handle>[A-Za-z0-9_]{1,15})|i(?:/web)?)/status(?:es)?/(?P<id>\d{1,25})(?:/|$)")
_LI_URN = re.compile(r"urn:li:(?P<kind>activity|share|ugcPost):(?P<id>\d{6,25})")
_LI_POST_SLUG = re.compile(r"-(?P<kind>activity|share|ugcPost)-(?P<id>\d{6,25})-")
_RESERVED_X_PATHS = {"i", "home", "search", "explore", "settings", "messages", "notifications"}


class InvalidURL(ValueError):
    pass


@dataclass(frozen=True)
class Canonical:
    canonical_url: str
    source_platform: str  # x | linkedin | other
    author_handle: str | None
    clean_url: str  # the URL as stored: trimmed, scheme/host lower-cased


def _strip_host(host: str) -> str:
    host = host.lower().rstrip(".")
    for prefix in ("www.", "mobile.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def canonicalize(raw: str) -> Canonical:
    url = (raw or "").strip()
    if not url:
        raise InvalidURL("URL is empty")
    if len(url) > MAX_URL_LENGTH:
        raise InvalidURL(f"URL is longer than {MAX_URL_LENGTH} characters")
    if "://" not in url and re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", url, re.I):
        url = "https://" + url  # pasted without a scheme, e.g. "x.com/user/status/1"

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidURL("Only http and https links can be saved")
    if not parts.hostname:
        raise InvalidURL("URL has no host")
    if any(ch.isspace() for ch in url):
        raise InvalidURL("URL contains spaces")

    host = _strip_host(parts.hostname)
    netloc = parts.hostname.lower() + (f":{parts.port}" if parts.port else "")
    clean_url = f"{scheme}://{netloc}{parts.path or '/'}" + (f"?{parts.query}" if parts.query else "")
    if parts.fragment:
        clean_url += f"#{parts.fragment}"

    if host in X_HOSTS:
        m = _X_STATUS.match(parts.path)
        if m:
            handle = m.group("handle")
            if handle and handle.lower() in _RESERVED_X_PATHS:
                handle = None
            return Canonical(f"x:status:{m.group('id')}", "x", handle, clean_url)
        return Canonical(_generic(host, parts.path, parts.query), "x", None, clean_url)

    if host in LINKEDIN_HOSTS or host.endswith(".linkedin.com"):
        path = unquote(parts.path)
        m = _LI_URN.search(path) or _LI_POST_SLUG.search(path)
        if m:
            kind = "activity" if m.group("kind") == "activity" else m.group("kind").lower()
            return Canonical(f"linkedin:{kind}:{m.group('id')}", "linkedin", None, clean_url)
        return Canonical(_generic("linkedin.com", parts.path, parts.query), "linkedin", None, clean_url)

    return Canonical(_generic(host, parts.path, parts.query), "other", None, clean_url)


def _generic(host: str, path: str, query: str) -> str:
    path = re.sub(r"/{2,}", "/", path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    params = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    params.sort()
    q = urlencode(params)
    return f"url:{host}{path}" + (f"?{q}" if q else "")


def note_key(title: str) -> str:
    """Duplicate key for a checklist item that has no link: its title, ignoring case and spacing."""
    return "note:" + " ".join(title.lower().split())


def for_item(url: str | None, title: str | None) -> Canonical:
    """A link is canonicalised as usual; an item without a link is identified by its title."""
    if url and url.strip():
        return canonicalize(url)
    t = " ".join((title or "").split())
    if not t:
        raise InvalidURL("Give a link, or a title for a checklist item without one")
    return Canonical(note_key(t), "other", None, "")


def default_title(c: Canonical) -> str:
    if c.source_platform == "x":
        return f"X post by @{c.author_handle}" if c.author_handle else "X post"
    if c.source_platform == "linkedin":
        return "LinkedIn post"
    return urlsplit(c.clean_url).hostname or "Link"
