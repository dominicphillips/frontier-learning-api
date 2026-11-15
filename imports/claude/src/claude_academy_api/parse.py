"""Deterministic metadata extraction from public Claude Academy page HTML.

Only catalog metadata is read: the page title, its published description, the header chips
(duration, lesson and quiz counts, product and role labels), the course outline titles and a
collection's member links. Course bodies, lesson text, media and images are never extracted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from .html import Node, parse_html
from .security import (
    ACADEMY_ORIGIN,
    UNIT_PATH,
    artwork_url,
    official_url,
    resource_kind,
    resource_slug,
    resource_url,
)

SITE_SUFFIX = re.compile(r"\s*[·|–-]\s*Claude Academy\s*$")
PRIVATE_USE = re.compile(r"[-]")
DURATION = re.compile(
    r"(?:(?P<hours>\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours))?\s*"
    r"(?:(?P<minutes>\d+)\s*(?:m|min|mins|minute|minutes))?",
    re.IGNORECASE,
)
ISO_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?")
LESSONS = re.compile(r"(\d+)\s+lessons?", re.IGNORECASE)
QUIZZES = re.compile(r"(\d+)\s+quiz(?:zes)?", re.IGNORECASE)
IGNORED_CHIPS = frozenset({"completion badge", "no completion badge"})
MAX_TEXT = 300


@dataclass
class PageMetadata:
    url: str
    kind: str
    title: str
    summary: str | None = None
    minutes: int | None = None
    lesson_count: int | None = None
    quiz_count: int | None = None
    products: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    artwork: dict | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def tags(self) -> list[str]:
        return list(dict.fromkeys([*self.products, *self.roles]))


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(PRIVATE_USE.sub(" ", value).split())
    return text or None


def parse_minutes(value: str) -> int | None:
    text = clean(value)
    if not text:
        return None
    match = DURATION.fullmatch(text)
    if not match or not (match["hours"] or match["minutes"]):
        return None
    return round(float(match["hours"] or 0) * 60) + int(match["minutes"] or 0)


def parse_iso_minutes(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = ISO_DURATION.fullmatch(value.strip())
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = match.groups()
    total = int(days or 0) * 1440 + int(hours or 0) * 60 + int(minutes or 0)
    return total + round(float(seconds or 0) / 60)


def _meta(doc: Node, key: str) -> str | None:
    for node in doc.find_all("meta"):
        if node.attrs.get("property") == key or node.attrs.get("name") == key:
            return clean(node.attrs.get("content"))
    return None


def _json_ld(doc: Node) -> list[dict]:
    found: list[dict] = []
    for node in doc.find_all("script", type="application/ld+json"):
        try:
            value = json.loads(node.raw_text())
        except ValueError:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                graph = item.get("@graph")
                found.extend(x for x in graph if isinstance(x, dict)) if isinstance(
                    graph, list
                ) else found.append(item)
    return found


def _same_page(value: object, url: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return resource_url(urljoin(url, value)) == url
    except ValueError:
        return False


def _absolute(href: str | None, base: str) -> str | None:
    if not href or href.startswith("#"):
        return None
    target = urljoin(base, href)
    return target if target.startswith(ACADEMY_ORIGIN + "/") else None


def _artwork(doc: Node, primary: dict | None, url: str) -> dict | None:
    """The page's own share image. Site-wide fallbacks and images of other pages are absent."""
    candidates: list[object] = []
    if primary:
        image = primary.get("image")
        for item in image if isinstance(image, list) else [image]:
            candidates.append(item.get("url") if isinstance(item, dict) else item)
    candidates.append(_meta(doc, "og:image"))
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        try:
            image_url = artwork_url(urljoin(url, candidate.strip()), url)
        except ValueError:
            continue
        alt = _meta(doc, "og:image:alt")
        return {"url": image_url, "alt": alt[:500] if alt else None, "sourceUrl": url}
    return None


def _chips(main: Node | None) -> list[str]:
    h1 = main.find("h1") if main else None
    box = h1.parent.next_element() if h1 and h1.parent else None
    if box is None or not box.elements or any(e.tag != "span" for e in box.elements):
        return []
    return [text for e in box.elements if (text := clean(e.text()))]


def _course_outline(main: Node, url: str, page: PageMetadata) -> list[dict]:
    nav = next(
        (n for n in main.find_all("nav") if n.attrs.get("aria-label") == "Course outline"), None
    )
    if nav is None:
        return []
    course = resource_slug(url)
    sections: list[dict] = []
    for listing in nav.find_all("ul"):
        heading = listing.previous_element()
        # Lists without a section heading hold the completion badge, not lessons.
        title = clean(heading.text()) if heading is not None and heading.tag == "span" else None
        if not title:
            continue
        units = []
        for item in listing.elements:
            link = item.find("a")
            href = _absolute(link.attrs.get("href") if link else None, url)
            if link is None or href is None:
                continue
            try:
                unit_url = official_url(href)
            except ValueError:
                page.warnings.append(f"Skipped outline link outside the course: {href}")
                continue
            match = UNIT_PATH.fullmatch(unit_url.removeprefix(ACADEMY_ORIGIN))
            if not match or match.group(1) != course:
                page.warnings.append(f"Skipped outline link outside the course: {href}")
                continue
            labels = [clean(s.text()) for s in link.elements if s.tag == "span"]
            unit_title = labels[0] if labels else clean(link.text())
            if not unit_title:
                continue
            quiz = any(label and label.casefold() == "quiz" for label in labels[1:])
            units.append(
                {
                    "title": unit_title[:MAX_TEXT],
                    "url": unit_url,
                    "kind": "quiz" if quiz else "lesson",
                    "context": None,
                    "videoCount": None,
                }
            )
        if units:
            sections.append({"title": title[:MAX_TEXT], "context": None, "units": units})
    return sections


