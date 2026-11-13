from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from conftest import ORIGIN, SiteOpener, fixture_page

from gemini_academy_api.collector import (
    CATALOG_URL,
    CollectionAborted,
    collect,
)
from gemini_academy_api.fetch import Fetcher
from gemini_academy_api.models import CollectionArtifact
from gemini_academy_api.parse import parse_page
from gemini_academy_api.storage import SnapshotStore

PATH_3666 = f"{ORIGIN}/paths/3666"
COURSE_1401 = f"{ORIGIN}/course_templates/1401"
COURSE_1232 = f"{ORIGIN}/course_templates/1232"
COURSE_1600 = f"{ORIGIN}/course_templates/1600"
LAB_104701 = f"{ORIGIN}/focuses/104701?parent=catalog"
LAB_124709 = f"{ORIGIN}/focuses/124709?parent=catalog"
CAT_3666 = "gemini-enterprise-and-gemini-notebook-3666"


def run(site: SiteOpener, previous=None, **kwargs):
    fetcher = Fetcher(opener=site, sleep=lambda _: None, retries=0)
    outcome = collect(fetcher, previous, **kwargs)
    artifact = CollectionArtifact.model_validate_json(json.dumps(outcome.artifact))
    return fetcher, outcome, artifact


def listing_html(items: list[dict], results_count: int) -> str:
    payload = json.dumps({"searchResults": items, "resultsCount": results_count, "itemsPerPage": 8})
    return (
        "<html><head><title>Catalog | Google Skills</title></head><body>"
        f"<ql-search-result-container pagedSearchResults='{payload}'></ql-search-result-container>"
        "</body></html>"
    )


def course_stub(course_id: str, title: str) -> str:
    return (
        f"<html><head><meta name='description' content='{title} summary'></head>"
        f"<body><div class='top-title'><h1>{title}</h1></div>"
        f"<span class='course-detail'>1 hour</span><span class='course-detail'>Introductory</span>"
        f"</body></html>"
    )


def test_full_pass_builds_valid_artifact_and_never_fetches_labs(tmp_path):
    site = SiteOpener()
    fetcher, outcome, artifact = run(site)

    assert site.calls[:4] == [
        f"{ORIGIN}/robots.txt",
        f"{CATALOG_URL}?page=1",
        f"{CATALOG_URL}?page=2",
        f"{CATALOG_URL}?page=3",
    ]
    assert not any("/focuses/" in u for u in site.calls)
    assert PATH_3666 in site.calls
    assert COURSE_1401 in site.calls and COURSE_1600 in site.calls
    assert artifact.fetch_report.requests == len(site.calls) == fetcher.requests

    by_url = {r.url: r for r in artifact.resources}
    # In-scope: path 3666, courses 1401, 1232, path-only course 1600,
    # listing lab 104701, path-only lab 124709.
    # Path-only courses 1191, 1559, 1587 returned 404 from fixtures and have no previous record.
    assert set(by_url) == {PATH_3666, COURSE_1401, COURSE_1232, COURSE_1600, LAB_104701, LAB_124709}
    assert set(outcome.failed) == {
        f"{ORIGIN}/course_templates/1191",
        f"{ORIGIN}/course_templates/1559",
        f"{ORIGIN}/course_templates/1587",
    }

    assert by_url[PATH_3666].category_ids == [CAT_3666]
    assert by_url[PATH_3666].duration.path_minutes == 1004
    assert by_url[PATH_3666].duration.course_minutes is None
    assert by_url[COURSE_1401].category_ids == [CAT_3666]
    assert by_url[COURSE_1401].provenance.source_urls == [COURSE_1401, CATALOG_URL, PATH_3666]
    assert by_url[COURSE_1600].category_ids == [CAT_3666]
    assert by_url[COURSE_1600].provenance.source_urls == [COURSE_1600, PATH_3666]
    assert by_url[COURSE_1232].tags == ["Skill badge"]
    assert by_url[LAB_104701].provenance.source_urls == [LAB_104701, CATALOG_URL]
    assert by_url[LAB_124709].summary is None and by_url[LAB_124709].level is None
    assert by_url[LAB_124709].duration.course_minutes == 90
    assert by_url[LAB_124709].provenance.source_urls == [LAB_124709, PATH_3666]
    assert all(r.media == [] and r.audiences == [] and r.artwork is None for r in by_url.values())

    (coverage,) = artifact.coverage
    assert coverage.category_id == CAT_3666
    assert coverage.state == "partial"
    assert coverage.discovered == 7  # path + 6 members
    assert coverage.collected == 4  # path + 1401 + 1600 + lab 124709

    snapshot = SnapshotStore(tmp_path / "snapshot.json").publish_artifact(
        artifact, method="crawler", merge=False
    )
    assert all(r.provenance.method == "crawler" for r in snapshot.resources)
    assert all(r.id.startswith("ga_") for r in snapshot.resources)


