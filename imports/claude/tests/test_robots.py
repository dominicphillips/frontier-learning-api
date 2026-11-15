from __future__ import annotations

import pytest
from conftest import FIXTURES, ORIGIN

from claude_academy_api.fetch import PRODUCT
from claude_academy_api.robots import Robots

LIVE = Robots((FIXTURES / "robots.txt").read_text())


@pytest.mark.parametrize(
    "path",
    [
        "/courses/claude-code-101",
        "/collections/ai-fluency",
        "/tutorials/choosing-the-right-claude-model",
        "/use-cases/account-research-brief",
        "/sitemap.xml",
    ],
)
def test_saved_policy_allows_public_resource_pages(path):
    assert LIVE.allowed(ORIGIN + path, PRODUCT)


@pytest.mark.parametrize(
    "path",
    [
        "/api/catalog",
        "/mcp",
        "/mcp/tools",
        "/search-corpus.json",
        "/admin/x",
        "/badges/abc",
        "/certificates/abc",
        "/dashboard",
        "/settings/profile",
        "/login?returnTo=%2Fcourses",
        "/start",
        "/plan",
        "/labs/new",
        "/embed/courses/claude-101",
    ],
)
def test_saved_policy_blocks_private_and_machine_paths(path):
    assert not LIVE.allowed(ORIGIN + path, PRODUCT)
    assert LIVE.sitemaps == [ORIGIN + "/sitemap.xml"]


def test_longest_match_allow_ties_wildcards_and_agent_groups():
    robots = Robots(
        "User-agent: *\n"
        "Disallow: /courses/\n"
        "Allow: /courses/open\n"
        "Disallow: /*.json$\n"
        "Allow: /tie\n"
        "Disallow: /tie\n"
        "\n"
        "User-agent: claude-academy-api\n"
        "User-agent: other-bot\n"
        "Disallow: /tutorials/\n"
    )
    star = "some-other-crawler"
    assert not robots.allowed(ORIGIN + "/courses/closed", star)
    assert robots.allowed(ORIGIN + "/courses/open-course", star)
    assert not robots.allowed(ORIGIN + "/data.json", star)
    assert robots.allowed(ORIGIN + "/data.json?x=1", star)
    assert robots.allowed(ORIGIN + "/tie", star)
    # A named group replaces the * group for that crawler.
    assert robots.allowed(ORIGIN + "/courses/closed", PRODUCT)
    assert not robots.allowed(ORIGIN + "/tutorials/a", PRODUCT)
    assert Robots("").allowed(ORIGIN + "/anything", PRODUCT)
