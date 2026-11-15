"""URL policy shared by artifact validation and the collector's fetcher."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote, urlsplit, urlunsplit

ACADEMY_HOST = "www.skills.google"
ACADEMY_ORIGIN = f"https://{ACADEMY_HOST}"
CATALOG_URL = f"{ACADEMY_ORIGIN}/catalog"

# Path prefix of each public resource page and the resource kind it holds.
RESOURCE_SECTIONS = {
    "paths": "learning-path",
    "course_templates": "course",
    "focuses": "lab",
}

# Mirrors robots.txt plus private account routes. The collector also parses the live robots.txt
# before every run; this static copy keeps excluded paths out of artifacts when validated offline.
EXCLUDED_PREFIXES = (
    "/api/",
    "/users/",
    "/my_account/",
    "/profile/",
    "/admin/",
    "/suadmin/",
    "/classrooms/",
    "/games/",
    "/labs/",
)
EXCLUDED_FOCUS_ACTION = re.compile(r"^/focuses/[^/]+/(?:start|resume|stop)(?:/|$)")

DIGITS = r"\d+"
RESOURCE_PATH = re.compile(rf"/({'|'.join(map(re.escape, RESOURCE_SECTIONS))})/({DIGITS})")
# Steps inside a course: readings, quizzes, labs, videos and interactive lesson bundles.
# They are linked, never fetched.
UNIT_PATH = re.compile(
    rf"/course_templates/({DIGITS})/(documents|quizzes|labs|video|html_bundles)/({DIGITS})"
)
CATALOG_QUERY = re.compile(r"page=[1-9]\d*")


def checked_https_url(value: str, hosts: frozenset[str]) -> str:
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("Invalid URL")
    if any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("URL contains unsafe characters")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parts.scheme != "https" or parts.hostname not in hosts:
        raise ValueError("URL host is not allowed")
    if parts.username is not None or parts.password is not None or port not in (None, 443):
        raise ValueError("URL credentials and nonstandard ports are not allowed")
    # Repeated decoding catches encoded traversal and delimiter smuggling.
    decoded = parts.path
    for _ in range(3):
        decoded = unquote(decoded)
    if "\\" in decoded or "//" in decoded or any(x in (".", "..") for x in decoded.split("/")):
        raise ValueError("Unsafe URL path")
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        raise ValueError("Unsafe URL path")
    return urlunsplit(("https", parts.hostname, parts.path or "/", parts.query, ""))


def _academy_path(value: str) -> str:
    """Return the canonical path of a Google Skills URL; fragments are dropped."""
    url = checked_https_url(value, frozenset({ACADEMY_HOST}))
    path = urlsplit(url).path
    if path != "/":
        path = path.rstrip("/")
    if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        raise ValueError("Path is excluded by the Google Skills robots policy")
    if EXCLUDED_FOCUS_ACTION.match(path):
        raise ValueError("Focus action path is excluded by the Google Skills robots policy")
    return path


def resource_url(value: str) -> str:
    """Canonical URL of one public learning path, course or lab page."""
    path = _academy_path(value)
    match = RESOURCE_PATH.fullmatch(path)
    if not match:
        raise ValueError("Google Skills path is not a public resource page")
    if match.group(1) == "focuses":
        return f"{ACADEMY_ORIGIN}{path}?parent=catalog"
    return ACADEMY_ORIGIN + path


def official_url(value: str) -> str:
    """A resource page or a unit page of a course. Lab and unit pages are linked, never fetched."""
    path = _academy_path(value)
    if RESOURCE_PATH.fullmatch(path):
        return resource_url(value)
    if UNIT_PATH.fullmatch(path):
        return ACADEMY_ORIGIN + path
    raise ValueError("Google Skills path is outside public learning resources")


def artwork_url(value: str, resource: str | None = None) -> str:
    """Google Skills does not publish per-page share images."""
    checked_https_url(value, frozenset({ACADEMY_HOST}))
    raise ValueError("Google Skills does not publish per-page share images")


def source_url(value: str) -> str:
    """Canonical provenance or discovery URL allowed for Google Skills."""
    url = checked_https_url(value, frozenset({ACADEMY_HOST}))
    parts = urlsplit(url)
    path = _academy_path(value)
    if path == "/robots.txt":
        if parts.query:
            raise ValueError("robots.txt URL must not have a query")
        return ACADEMY_ORIGIN + path
    if path == "/catalog":
        if not parts.query:
            return ACADEMY_ORIGIN + path
        if CATALOG_QUERY.fullmatch(parts.query):
            return f"{ACADEMY_ORIGIN}{path}?{parts.query}"
        raise ValueError("Catalog discovery URL may only use a page=<digits> query")
    return official_url(value)


def fetchable_url(value: str) -> str:
    """Return canonical URL for fetchable targets (robots, catalog, paths, courses)."""
    canonical = source_url(value)
    path = urlsplit(canonical).path
    if path.startswith("/focuses/") or UNIT_PATH.fullmatch(path):
        raise ValueError("Lab and unit pages are never fetched")
    return canonical


def resource_kind(url: str) -> str:
    match = RESOURCE_PATH.fullmatch(urlsplit(resource_url(url)).path)
    assert match is not None
    return RESOURCE_SECTIONS[match.group(1)]


def resource_slug(url: str) -> str:
    match = RESOURCE_PATH.fullmatch(urlsplit(resource_url(url)).path)
    assert match is not None
    return match.group(2)


def stable_id(url: str) -> str:
    canonical = resource_url(url)
    return "ga_" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