def test_complete_coverage_and_deprecated_path_member_filtering():
    stubs = {
        f"{ORIGIN}/course_templates/1191": course_stub("1191", "Accelerate Knowledge Exchange"),
        f"{ORIGIN}/course_templates/1559": course_stub(
            "1559", "Unlock Insights with Gemini Notebook"
        ),
        f"{ORIGIN}/course_templates/1587": course_stub("1587", "Enterprise Agents and Use Cases"),
    }
    site = SiteOpener(pages=stubs)
    _, outcome, artifact = run(site)
    (coverage,) = artifact.coverage
    assert outcome.failed == {}
    assert coverage.state == "complete" and coverage.discovered == coverage.collected == 7
    assert not any("/focuses/" in u for u in site.calls)

    # Path 2919 includes a [DEPRECATED] course member (1166) that must be excluded.
    p2919_listing = listing_html(
        [
            {
                "type": "learning_path",
                "title": "Gemini for Government",
                "description": "Gemini for Government",
                "path": "/paths/2919",
                "duration": "13 hours 14 minutes",
                "level": None,
                "credentialType": None,
            }
        ],
        results_count=1,
    )
    p2919_stubs = {
        f"{CATALOG_URL}?page=1": p2919_listing,
        f"{CATALOG_URL}?page=2": listing_html([], results_count=1),
        f"{ORIGIN}/course_templates/1191": course_stub("1191", "Accelerate Knowledge Exchange"),
        f"{ORIGIN}/course_templates/1402": course_stub("1402", "Configure Gemini Code Assist"),
        f"{ORIGIN}/course_templates/1385": course_stub("1385", "Model Armor"),
    }
    p2919_site = SiteOpener(pages=p2919_stubs)
    _, _, p2919_artifact = run(p2919_site)
    assert f"{ORIGIN}/course_templates/1166" not in p2919_site.calls
    assert f"{ORIGIN}/course_templates/1166" not in {r.url for r in p2919_artifact.resources}


def test_failed_course_keeps_last_record_and_out_of_scope_entry_leaves(tmp_path):
    stubs = {
        f"{ORIGIN}/course_templates/1191": course_stub("1191", "Accelerate Knowledge Exchange"),
        f"{ORIGIN}/course_templates/1559": course_stub(
            "1559", "Unlock Insights with Gemini Notebook"
        ),
        f"{ORIGIN}/course_templates/1587": course_stub("1587", "Enterprise Agents and Use Cases"),
    }
    store = SnapshotStore(tmp_path / "snapshot.json")
    _, _, first = run(SiteOpener(pages=stubs))
    previous = store.publish_artifact(first, method="crawler", merge=False)
    old = {r.url: r for r in previous.resources}

    # On run 2, course 1232 left scope (omitted from listing), and course 1401 fails with 500.
    p1_narrow = listing_html(
        [
            {
                "type": "learning_path",
                "title": "Gemini Enterprise and Gemini Notebook",
                "description": "Gemini Enterprise",
                "path": "/paths/3666",
                "duration": "16 hours 44 minutes",
                "level": None,
                "credentialType": None,
            },
            {
                "type": "course",
                "title": "Introduction to Gemini Enterprise",
                "description": "Gemini Enterprise course",
                "path": "/course_templates/1401",
                "duration": "2 hours 15 minutes",
                "level": "introductory",
                "credentialType": None,
            },
            {
                "type": "lab",
                "title": "Intro to Context Caching with the Gemini API",
                "description": "Gemini API lab",
                "path": "/focuses/104701",
                "duration": "45 minutes",
                "level": "intermediate",
                "credentialType": None,
            },
        ],
        results_count=3,
    )
    later = datetime.now(UTC) + timedelta(seconds=1)
    site2 = SiteOpener(
        pages=stubs
        | {
            f"{CATALOG_URL}?page=1": p1_narrow,
            f"{CATALOG_URL}?page=2": listing_html([], results_count=3),
            COURSE_1401: 500,
        }
    )
    _, outcome, second = run(site2, previous, now=lambda: later)
    by_url = {r.url: r for r in second.resources}
    assert COURSE_1232 not in by_url
    assert outcome.retained == [COURSE_1401]
    assert by_url[COURSE_1401].provenance.fetched_at == old[COURSE_1401].provenance.fetched_at
    assert by_url[COURSE_1600].provenance.fetched_at > old[COURSE_1600].provenance.fetched_at


