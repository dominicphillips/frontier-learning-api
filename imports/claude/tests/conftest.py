from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ORIGIN = "https://academy.claude.com"


def fixture_page(url: str) -> str:
    name = url.removeprefix(ORIGIN + "/").replace("/", "__") + ".html"
    return (FIXTURES / "pages" / name).read_text()


@pytest.fixture
def artifact():
    timestamp = datetime.now(UTC) - timedelta(seconds=2)
    generated = timestamp.isoformat()
    categories = [
        {"id": "build-with-claude", "label": "Build with Claude"},
        {"id": "ai-fluency", "label": "AI Fluency"},
        {"id": "claude-for-work", "label": "Claude for work"},
    ]
    resources = []
    for title, path, kind, category, minutes in [
        ("Claude Code 101", "courses/claude-code-101", "course", "build-with-claude", 81),
        ("The 4 Properties of AI", "tutorials/the-4-properties-of-ai", "tutorial", "ai-fluency", 7),
        ("Account research", "use-cases/account-research-brief", "use-case", "claude-for-work", 10),
    ]:
        url = f"{ORIGIN}/{path}"
        resources.append(
            {
                "title": title,
                "url": url,
                "kind": kind,
                "categoryIds": [category],
                "audiences": [],
                "tags": ["Claude Code"] if kind == "course" else [],
                "summary": None,
                "level": None,
                "duration": {"courseMinutes": minutes, "pathMinutes": None, "videoSeconds": None},
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
            {"categoryId": c["id"], "state": "complete", "discovered": 1, "collected": 1}
            for c in categories
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
        assert request.get_header("User-agent").startswith("claude-academy-api/")
        if url == ORIGIN + "/robots.txt":
            return Response(self.robots.encode())
        if url == ORIGIN + "/sitemap.xml" and url not in self.pages:
            return Response((FIXTURES / "sitemap.xml").read_bytes())
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
def no_deployment_purge(monkeypatch):
    # Tests never read a real deployment token or call Cloudflare.
    for name in (
        "CLAUDE_ACADEMY_CLOUDFLARE_ZONE_ID",
        "CLAUDE_ACADEMY_CLOUDFLARE_HOSTNAME",
        "CLAUDE_ACADEMY_CLOUDFLARE_PURGE_TOKEN_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
