from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from gemini_academy_api.models import CollectionArtifact
from gemini_academy_api.security import (
    artwork_url,
    fetchable_url,
    official_url,
    resource_kind,
    resource_slug,
    resource_url,
    source_url,
    stable_id,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.skills.google/course_templates/1401",
        "https://skills.google/course_templates/1401",
        "https://www.skills.google.evil.example/course_templates/1401",
        "https://www.skills.google@evil.example/course_templates/1401",
        "https://user:secret@www.skills.google/course_templates/1401",
        "https://cdn.qwiklabs.com/course_templates/1401",
        "https://127.0.0.1/course_templates/1401",
        "https://[::1]/course_templates/1401",
        "https://www.skills.google:444/course_templates/1401",
        "https://www.skills.google/course_templates/%2e%2e/users/sign_in",
        "https://www.skills.google/course_templates/%252e%252e/api/v1",
        "https://www.skills.google/course_templates/1401\\b",
        "https://www.skills.google/course_templates/1401%0d%0aHost:evil",
        "https://www.skills.google/course_templates/abc",
        "https://www.skills.google/course_templates",
        "https://www.skills.google/course_templates/1401/documents/686074",
        "https://www.skills.google/paths/3666/course_templates/1401",
        "https://www.skills.google/api/catalog",
        "https://www.skills.google/focuses/104012/start",
        "https://www.skills.google/focuses/104012/resume",
        "https://www.skills.google/focuses/104012/stop",
        "https://www.skills.google/users/sign_in",
        "https://www.skills.google/my_account/profile",
        "https://www.skills.google/profile/u/1",
    ],
)
def test_only_public_resource_pages_are_resources(url):
    with pytest.raises(ValueError):
        resource_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.skills.google/api/v1/catalog",
        "https://www.skills.google/api",
        "https://www.skills.google/focuses/104012/start",
        "https://www.skills.google/focuses/104012/resume",
        "https://www.skills.google/focuses/104012/stop",
        "https://www.skills.google/users/sign_in",
        "https://www.skills.google/my_account/badges",
        "https://www.skills.google/profile/abc",
        "https://www.skills.google/catalog?q=gemini",
        "https://www.skills.google/catalog?page=0",
        "https://www.skills.google/catalog?page=1&sort=new",
        "https://www.skills.google/robots.txt?v=1",
        "https://www.skills.google/course_templates/1401/unknown/123",
    ],
)
def test_excluded_and_invalid_paths_are_never_sources(url):
    with pytest.raises(ValueError):
        source_url(url)


def test_canonical_urls_kinds_units_and_stable_ids():
    course = "https://www.skills.google/course_templates/1401"
    dirty_course = "https://www.skills.google/course_templates/1401/?catalog_rank=1#outline"
    assert resource_url(dirty_course) == course
    assert stable_id(course) == stable_id(dirty_course)
    assert stable_id(course).startswith("ga_") and len(stable_id(course)) == 27
    assert resource_kind(course) == "course"
    assert resource_slug(course) == "1401"

    path = "https://www.skills.google/paths/3666"
    assert resource_url(path + "?catalog_rank=3") == path
    assert resource_kind(path) == "learning-path"
    assert resource_slug(path) == "3666"

    lab_canonical = "https://www.skills.google/focuses/104012?parent=catalog"
    assert resource_url("https://www.skills.google/focuses/104012") == lab_canonical
    assert (
        resource_url("https://www.skills.google/focuses/104012?catalog_rank=2&path=3666")
        == lab_canonical
    )
    assert resource_kind(lab_canonical) == "lab"
    assert stable_id(lab_canonical) == stable_id("https://www.skills.google/focuses/104012")

    for segment in ("documents", "quizzes", "labs", "video", "html_bundles"):
        unit = f"https://www.skills.google/course_templates/1401/{segment}/686074"
        assert official_url(unit) == unit
        assert source_url(unit) == unit
        with pytest.raises(ValueError):
            fetchable_url(unit)

    with pytest.raises(ValueError):
        fetchable_url(lab_canonical)
    assert fetchable_url(course) == course
    assert fetchable_url(path) == path
    assert (
        fetchable_url("https://www.skills.google/catalog?page=2")
        == "https://www.skills.google/catalog?page=2"
    )
    assert source_url("https://www.skills.google/robots.txt").endswith("/robots.txt")


def test_artwork_is_rejected():
    with pytest.raises(ValueError):
        artwork_url("https://www.skills.google/super_G_optimized.png")


def test_media_non_null_artwork_and_mismatched_records_are_rejected(artifact):
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
        {"kind": "lab"},
        {"url": "https://www.skills.google/course_templates/1401/documents/686074"},
        {
            "artwork": {
                "url": "https://www.skills.google/og/courses/1401.png",
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