def _collection_members(main: Node, url: str) -> tuple[list[str], list[dict]]:
    members: dict[str, None] = {}
    sections: list[dict] = []
    for section in main.find_all("section"):
        heading = section.find("h2")
        units = []
        for link in section.find_all("a"):
            href = _absolute(link.attrs.get("href"), url)
            try:
                member = resource_url(href) if href else None
            except ValueError:
                member = None
            if member is None or member == url or member in members:
                continue
            title_node = next((n for n in link.iter() if n.tag in {"h2", "h3", "h4"}), None)
            title = clean(title_node.text() if title_node else link.attrs.get("aria-label"))
            members[member] = None
            if title:
                units.append(
                    {
                        "title": title[:MAX_TEXT],
                        "url": member,
                        "kind": resource_kind(member),
                        "context": None,
                        "videoCount": None,
                    }
                )
        if units:
            title = clean(heading.text()) if heading else None
            sections.append(
                {"title": title[:MAX_TEXT] if title else None, "context": None, "units": units}
            )
    # Member links outside titled sections still count toward membership.
    for link in main.find_all("a"):
        href = _absolute(link.attrs.get("href"), url)
        try:
            member = resource_url(href) if href else None
        except ValueError:
            continue
        if member and member != url and not link_in_breadcrumb(link):
            members.setdefault(member, None)
    return list(members), sections


def link_in_breadcrumb(node: Node) -> bool:
    current = node.parent
    while current is not None:
        if current.tag == "nav" and current.attrs.get("aria-label") == "Breadcrumb":
            return True
        current = current.parent
    return False


def parse_page(url: str, text: str) -> PageMetadata:
    url = resource_url(url)
    kind = resource_kind(url)
    doc = parse_html(text)
    main = doc.find("main")
    ld = _json_ld(doc)
    primary = next((x for x in ld if _same_page(x.get("url"), url) and x.get("name")), None)

    title = None
    if primary:
        title = clean(str(primary["name"]))
    if not title and (og := _meta(doc, "og:title")):
        title = clean(SITE_SUFFIX.sub("", og))
    if not title and main and (h1 := main.find("h1")):
        title = clean(h1.text())
    if not title and (node := doc.find("title")):
        title = clean(SITE_SUFFIX.sub("", node.raw_text()))
    if not title:
        raise ValueError("Page has no title")
    page = PageMetadata(url=url, kind=kind, title=title[:MAX_TEXT])

    canonical = next(
        (n.attrs.get("href") for n in doc.find_all("link") if n.attrs.get("rel") == "canonical"),
        None,
    ) or _meta(doc, "og:url")
    if canonical and not _same_page(canonical, url):
        page.warnings.append(f"Canonical URL differs from the requested page: {canonical}")

    summary = None
    if primary and isinstance(primary.get("description"), str):
        summary = clean(primary["description"])
    summary = summary or _meta(doc, "og:description") or _meta(doc, "description")
    if summary and len(summary) > 1200:
        page.warnings.append("Summary longer than 1200 characters was left out")
        summary = None
    page.summary = summary
    page.artwork = _artwork(doc, primary, url)

    if primary:
        instances = primary.get("hasCourseInstance")
        for instance in instances if isinstance(instances, list) else [instances]:
            if isinstance(instance, dict) and page.minutes is None:
                page.minutes = parse_iso_minutes(instance.get("courseWorkload"))
        if page.minutes is None:
            page.minutes = parse_iso_minutes(primary.get("timeRequired"))

    for chip in _chips(main):
        lowered = chip.casefold()
        if lowered in IGNORED_CHIPS:
            continue
        if match := LESSONS.fullmatch(chip):
            page.lesson_count = int(match[1])
        elif match := QUIZZES.fullmatch(chip):
            page.quiz_count = int(match[1])
        elif (minutes := parse_minutes(chip)) is not None:
            if page.minutes is None:
                page.minutes = minutes
        elif chip == "Claude" or chip.startswith("Claude "):
            page.products.append(chip[:MAX_TEXT])
        else:
            page.roles.append(chip[:MAX_TEXT])
    page.products = list(dict.fromkeys(page.products))
    page.roles = list(dict.fromkeys(page.roles))

    if main is not None and kind == "course":
        page.sections = _course_outline(main, url, page)
        lessons = sum(u["kind"] == "lesson" for s in page.sections for u in s["units"])
        quizzes = sum(u["kind"] == "quiz" for s in page.sections for u in s["units"])
        if page.sections and page.lesson_count is not None and lessons != page.lesson_count:
            page.warnings.append(
                f"Outline lists {lessons} lessons but the header says {page.lesson_count}"
            )
        if page.sections and page.quiz_count is not None and quizzes != page.quiz_count:
            page.warnings.append(
                f"Outline lists {quizzes} quizzes but the header says {page.quiz_count}"
            )
    elif main is not None and kind == "collection":
        page.members, page.sections = _collection_members(main, url)
    return page