def test_ninety_percent_listing_check_zero_scope_and_half_kept_aborts(tmp_path):
    # 90% listing check fails when resultsCount=100 but only 3 distinct entries returned.
    short_p1 = listing_html(
        [
            {
                "type": "course",
                "title": "Gemini Course",
                "description": "Gemini",
                "path": "/course_templates/1401",
                "duration": "1 hour",
                "level": "introductory",
                "credentialType": None,
            }
        ],
        results_count=100,
    )
    with pytest.raises(CollectionAborted, match="distinct entries"):
        run(
            SiteOpener(
                pages={
                    f"{CATALOG_URL}?page=1": short_p1,
                    f"{CATALOG_URL}?page=2": listing_html([], results_count=100),
                }
            )
        )

    # Zero in-scope entries aborts.
    no_gemini = listing_html(
        [
            {
                "type": "course",
                "title": "Cloud SQL Basics",
                "description": "Databases",
                "path": "/course_templates/1401",
                "duration": "1 hour",
                "level": "introductory",
                "credentialType": None,
            }
        ],
        results_count=1,
    )
    with pytest.raises(CollectionAborted, match="no in-scope"):
        run(
            SiteOpener(
                pages={
                    f"{CATALOG_URL}?page=1": no_gemini,
                    f"{CATALOG_URL}?page=2": listing_html([], results_count=1),
                }
            )
        )

    # Half-kept rule aborts and preserves the published snapshot.
    stubs = {
        f"{ORIGIN}/course_templates/1191": course_stub("1191", "Accelerate Knowledge Exchange"),
        f"{ORIGIN}/course_templates/1559": course_stub(
            "1559", "Unlock Insights with Gemini Notebook"
        ),
        f"{ORIGIN}/course_templates/1587": course_stub("1587", "Enterprise Agents and Use Cases"),
    }
    store = SnapshotStore(tmp_path / "snapshot.json")
    _, _, first = run(SiteOpener(pages=stubs))
    previous = store.publish_artifact(first, method="crawler", merge=False)
    before = store.path.read_bytes()

    failing = {
        PATH_3666: 503,
        COURSE_1401: 503,
        COURSE_1232: 503,
        COURSE_1600: 503,
        f"{ORIGIN}/course_templates/1191": 503,
        f"{ORIGIN}/course_templates/1559": 503,
        f"{ORIGIN}/course_templates/1587": 503,
    }
    with pytest.raises(CollectionAborted, match="keeping the snapshot"):
        run(SiteOpener(pages=failing), previous)
    assert store.path.read_bytes() == before


def test_robots_disallow_skips_page_and_blocks_catalog():
    robots = "User-agent: *\nDisallow: /api/\nDisallow: /course_templates/1232\n"
    site = SiteOpener(robots=robots)
    _, outcome, artifact = run(site)
    assert COURSE_1232 in outcome.skipped and COURSE_1232 not in site.calls
    assert COURSE_1232 not in {r.url for r in artifact.resources}

    blocked_catalog = SiteOpener(robots="User-agent: *\nDisallow: /catalog\n")
    with pytest.raises(CollectionAborted, match="robots.txt disallows"):
        run(blocked_catalog)
    assert blocked_catalog.calls == [f"{ORIGIN}/robots.txt"]
    parsed_path = parse_page(PATH_3666, fixture_page(PATH_3666))
    assert parsed_path.title == "Gemini Enterprise and Gemini Notebook"


def test_course_that_redirects_anonymous_visitors_is_not_public_and_leaves_the_path_complete():
    # Course 1191 now sends anonymous visitors to the home page: it is skipped, not failed, and the
    # path's coverage counts only the members a visitor can open.
    stubs = {
        f"{ORIGIN}/course_templates/1191": 302,
        f"{ORIGIN}/course_templates/1559": course_stub("1559", "Unlock Insights with Gemini Notebook"),
        f"{ORIGIN}/course_templates/1587": course_stub("1587", "Enterprise Agents and Use Cases"),
    }
    _, outcome, artifact = run(SiteOpener(pages=stubs))
    (coverage,) = artifact.coverage
    assert outcome.failed == {}
    assert "not public" in outcome.skipped[f"{ORIGIN}/course_templates/1191"]
    assert f"{ORIGIN}/course_templates/1191" not in {r.url for r in artifact.resources}
    assert coverage.state == "complete" and coverage.discovered == coverage.collected == 6
