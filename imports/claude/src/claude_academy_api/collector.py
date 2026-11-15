"""Deterministic collection: robots.txt, the sitemap, then each public resource page once.

No model or agent is involved. A page that fails keeps its previous record (marked by its older
`fetchedAt`); a page that left the sitemap leaves the snapshot.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .fetch import Fetcher, FetchError, RobotsDisallowed
from .models import Snapshot
from .parse import PageMetadata, parse_page
from .security import ACADEMY_ORIGIN, resource_kind, resource_url

SITEMAP_URL = ACADEMY_ORIGIN + "/sitemap.xml"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# Collections go first: their member links can add pages that the sitemap does not list.
ORDER = {"collection": 0, "course": 1, "tutorial": 2, "use-case": 3}
MAX_SOURCE_URLS = 16


class CollectionAborted(RuntimeError):
    pass


@dataclass
class Outcome:
    artifact: dict
    pages: dict[str, PageMetadata] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    retained: list[str] = field(default_factory=list)
    warnings: dict[str, list[str]] = field(default_factory=dict)


def sitemap_urls(body: bytes) -> list[str]:
    if b"<!DOCTYPE" in body[:2048].upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Sitemap must not declare a DOCTYPE or entities")
    root = ElementTree.fromstring(body)
    if root.tag != SITEMAP_NS + "urlset":
        raise ValueError("Only a single sitemap urlset is supported")
    return [
        (node.text or "").strip() for node in root.iter(SITEMAP_NS + "loc") if (node.text or "")
    ]


def resource_queue(urls: list[str]) -> list[str]:
    found: dict[str, None] = {}
    for url in urls:
        try:
            found.setdefault(resource_url(url), None)
        except ValueError:
            continue  # Index pages, lesson pages, product pages and help pages are not fetched.
    return sorted(found, key=lambda u: (ORDER[resource_kind(u)], u))


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _input_record(page: PageMetadata, categories: list[str], sources: list[str]) -> dict:
    minutes = page.minutes if page.kind != "collection" else None
    return {
        "title": page.title,
        "url": page.url,
        "kind": page.kind,
        "categoryIds": categories,
        "audiences": [],
        "tags": page.tags,
        "summary": page.summary,
        "level": None,
        "duration": {"courseMinutes": minutes, "pathMinutes": None, "videoSeconds": None},
        "detail": {
            "audience": None,
            "prerequisites": [],
            "objectives": [],
            "sections": page.sections,
        },
        "media": [],
        "artwork": page.artwork,
        "provenance": {"sourceUrls": sources, "fetchedAt": None},
    }


def collect(
    fetcher: Fetcher,
    previous: Snapshot | None = None,
    *,
    max_resources: int = 2000,
    min_kept_ratio: float = 0.5,
    now=lambda: datetime.now(UTC),
) -> Outcome:
    fetcher.load_robots()
    if not fetcher.allowed(SITEMAP_URL):
        raise CollectionAborted("robots.txt disallows the sitemap")
    queue = resource_queue(sitemap_urls(fetcher.get(SITEMAP_URL).body))
    if not queue:
        raise CollectionAborted("The sitemap lists no public resource pages")
    if len(queue) > max_resources:
        raise CollectionAborted(f"The sitemap lists more than {max_resources} resource pages")

    outcome = Outcome(artifact={})
    fetched_at: dict[str, datetime] = {}
    members: dict[str, list[str]] = {}  # collection URL -> member resource URLs
    seen = set(queue)
    index = 0
    while index < len(queue):
        url = queue[index]
        index += 1
        if not fetcher.allowed(url):
            outcome.skipped[url] = "robots.txt disallows this page"
            continue
        try:
            page = fetcher.get(url)
            metadata = parse_page(url, page.text())
        except RobotsDisallowed as exc:
            outcome.skipped[url] = str(exc)
            continue
        except (FetchError, ValueError) as exc:
            outcome.failed[url] = str(exc)
            continue
        outcome.pages[url] = metadata
        fetched_at[url] = page.fetched_at
        if metadata.warnings:
            outcome.warnings[url] = metadata.warnings
        if metadata.kind == "collection":
            members[url] = metadata.members
            # Collection members missing from the sitemap are still public resource pages.
            for member in metadata.members:
                if member not in seen and len(queue) < max_resources:
                    seen.add(member)
                    queue.append(member)

    old = {r.url: r for r in previous.resources} if previous else {}
    old_labels = {c.id: c.label for c in previous.categories} if previous else {}
    slug = {url: url.rsplit("/", 1)[1] for url in queue if resource_kind(url) == "collection"}

    # Categories are collections. A collection page that failed keeps its previous membership.
    category_members: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    fresh_categories: set[str] = set()
    for url in sorted(slug):
        category = slug[url]
        if url in outcome.pages:
            labels[category] = outcome.pages[url].title
            category_members[category] = set(members[url])
            fresh_categories.add(category)
        elif category in old_labels:
            labels[category] = old_labels[category]
            category_members[category] = {r.url for r in old.values() if category in r.category_ids}

    def categories_of(url: str) -> list[str]:
        return sorted(c for c, urls in category_members.items() if url in urls)

    resources = []
    for url in queue:
        categories = categories_of(url)
        sources = [url, *(f"{ACADEMY_ORIGIN}/collections/{c}" for c in categories)]
        if url in outcome.pages:
            record = _input_record(outcome.pages[url], categories, sources[:MAX_SOURCE_URLS])
            record["provenance"]["fetchedAt"] = fetched_at[url]
            resources.append(record)
        elif url in old and url not in outcome.skipped:
            record = old[url].model_dump(mode="json", by_alias=True, exclude={"id"})
            record["categoryIds"] = categories
            record["provenance"] = {
                "sourceUrls": record["provenance"]["sourceUrls"],
                "fetchedAt": old[url].provenance.fetched_at,
            }
            resources.append(record)
            outcome.retained.append(url)

    fresh = len(outcome.pages)
    if old and fresh < min_kept_ratio * len(old):
        raise CollectionAborted(
            f"Only {fresh} pages were read against {len(old)} published; keeping the snapshot"
        )
    if not fresh:
        raise CollectionAborted("No resource page could be read")

    present = {r["url"] for r in resources}
    coverage = []
    for category in sorted(labels):
        collected = sum(category in r["categoryIds"] for r in resources)
        expected = category_members[category]
        complete = category in fresh_categories and all(u in outcome.pages for u in expected)
        if collected == 0 and category not in fresh_categories:
            state = "not-collected"
        else:
            state = "complete" if complete and expected <= present else "partial"
        coverage.append(
            {
                "categoryId": category,
                "state": state,
                "discovered": len(expected) if category in fresh_categories else None,
                "collected": collected,
            }
        )
    generated = now()
    for record in resources:
        record["provenance"]["fetchedAt"] = _utc(record["provenance"]["fetchedAt"])
    outcome.artifact = {
        "schemaVersion": 1,
        "generatedAt": _utc(generated),
        "categories": [{"id": c, "label": labels[c]} for c in sorted(labels)],
        "resources": resources,
        "coverage": coverage,
        "fetchReport": {
            "requests": fetcher.requests,
            "robotsChecked": True,
            "completedWithinLimits": True,
        },
    }
    return outcome
