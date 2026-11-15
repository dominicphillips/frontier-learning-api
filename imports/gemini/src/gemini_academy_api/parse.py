"""Deterministic metadata extraction from public Google Skills page HTML.

Only catalog metadata is read: listing cards inside <ql-search-result-container>, the page title,
its published description, header facts (duration and level), course outline modules/activities and
a learning path's member cards. Course bodies, lesson text, media and images are never extracted.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from .html import Node, parse_html
from .security import (
    ACADEMY_ORIGIN,
    UNIT_PATH,
    official_url,
    resource_kind,
    resource_slug,
    resource_url,
)

SITE_SUFFIX = re.compile(r"\s*[·|–-]\s*Google Skills\s*$", re.IGNORECASE)
PRIVATE_USE = re.compile(r"[\ue000-\uf8ff]")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
DURATION = re.compile(
    r"(?:(?P<days>\d+(?:\.\d+)?)\s*(?:d|day|days))?\s*"
    r"(?:(?P<hours>\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours))?\s*"
    r"(?:(?P<minutes>\d+)\s*(?:m|min|mins|minute|minutes))?",
    re.IGNORECASE,
)
ISO_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?")
PATH_COURSE_RE = re.compile(r"^/paths/\d+(/course_templates/\d+)$")
UPDATED_RE = re.compile(r"^updated\b", re.IGNORECASE)
LEVELS = {
    "introductory": "beginner",
    "intermediate": "intermediate",
    "advanced": "advanced",
}
LISTING_KINDS = {
    "course": "course",
    "lab": "lab",
    "learning_path": "learning-path",
}
UNIT_KINDS = {
    "link": "lesson",
    "quiz": "quiz",
    "lab": "lab",
}
MAX_TEXT = 300
MAX_SHORT_TEXT = 500
MAX_SUMMARY = 1200


@dataclass
class ListingEntry:
    url: str
    kind: str
    title: str
    description: str | None = None
    summary: str | None = None
    minutes: int | None = None
    level: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ListingPage:
    entries: list[ListingEntry]
    results_count: int
    items_per_page: int | None = None
    path: str | None = None
    # Results on the page that are not a known resource (a new type or URL shape). They are left
    # out rather than guessed; the collector's distinct-entry check still bounds how many may go.
    unrecognised: int = 0


@dataclass
class PathMember:
    url: str
    kind: str
    title: str
    minutes: int | None = None


@dataclass
class PageMetadata:
    url: str
    kind: str
    title: str
    summary: str | None = None
    minutes: int | None = None
    level: str | None = None
    tags: list[str] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    member_cards: list[PathMember] = field(default_factory=list)
    artwork: dict | None = None
    warnings: list[str] = field(default_factory=list)
    summary_overlong: bool = False


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = PRIVATE_USE.sub(" ", value)
    text = CONTROL_CHARS.sub(" ", text)
    text = " ".join(text.split())
    return text or None


def clean_html(value: str | None) -> str | None:
    if value is None:
        return None
    unescaped = html.unescape(value)
    text = parse_html(unescaped).text()
    return clean(text)


def parse_minutes(value: str | None) -> int | None:
    text = clean(value)
    if not text:
        return None
    match = DURATION.fullmatch(text)
    if not match or not (match["days"] or match["hours"] or match["minutes"]):
        return None
    total = (
        round(float(match["days"] or 0) * 1440)
        + round(float(match["hours"] or 0) * 60)
        + int(match["minutes"] or 0)
    )
    if total < 0 or total > 10000:
        return None
    return total


def parse_iso_minutes(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = ISO_DURATION.fullmatch(value.strip())
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = match.groups()
    total = int(days or 0) * 1440 + int(hours or 0) * 60 + int(minutes or 0)
    total += round(float(seconds or 0) / 60)
    return total if 0 <= total <= 10000 else None


def parse_level(value: str | None) -> str | None:
    text = clean(value)
    if not text:
        return None
    return LEVELS.get(text.casefold())


def parse_credential_tags(value: str | None) -> list[str]:
    text = clean(value)
    if not text:
        return []
    words = " ".join(text.replace("_", " ").replace("-", " ").split()).lower()
    if not words:
        return []
    return [(words[0].upper() + words[1:])[:MAX_TEXT]]


def path_category_id(title: str, url: str) -> str:
    num = resource_slug(url)
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    suffix = f"-{num}"
    max_slug = 100 - len(suffix)
    slug = slug[:max_slug].rstrip("-") or "path"
    return f"{slug}{suffix}"


def _meta(doc: Node, key: str) -> str | None:
    for node in doc.find_all("meta"):
        if node.attrs.get("property") == key or node.attrs.get("name") == key:
            return clean(node.attrs.get("content"))
    return None


def _meta_raw(doc: Node, key: str) -> str | None:
    for node in doc.find_all("meta"):
        if node.attrs.get("property") == key or node.attrs.get("name") == key:
            return node.attrs.get("content")
    return None


def _same_page(value: object, url: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return resource_url(urljoin(url, value)) == url
    except ValueError:
        return False


def _top_title_h1(doc: Node) -> str | None:
    for node in doc.iter():
        if "top-title" in node.attrs.get("class", "").split():
            h1 = node.find("h1")
            if h1 and (text := clean(h1.text())):
                return text
    return None


def _first_h1(doc: Node) -> str | None:
    main = doc.find("main")
    scope = main or doc
    h1 = scope.find("h1")
    return clean(h1.text()) if h1 else None


def _normalize_member_path(raw_path: str) -> str:
    path_only = raw_path.split("?", 1)[0].split("#", 1)[0]
    match = PATH_COURSE_RE.fullmatch(path_only)
    if match:
        return match.group(1)
    return raw_path


def parse_listing_page(text: str) -> ListingPage:
    doc = parse_html(text)
    container = doc.find("ql-search-result-container")
    if container is None:
        raise ValueError("Listing page missing ql-search-result-container")
    raw_attr = container.attrs.get("pagedsearchresults")
    if not raw_attr:
        raise ValueError("Listing container missing pagedSearchResults attribute")
    try:
        payload = json.loads(raw_attr)
    except ValueError as exc:
        raise ValueError("Malformed pagedSearchResults JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("pagedSearchResults must be a JSON object")

    raw_results = payload.get("searchResults")
    results_count = payload.get("resultsCount")
    if not isinstance(raw_results, list) or not isinstance(results_count, int) or results_count < 0:
        raise ValueError("pagedSearchResults missing valid searchResults or resultsCount")

    entries: list[ListingEntry] = []
    unrecognised = 0
    for item in raw_results:
        if not isinstance(item, dict):
            raise ValueError("Listing entry must be an object")
        raw_path = item.get("path")
        raw_type = item.get("type")
        if not isinstance(raw_path, str) or raw_type not in LISTING_KINDS:
            unrecognised += 1
            continue
        try:
            url = resource_url(urljoin(ACADEMY_ORIGIN, raw_path))
        except ValueError:
            unrecognised += 1
            continue
        kind = resource_kind(url)
        title = clean(item.get("title") if isinstance(item.get("title"), str) else None)
        if LISTING_KINDS[raw_type] != kind or not title:
            unrecognised += 1
            continue
        raw_desc = item.get("description") if isinstance(item.get("description"), str) else None
        description = clean_html(raw_desc)
        summary = description if description and len(description) <= MAX_SUMMARY else None
        raw_duration = item.get("duration")
        minutes = parse_minutes(raw_duration if isinstance(raw_duration, str) else None)
        level = parse_level(item.get("level") if isinstance(item.get("level"), str) else None)
        cred = item.get("credentialType") if isinstance(item.get("credentialType"), str) else None
        entries.append(
            ListingEntry(
                url=url,
                kind=kind,
                title=title[:MAX_TEXT],
                description=description,
                summary=summary,
                minutes=minutes,
                level=level,
                tags=parse_credential_tags(cred),
            )
        )

    items_per_page = payload.get("itemsPerPage")
    path = payload.get("path")
    return ListingPage(
        entries=entries,
        results_count=results_count,
        items_per_page=items_per_page if isinstance(items_per_page, int) else None,
        path=path if isinstance(path, str) else None,
        unrecognised=unrecognised,
    )


def _course_facts(doc: Node, page: PageMetadata) -> None:
    for span in doc.find_all("span"):
        classes = span.attrs.get("class", "").split()
        if "course-detail" not in classes:
            continue
        text = clean(span.text())
        if not text or UPDATED_RE.match(text):
            continue
        if page.minutes is None and (minutes := parse_minutes(text)) is not None:
            page.minutes = minutes
        elif page.level is None and (level := parse_level(text)) is not None:
            page.level = level


def _course_outline(doc: Node, url: str, page: PageMetadata) -> list[dict]:
    menu = doc.find("ql-contents-menu")
    if menu is None:
        return []
    raw_modules = menu.attrs.get("modules")
    if not raw_modules:
        return []
    try:
        modules = json.loads(raw_modules)
    except ValueError as exc:
        raise ValueError("Malformed ql-contents-menu modules JSON") from exc
    if not isinstance(modules, list):
        raise ValueError("ql-contents-menu modules must be a list")

    course_id = resource_slug(url)
    sections: list[dict] = []
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        mod_title = clean(mod.get("title") if isinstance(mod.get("title"), str) else None)
        raw_mod_desc = mod.get("description")
        mod_desc = clean_html(raw_mod_desc if isinstance(raw_mod_desc, str) else None)
        context = mod_desc[:MAX_SHORT_TEXT].rstrip() or None if mod_desc else None
        units: list[dict] = []
        steps = mod.get("steps") or []
        if not isinstance(steps, list):
            steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            activities = step.get("activities") or []
            if not isinstance(activities, list):
                continue
            for act in activities:
                if not isinstance(act, dict):
                    continue
                act_type = act.get("type")
                if act_type == "credential":
                    cred = act.get("credentialType")
                    if isinstance(cred, str):
                        page.tags = list(dict.fromkeys([*page.tags, *parse_credential_tags(cred)]))
                    continue
                href = act.get("href")
                if not isinstance(href, str) or not href.strip():
                    continue
                abs_href = urljoin(ACADEMY_ORIGIN, href.strip())
                try:
                    unit_url = official_url(abs_href)
                except ValueError:
                    page.warnings.append(f"Skipped outline link outside the course: {abs_href}")
                    continue
                match = UNIT_PATH.fullmatch(unit_url.removeprefix(ACADEMY_ORIGIN))
                if not match or match.group(1) != course_id:
                    page.warnings.append(f"Skipped outline link outside the course: {abs_href}")
                    continue
                unit_title = clean(act.get("title") if isinstance(act.get("title"), str) else None)
                if not unit_title:
                    continue
                kind = UNIT_KINDS.get(act_type, "lesson")
                units.append(
                    {
                        "title": unit_title[:MAX_TEXT],
                        "url": unit_url,
                        "kind": kind,
                        "context": None,
                        "videoCount": None,
                    }
                )
        if units:
            sections.append(
                {
                    "title": mod_title[:MAX_TEXT] if mod_title else None,
                    "context": context,
                    "units": units,
                }
            )
    return sections


def _path_members(doc: Node, page: PageMetadata) -> tuple[list[PathMember], list[dict]]:
    seen: dict[str, PathMember] = {}
    for card in doc.find_all("ql-activity-card"):
        raw_path = card.attrs.get("path", "")
        if not raw_path:
            continue
        normalized = _normalize_member_path(raw_path)
        target = urljoin(ACADEMY_ORIGIN, normalized)
        try:
            member_url = resource_url(target)
        except ValueError:
            page.warnings.append(f"Skipped non-resource path card: {raw_path}")
            continue
        member_kind = resource_kind(member_url)
        if member_kind not in {"course", "lab"}:
            page.warnings.append(f"Skipped unexpected member kind {member_kind!r}: {member_url}")
            continue
        card_type = card.attrs.get("type", "").strip()
        if card_type and card_type != member_kind:
            page.warnings.append(f"Path card type {card_type!r} differed from URL {member_url}")
        title = clean(card.attrs.get("name"))
        if not title:
            continue
        minutes = parse_minutes(card.attrs.get("duration"))
        seen.setdefault(
            member_url,
            PathMember(url=member_url, kind=member_kind, title=title[:MAX_TEXT], minutes=minutes),
        )
    cards = list(seen.values())
    sections = (
        [
            {
                "title": None,
                "context": None,
                "units": [
                    {
                        "title": m.title,
                        "url": m.url,
                        "kind": m.kind,
                        "context": None,
                        "videoCount": None,
                    }
                    for m in cards
                ],
            }
        ]
        if cards
        else []
    )
    return cards, sections


def parse_page(url: str, text: str) -> PageMetadata:
    url = resource_url(url)
    kind = resource_kind(url)
    if kind == "lab":
        raise ValueError("Lab pages are never parsed")

    doc = parse_html(text)
    og_title = _meta(doc, "og:title")
    og_clean = clean(SITE_SUFFIX.sub("", og_title)) if og_title else None
    top_h1 = _top_title_h1(doc)
    first_h1 = _first_h1(doc)
    doc_title = clean(SITE_SUFFIX.sub("", node.raw_text())) if (node := doc.find("title")) else None

    if kind == "course":
        title = top_h1 or og_clean or first_h1 or doc_title
    else:
        title = og_clean or top_h1 or first_h1 or doc_title
    if not title:
        raise ValueError("Page has no title")

    page = PageMetadata(url=url, kind=kind, title=title[:MAX_TEXT])

    canonical = next(
        (n.attrs.get("href") for n in doc.find_all("link") if n.attrs.get("rel") == "canonical"),
        None,
    ) or _meta(doc, "og:url")
    if canonical and not _same_page(canonical, url):
        page.warnings.append(f"Canonical URL differs from the requested page: {canonical}")

    raw_desc = _meta_raw(doc, "description") or _meta_raw(doc, "og:description")
    summary = clean_html(raw_desc)
    if summary and len(summary) > MAX_SUMMARY:
        page.warnings.append("Summary longer than 1200 characters was left out")
        summary = None
        page.summary_overlong = True
    page.summary = summary
    page.artwork = None

    if kind == "course":
        _course_facts(doc, page)
        page.sections = _course_outline(doc, url, page)
    elif kind == "learning-path":
        page.member_cards, page.sections = _path_members(doc, page)
        page.members = [m.url for m in page.member_cards]
    return page
