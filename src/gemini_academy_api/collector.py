"""Deterministic collection: robots.txt, catalog listing, in-scope paths, then courses.

No model or agent is involved. Labs are never fetched; their records come from the catalog
listing or a learning path card. A path or course page that fails keeps its previous record
(marked by its older `fetchedAt`); an entry that left scope leaves the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .fetch import Fetcher, FetchError, RobotsDisallowed
from .models import Snapshot
from .parse import (
    ListingEntry,
    PageMetadata,
    PathMember,
    parse_listing_page,
    parse_page,
    path_category_id,
)
from .scope import in_text_scope, is_deprecated
from .security import ACADEMY_ORIGIN, resource_kind

CATALOG_URL = ACADEMY_ORIGIN + "/catalog"
MAX_LISTING_PAGES = 400
MIN_LISTING_RATIO = 0.9
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


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def discover_catalog(
    fetcher: Fetcher,
    *,
    max_listing_pages: int = MAX_LISTING_PAGES,
) -> tuple[dict[str, ListingEntry], dict[str, datetime], int]:
    entries: dict[str, ListingEntry] = {}
    fetched_at: dict[str, datetime] = {}
    last_results_count: int | None = None

    for page_num in range(1, max_listing_pages + 2):
        if page_num > max_listing_pages:
            raise CollectionAborted(f"Catalog listing exceeded {max_listing_pages} pages")
        url = f"{CATALOG_URL}?page={page_num}"
        if not fetcher.allowed(url):
            raise CollectionAborted(f"robots.txt disallows {url}")
        try:
            page = fetcher.get(url)
            parsed = parse_listing_page(page.text())
        except (FetchError, ValueError) as exc:
            raise CollectionAborted(f"Catalog listing page {page_num} failed: {exc}") from exc
        last_results_count = parsed.results_count
        if not parsed.entries and not parsed.unrecognised:
            break
        for entry in parsed.entries:
            if entry.url not in entries:
                entries[entry.url] = entry
                fetched_at[entry.url] = page.fetched_at

    if not entries or last_results_count is None:
        raise CollectionAborted("Catalog listing returned zero entries")
    if len(entries) < MIN_LISTING_RATIO * last_results_count:
        raise CollectionAborted(
            f"Catalog listing yielded {len(entries)} distinct entries "
            f"against {last_results_count} reported"
        )
    return entries, fetched_at, last_results_count


def _input_record(
    page: PageMetadata,
    categories: list[str],
    sources: list[str],
    listing: ListingEntry | None = None,
) -> dict:
    summary = page.summary
    if summary is None and not page.summary_overlong and listing is not None:
        summary = listing.summary
    level = page.level if page.level is not None else (listing.level if listing else None)
    minutes = page.minutes if page.minutes is not None else (listing.minutes if listing else None)
    tags = list(dict.fromkeys([*page.tags, *(listing.tags if listing else [])]))
    if page.kind == "learning-path":
        duration = {"courseMinutes": None, "pathMinutes": minutes, "videoSeconds": None}
    else:
        duration = {"courseMinutes": minutes, "pathMinutes": None, "videoSeconds": None}
    return {
        "title": page.title,
        "url": page.url,
        "kind": page.kind,
        "categoryIds": categories,
        "audiences": [],
        "tags": tags,
        "summary": summary,
        "level": level,
        "duration": duration,
        "detail": {
            "audience": None,
            "prerequisites": [],
            "objectives": [],
            "sections": page.sections,
        },
        "media": [],
        "artwork": None,
        "provenance": {"sourceUrls": sources, "fetchedAt": None},
    }


def collect(
    fetcher: Fetcher,
    previous: Snapshot | None = None,
    *,
    max_resources: int = 2000,
    max_listing_pages: int = MAX_LISTING_PAGES,
    min_kept_ratio: float = 0.5,
    now=lambda: datetime.now(UTC),
) -> Outcome:
    fetcher.load_robots()
    listing_entries, listing_fetched_at, _ = discover_catalog(
        fetcher, max_listing_pages=max_listing_pages
    )

    path_urls = sorted(
        u
        for u, e in listing_entries.items()
        if e.kind == "learning-path" and in_text_scope(e.title, e.description)
    )
    course_urls = {
        u
        for u, e in listing_entries.items()
        if e.kind == "course" and in_text_scope(e.title, e.description)
    }
    lab_urls = {
        u
        for u, e in listing_entries.items()
        if e.kind == "lab" and in_text_scope(e.title, e.description)
    }
    if not (path_urls or course_urls or lab_urls):
        raise CollectionAborted("Catalog listing contains no in-scope Gemini resources")

    old = {r.url: r for r in previous.resources} if previous else {}
    old_labels = {c.id: c.label for c in previous.categories} if previous else {}
    old_category_by_url = {
        r.url: next(
            (cid for cid in r.category_ids if cid.endswith(f"-{r.url.rsplit('/', 1)[1]}")),
            r.category_ids[0] if r.category_ids else None,
        )
        for r in old.values()
        if r.kind == "learning-path"
    }

    outcome = Outcome(artifact={})
    fetched_at: dict[str, datetime] = {}
    path_members: dict[str, list[str]] = {}
    path_cards: dict[str, tuple[PathMember, datetime]] = {}
    active_paths: list[str] = []

    for url in path_urls:
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
            active_paths.append(url)
            if (cid := old_category_by_url.get(url)) is not None:
                for member in old.values():
                    if member.url != url and cid in member.category_ids:
                        if member.kind == "course":
                            course_urls.add(member.url)
                        elif member.kind == "lab":
                            lab_urls.add(member.url)
            continue
        if is_deprecated(metadata.title):
            continue
        active_paths.append(url)
        outcome.pages[url] = metadata
        fetched_at[url] = page.fetched_at
        if metadata.warnings:
            outcome.warnings[url] = metadata.warnings

        kept_cards: list[PathMember] = []
        for card in metadata.member_cards:
            listing = listing_entries.get(card.url)
            if is_deprecated(card.title) or (listing is not None and is_deprecated(listing.title)):
                continue
            kept_cards.append(card)
            path_cards.setdefault(card.url, (card, page.fetched_at))
            if card.kind == "course":
                course_urls.add(card.url)
            elif card.kind == "lab":
                lab_urls.add(card.url)
        metadata.member_cards = kept_cards
        metadata.members = [card.url for card in kept_cards]
        if kept_cards:
            metadata.sections = [
                {
                    "title": None,
                    "context": None,
                    "units": [
                        {
                            "title": card.title,
                            "url": card.url,
                            "kind": card.kind,
                            "context": None,
                            "videoCount": None,
                        }
                        for card in kept_cards
                    ],
                }
            ]
        else:
            metadata.sections = []
        path_members[url] = metadata.members

    total_queued = len(active_paths) + len(course_urls) + len(lab_urls)
    if total_queued > max_resources:
        raise CollectionAborted(
            f"In-scope queue ({total_queued}) exceeds max_resources ({max_resources})"
        )

    active_courses: list[str] = []
    for url in sorted(course_urls):
        if not fetcher.allowed(url):
            outcome.skipped[url] = "robots.txt disallows this page"
            continue
        try:
            page = fetcher.get(url)
            metadata = parse_page(url, page.text())
        except RobotsDisallowed as exc:
            outcome.skipped[url] = str(exc)
            active_courses.append(url)
            continue
        except (FetchError, ValueError) as exc:
            outcome.failed[url] = str(exc)
            active_courses.append(url)
            continue
        if is_deprecated(metadata.title):
            for members in path_members.values():
                if url in members:
                    members.remove(url)
            continue
        active_courses.append(url)
        outcome.pages[url] = metadata
        fetched_at[url] = page.fetched_at
        if metadata.warnings:
            outcome.warnings[url] = metadata.warnings

    active_labs: list[str] = []
    for url in sorted(lab_urls):
        if not fetcher.allowed(url):
            outcome.skipped[url] = "robots.txt disallows this page"
            continue
        if url in listing_entries:
            entry = listing_entries[url]
            outcome.pages[url] = PageMetadata(
                url=url,
                kind="lab",
                title=entry.title,
                summary=entry.summary,
                minutes=entry.minutes,
                level=entry.level,
                tags=list(entry.tags),
            )
            fetched_at[url] = listing_fetched_at[url]
            active_labs.append(url)
        elif url in path_cards:
            card, card_time = path_cards[url]
            outcome.pages[url] = PageMetadata(
                url=url,
                kind="lab",
                title=card.title,
                summary=None,
                minutes=card.minutes,
                level=None,
                tags=[],
            )
            fetched_at[url] = card_time
            active_labs.append(url)
        elif url in old:
            active_labs.append(url)

    category_members: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    category_path_url: dict[str, str] = {}
    fresh_categories: set[str] = set()
    for path_url in active_paths:
        if path_url in outcome.pages:
            title = outcome.pages[path_url].title
            cid = path_category_id(title, path_url)
            labels[cid] = title
            category_path_url[cid] = path_url
            category_members[cid] = {path_url, *path_members.get(path_url, [])}
            fresh_categories.add(cid)
        else:
            cid = old_category_by_url.get(path_url)
            if cid and cid in old_labels:
                labels[cid] = old_labels[cid]
                category_path_url[cid] = path_url
                category_members[cid] = {r.url for r in old.values() if cid in r.category_ids}

    def categories_of(url: str) -> list[str]:
        return sorted(c for c, urls in category_members.items() if url in urls)

    all_urls = [*active_paths, *active_courses, *active_labs]
    resources = []
    for url in all_urls:
        categories = categories_of(url)
        sources: list[str] = [url]
        if url in listing_entries:
            sources.append(CATALOG_URL)
        for cid in categories:
            p_url = category_path_url.get(cid)
            if p_url and p_url not in sources:
                sources.append(p_url)
        sources = sources[:MAX_SOURCE_URLS]

        if url in outcome.pages:
            record = _input_record(
                outcome.pages[url],
                categories,
                sources,
                listing_entries.get(url),
            )
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
            f"Only {fresh} resources were read against {len(old)} published; keeping the snapshot"
        )
    if not fresh:
        raise CollectionAborted("No resource could be read")

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


__all__ = [
    "CATALOG_URL",
    "CollectionAborted",
    "MAX_LISTING_PAGES",
    "MIN_LISTING_RATIO",
    "Outcome",
    "collect",
    "discover_catalog",
    "resource_kind",
]
