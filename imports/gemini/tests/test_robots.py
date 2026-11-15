from __future__ import annotations

import pytest
from conftest import FIXTURES, ORIGIN

from gemini_academy_api.fetch import PRODUCT
from gemini_academy_api.robots import Robots

LIVE = Robots((FIXTURES / "robots.txt").read_text())


@pytest.mark.parametrize(
    "path",
    [
        "/catalog",
        "/catalog?page=1",
        "/paths/3666",
        "/course_templates/1401",
        "/focuses/104012?parent=catalog",
        "/sitemap.xml",
    ],
)
def test_saved_policy_allows_public_resource_and_catalog_pages(path):
    assert LIVE.allowed(ORIGIN + path, PRODUCT)


@pytest.mark.parametrize(
    "path",
    [
        "/api/catalog",
        "/focuses/104012/start",
        "/focuses/104012/resume",
        "/focuses/104012/stop",
    ],
)
def test_saved_policy_blocks_api_and_focus_action_paths(path):
    assert not LIVE.allowed(ORIGIN + path, PRODUCT)
    assert LIVE.sitemaps == [ORIGIN + "/sitemap.xml"]


def test_longest_match_allow_ties_wildcards_and_agent_groups():
    robots = Robots(
        "User-agent: *\n"
        "Disallow: /course_templates/\n"
        "Allow: /course_templates/1401\n"
        "Disallow: /*.json$\n"
        "Allow: /tie\n"
        "Disallow: /tie\n"
        "\n"
        "User-agent: gemini-academy-api\n"
        "User-agent: other-bot\n"
        "Disallow: /paths/\n"
    )
    star = "some-other-crawler"
    assert not robots.allowed(ORIGIN + "/course_templates/999", star)
    assert robots.allowed(ORIGIN + "/course_templates/1401", star)
    assert not robots.allowed(ORIGIN + "/data.json", star)
    assert robots.allowed(ORIGIN + "/data.json?x=1", star)
    assert robots.allowed(ORIGIN + "/tie", star)
    # A named group replaces the * group for that crawler.
    assert robots.allowed(ORIGIN + "/course_templates/999", PRODUCT)
    assert not robots.allowed(ORIGIN + "/paths/3666", PRODUCT)
    assert Robots("").allowed(ORIGIN + "/anything", PRODUCT)
