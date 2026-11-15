from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from claude_academy_api.models import CollectionArtifact
from claude_academy_api.security import (
    artwork_url,
    official_url,
    resource_kind,
    resource_url,
    source_url,
    stable_id,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://academy.claude.com/courses/a",
        "https://academy.claude.com.evil.example/courses/a",
        "https://academy.claude.com@evil.example/courses/a",
        "https://user:secret@academy.claude.com/courses/a",
        "https://anthropic.skilljar.com/claude-code-in-action",
        "https://127.0.0.1/courses/a",
        "https://[::1]/courses/a",
        "https://academy.claude.com:444/courses/a",
        "https://academy.claude.com/courses/%2e%2e/login",
        "https://academy.claude.com/courses/%252e%252e/login",
        "https://academy.claude.com/courses/a\\b",
        "https://academy.claude.com/courses/a%0d%0aHost:evil",
        "https://academy.claude.com/courses/a/lesson",
        "https://academy.claude.com/courses",
        "https://academy.claude.com/products/code",
        "https://academy.claude.com/help/faq",
        "https://academy.claude.com/api/courses",
        "https://academy.claude.com/labs/x",
        "https://academy.claude.com/embed/courses/a",
        "https://academy.claude.com/badges/x",
        "https://academy.claude.com/Courses/A",
    ],
)
def test_only_public_resource_pages_are_resources(url):
    with pytest.raises(ValueError):
        resource_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://academy.claude.com/search-corpus.json",
        "https://academy.claude.com/dashboard",
        "https://academy.claude.com/start",
        "https://academy.claude.com/certificates/abc",
        "https://academy.claude.com/courses/a/b/c",
    ],
)
def test_excluded_paths_are_never_sources(url):
    with pytest.raises(ValueError):
        source_url(url)


def test_canonical_urls_kinds_and_stable_ids():
    a = "https://academy.claude.com/courses/claude-code-101"
    b = "https://academy.claude.com/courses/claude-code-101/?ref=nav#outline"
    assert resource_url(b) == a
    assert stable_id(a) == stable_id(b)
    assert stable_id(a).startswith("ca_") and len(stable_id(a)) == 27
    assert resource_kind("https://academy.claude.com/use-cases/account-tracking") == "use-case"
    assert resource_kind("https://academy.claude.com/collections/k-12") == "collection"
    lesson = "https://academy.claude.com/courses/claude-code-101/hooks"
    assert official_url(lesson) == lesson
    assert source_url("https://academy.claude.com/sitemap.xml").endswith("/sitemap.xml")


def test_artwork_must_be_the_pages_own_share_image():
    page = "https://academy.claude.com/courses/claude-code-101"
    image = "https://academy.claude.com/og/courses/claude-code-101.png"
    assert artwork_url(image, page) == image
    for bad in [
        "https://academy.claude.com/og/site.png",
        "https://academy.claude.com/og/courses/claude-101.png",
        "https://academy.claude.com/og/tutorials/claude-code-101.png",
        "https://academy.claude.com/og/courses/claude-code-101.png?v=2",
        "https://cdn.example.com/og/courses/claude-code-101.png",
        "https://academy.claude.com/og/courses/claude-code-101.svg",
    ]:
        with pytest.raises(ValueError):
            artwork_url(bad, page)


def test_media_and_mismatched_records_are_rejected(artifact):
    first = artifact["resources"][0]
    for change in [
        {
            "media": [
                {
                    "kind": "video",
                    "url": first["url"],
                    "permission": "permitted",
                    "permissionEvidenceUrl": first["url"],
                }
            ]
        },
        {"kind": "tutorial"},
        {"url": "https://academy.claude.com/courses/claude-code-101/hooks"},
        {
            "artwork": {
                "url": "https://academy.claude.com/og/courses/another-course.png",
                "alt": None,
                "sourceUrl": first["url"],
            }
        },
        {"courseBody": "Course text must never pass through."},
    ]:
        candidate = json.loads(json.dumps(artifact))
        candidate["resources"][0].update(change)
        with pytest.raises(ValidationError):
            CollectionArtifact.model_validate_json(json.dumps(candidate))
