from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ORIGIN = "https://www.skills.google"


def fixture_page(url: str) -> str:
    rel = url.removeprefix(ORIGIN + "/")
    if rel.startswith("catalog?page="):
        page = rel.removeprefix("catalog?page=")
        name = f"catalog__page-{page}.html"
    else:
        name = rel.split("?", 1)[0].replace("/", "__") + ".html"
    return (FIXTURES / "pages" / name).read_text()


@pytest.fixture
def artifact():
    timestamp = datetime.now(UTC) - timedelta(seconds=2)
    generated = timestamp.isoformat()
    categories = [
        {
            "id": "gemini-enterprise-and-gemini-notebook-3666",
            "label": "Gemini Enterprise and Gemini Notebook",
        },
        {"id": "gemini-in-bigquery-1803", "label": "Gemini in BigQuery"},
    ]
    resources = []
    for title, path, kind, category, course_minutes, path_minutes, level, tags in [
        (
            "Introduction to Gemini Enterprise",
            "course_templates/1401",
            "course",
            "gemini-enterprise-and-gemini-notebook-3666",
            135,
            None,
            "beginner",
            [],
        ),
        (
            "Gemini Enterprise and Gemini Notebook",
            "paths/3666",
            "learning-path",
            "gemini-enterprise-and-gemini-notebook-3666",
            None,
            1004,
            None,
            [],
        ),
        (
            "Intro to Context Caching with the Gemini API",
            "focuses/104701?parent=catalog",
            "lab",
            "gemini-in-bigquery-1803",
            45,
            None,
            "intermediate",
            ["Skill badge"],
        ),
    ]:
        url = f"{ORIGIN}/{path}"
        resources.append(
            {
                "title": title,
                "url": url,
                "kind": kind,
                "categoryIds": [category],
                "audiences": [],
                "tags": tags,
                "summary": None,
                "level": level,
                "duration": {
                    "courseMinutes": course_minutes,
                    "pathMinutes": path_minutes,
                    "videoSeconds": None,
                },
                "detail": {"audience": None, "prerequisites": [], "objectives": [], "sections": []},
                "media": [],
                "artwork": None,
                "provenance": {"sourceUrls": [url], "fetchedAt": generated},
            }
        )
    return {
        "schemaVersion": 1,
        "generatedAt": generated,
        "categories": categories,
        "resources": resources,
        "coverage": [
            {
                "categoryId": "gemini-enterprise-and-gemini-notebook-3666",
                "state": "complete",
                "discovered": 2,
                "collected": 2,
            },
            {
                "categoryId": "gemini-in-bigquery-1803",
                "state": "complete",
                "discovered": 1,
                "collected": 1,
            },
        ],
        "fetchReport": {"requests": 4, "robotsChecked": True, "completedWithinLimits": True},
    }


@pytest.fixture
def write_artifact(tmp_path):
    def write(value: dict, name="artifact.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return path

    return write


class Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status


class SiteOpener:
    """Serves saved fixtures by URL; unknown pages return 404. Records every request."""

    def __init__(self, pages: dict[str, str | int] | None = None, robots: str | None = None):
        self.pages = pages or {}
        self.robots = robots if robots is not None else (FIXTURES / "robots.txt").read_text()
        self.calls: list[str] = []

    def open(self, request, timeout):
        url = request.full_url
        self.calls.append(url)
        assert request.get_method() == "GET"
        assert request.get_header("Accept-language") == "en"
        assert request.get_header("User-agent").startswith("gemini-academy-api/")
        if url == ORIGIN + "/robots.txt":
            return Response(self.robots.encode())
        value = self.pages.get(url)
        if value is None:
            try:
                value = fixture_page(url)
            except FileNotFoundError:
                value = 404
        if isinstance(value, int):
            raise urllib.error.HTTPError(url, value, "error", {}, io.BytesIO(b""))  # type: ignore[arg-type]
        return Response(value.encode())


@pytest.fixture
def site():
    return SiteOpener


@pytest.fixture(autouse=True)
def no_deployment_env(monkeypatch):
    # Tests never read a real deployment token, User-Agent override, or call Cloudflare.
    for name in (
        "GEMINI_ACADEMY_USER_AGENT",
        "GEMINI_ACADEMY_CLOUDFLARE_ZONE_ID",
        "GEMINI_ACADEMY_CLOUDFLARE_HOSTNAME",
        "GEMINI_ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
