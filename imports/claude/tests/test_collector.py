from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from conftest import FIXTURES, ORIGIN, SiteOpener, fixture_page

from claude_academy_api.collector import (
    CollectionAborted,
    collect,
    resource_queue,
    sitemap_urls,
)
from claude_academy_api.fetch import Fetcher
from claude_academy_api.models import CollectionArtifact
from claude_academy_api.parse import parse_page
from claude_academy_api.storage import SnapshotStore

COLLECTION = f"{ORIGIN}/collections/build-with-claude"
COURSE = f"{ORIGIN}/courses/claude-code-101"
TUTORIAL = f"{ORIGIN}/tutorials/choosing-the-right-claude-model"
USE_CASE = f"{ORIGIN}/use-cases/account-research-brief"


def run(site: SiteOpener, previous=None, **kwargs):
    fetcher = Fetcher(opener=site, sleep=lambda _: None, retries=0)
    outcome = collect(fetcher, previous, **kwargs)
    artifact = CollectionArtifact.model_validate_json(json.dumps(outcome.artifact))
    return fetcher, outcome, artifact


def sitemap(*urls: str) -> str:
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    )


def test_sitemap_queue_keeps_only_resource_pages_collections_first():
    urls = sitemap_urls((FIXTURES / "sitemap.xml").read_bytes())
    queue = resource_queue(urls)
    assert queue[0] == COLLECTION
    assert len(queue) == 6
    assert not any(u.endswith(("/all", "/courses", "/faq", "/products/code")) for u in queue)
    assert f"{COURSE}/what-is-claude-code" not in queue
    with pytest.raises(ValueError):
        sitemap_urls(b'<!DOCTYPE x [<!ENTITY a "b">]><urlset/>')
    with pytest.raises(ValueError):
        sitemap_urls(
            b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></sitemapindex>'
        )


def test_full_pass_builds_a_valid_artifact_with_collection_membership(tmp_path):
    site = SiteOpener()
    fetcher, outcome, artifact = run(site)
    assert site.calls[:2] == [f"{ORIGIN}/robots.txt", f"{ORIGIN}/sitemap.xml"]
    assert site.calls[2] == COLLECTION
    assert artifact.fetch_report.requests == len(site.calls) == fetcher.requests
    assert not any(u.endswith(("/all", "/courses", "/products/code")) for u in site.calls)
    assert not any("/what-is-claude-code" in u for u in site.calls)

    members = parse_page(COLLECTION, fixture_page(COLLECTION)).members
    # Members missing from the sitemap are fetched too; the fixture site returns 404 for them.
    assert set(members) <= set(site.calls)
    assert set(outcome.failed) == {m for m in members if m not in outcome.pages}

    by_url = {r.url: r for r in artifact.resources}
    assert len(by_url) == 6
    assert by_url[COURSE].category_ids == ["build-with-claude"]
    assert by_url[COURSE].provenance.source_urls == [COURSE, COLLECTION]
    assert by_url[USE_CASE].category_ids == [] and by_url[USE_CASE].tags == [
        "Claude Cowork",
        "Sales",
    ]
    assert by_url[COURSE].duration.course_minutes == 81
    assert by_url[COLLECTION].duration.course_minutes is None
    assert all(r.media == [] and r.audiences == [] and r.level is None for r in by_url.values())
    assert [c.model_dump() for c in artifact.categories] == [
        {"id": "build-with-claude", "label": "Build with Claude"}
    ]
    (coverage,) = artifact.coverage
    assert coverage.state == "partial" and coverage.discovered == len(members)
    assert coverage.collected == sum(m in by_url for m in members)

    snapshot = SnapshotStore(tmp_path / "snapshot.json").publish_artifact(
        artifact, method="crawler", merge=False
    )
    assert all(r.provenance.method == "crawler" for r in snapshot.resources)
    assert all(r.id.startswith("ca_") for r in snapshot.resources)


def test_complete_coverage_when_every_member_is_read():
    members = parse_page(COLLECTION, fixture_page(COLLECTION)).members
    page = "<html><head><title>{0} · Claude Academy</title></head><body><main><h1>{0}</h1>"
    stubs = {m: page.format(m.rsplit("/", 1)[1]) + "</main></body></html>" for m in members}
    _, outcome, artifact = run(SiteOpener(pages=stubs))
    (coverage,) = artifact.coverage
    assert outcome.failed == {}
    assert coverage.state == "complete" and coverage.discovered == coverage.collected


def test_failed_pages_keep_their_last_record_and_removed_pages_leave(tmp_path):
    store = SnapshotStore(tmp_path / "snapshot.json")
    _, _, first = run(SiteOpener())
    previous = store.publish_artifact(first, method="crawler", merge=False)
    old = {r.url: r for r in previous.resources}

    later = datetime.now(UTC) + timedelta(seconds=1)
    site = SiteOpener(
        pages={
            f"{ORIGIN}/sitemap.xml": sitemap(COLLECTION, COURSE, TUTORIAL),
            TUTORIAL: 500,
        }
    )
    _, outcome, second = run(site, previous, now=lambda: later)
    by_url = {r.url: r for r in second.resources}
    assert USE_CASE not in by_url  # It left the sitemap.
    assert outcome.retained == [TUTORIAL]
    assert by_url[TUTORIAL].provenance.fetched_at == old[TUTORIAL].provenance.fetched_at
    assert by_url[TUTORIAL].title == old[TUTORIAL].title
    assert by_url[COURSE].provenance.fetched_at > old[COURSE].provenance.fetched_at
    snapshot = store.publish_artifact(second, method="crawler", merge=False)
    assert {r.url for r in snapshot.resources} == set(by_url)


def test_mass_failure_aborts_and_keeps_the_published_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "snapshot.json")
    _, _, first = run(SiteOpener())
    previous = store.publish_artifact(first, method="crawler", merge=False)
    before = store.path.read_bytes()
    failing = {u: 503 for u in [COLLECTION, COURSE, TUTORIAL, USE_CASE]}
    failing[f"{ORIGIN}/courses/introduction-to-agent-skills"] = 503
    with pytest.raises(CollectionAborted):
        run(SiteOpener(pages=failing), previous)
    assert store.path.read_bytes() == before


def test_robots_disallowed_pages_are_skipped_without_a_request():
    robots = (FIXTURES / "robots.txt").read_text() + "\nUser-agent: *\nDisallow: /use-cases/\n"
    robots = robots.replace("Disallow: /embed/\n", "Disallow: /embed/\nDisallow: /use-cases/\n")
    site = SiteOpener(robots=robots)
    _, outcome, artifact = run(site)
    assert USE_CASE in outcome.skipped and USE_CASE not in site.calls
    assert USE_CASE not in {r.url for r in artifact.resources}


def test_robots_blocking_the_sitemap_aborts_before_any_page():
    site = SiteOpener(robots="User-agent: *\nDisallow: /sitemap.xml\n")
    with pytest.raises(CollectionAborted):
        run(site)
    assert site.calls == [f"{ORIGIN}/robots.txt"]
