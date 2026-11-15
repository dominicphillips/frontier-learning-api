"""URL policy shared by artifact validation and the collector's fetcher."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote, urlsplit, urlunsplit

ACADEMY_HOST = "academy.claude.com"
ACADEMY_ORIGIN = f"https://{ACADEMY_HOST}"
# Path prefix of each public resource page and the resource kind it holds.
RESOURCE_SECTIONS = {
    "courses": "course",
    "collections": "collection",
    "tutorials": "tutorial",
    "use-cases": "use-case",
}
# Mirrors the published robots.txt. The collector also parses the live file before every run;
# this static copy keeps excluded paths out of artifacts even when they are validated offline.
EXCLUDED_PREFIXES = (
    "/api/",
    "/mcp",
    "/search-corpus.json",
    "/search-corpus.manifest.json",
    "/admin/",
    "/badges/",
    "/certificates/",
    "/dashboard",
    "/settings",
    "/garden",
    "/login",
    "/oauth/",
    "/start",
    "/welcome",
    "/goodbye",
    "/plan",
    "/fluency-check-in",
    "/labs",
    "/embed/",
)
DISCOVERY_PATHS = frozenset({"/robots.txt", "/sitemap.xml"})
SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
RESOURCE_PATH = re.compile(rf"/({'|'.join(map(re.escape, RESOURCE_SECTIONS))})/({SLUG})")
UNIT_PATH = re.compile(rf"/courses/({SLUG})/({SLUG})")
# Per-page share images. They are hotlinked as artwork, never downloaded or re-hosted.
ARTWORK_PATH = re.compile(
    rf"/og/({'|'.join(map(re.escape, RESOURCE_SECTIONS))})/({SLUG})\.(?:png|jpg|jpeg|webp)"
)


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
    """Return the canonical path of an Academy URL; query strings and fragments are dropped."""
    url = checked_https_url(value, frozenset({ACADEMY_HOST}))
    path = urlsplit(url).path
    if path != "/":
        path = path.rstrip("/")
    if any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        raise ValueError("Path is excluded by the Academy robots policy")
    return path


def resource_url(value: str) -> str:
    """Canonical URL of one public course, collection, tutorial or use-case page."""
    path = _academy_path(value)
    if not RESOURCE_PATH.fullmatch(path):
        raise ValueError("Academy path is not a public resource page")
    return ACADEMY_ORIGIN + path


def official_url(value: str) -> str:
    """A resource page or a lesson page of a course. Lesson pages are linked, never fetched."""
    path = _academy_path(value)
    if not (RESOURCE_PATH.fullmatch(path) or UNIT_PATH.fullmatch(path)):
        raise ValueError("Academy path is outside public learning resources")
    return ACADEMY_ORIGIN + path


def artwork_url(value: str, resource: str | None = None) -> str:
    """The official share image of one resource page; with `resource`, it must be that page's."""
    url = checked_https_url(value, frozenset({ACADEMY_HOST}))
    parts = urlsplit(url)
    match = ARTWORK_PATH.fullmatch(parts.path)
    if parts.query or not match:
        raise ValueError("Artwork must be a per-page Academy share image")
    if resource is not None:
        page = RESOURCE_PATH.fullmatch(urlsplit(resource_url(resource)).path)
        if page is None or page.groups() != match.groups():
            raise ValueError("Artwork belongs to a different page")
    return ACADEMY_ORIGIN + parts.path


def source_url(value: str) -> str:
    path = _academy_path(value)
    if path in DISCOVERY_PATHS:
        return ACADEMY_ORIGIN + path
    return official_url(value)


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
    return "ca_" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
