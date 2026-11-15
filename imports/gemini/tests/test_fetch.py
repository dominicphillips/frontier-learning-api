from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest
from conftest import ORIGIN, Response, SiteOpener

from gemini_academy_api.fetch import (
    DEFAULT_USER_AGENT,
    USER_AGENT,
    BudgetExhausted,
    Fetcher,
    FetchError,
    RobotsDisallowed,
    user_agent_from_environment,
    validate_user_agent,
)


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []
        self.starts: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Timed(SiteOpener):
    def __init__(self, clock: Clock, **kwargs):
        super().__init__(**kwargs)
        self.clock = clock

    def open(self, request, timeout):
        self.clock.starts.append(self.clock.now)
        self.clock.now += 0.2  # Each response takes a little time.
        return super().open(request, timeout)


def fetcher(opener, clock=None, **kwargs) -> Fetcher:
    clock = clock or Clock()
    return Fetcher(opener=opener, clock=clock, sleep=clock.sleep, **kwargs)


def test_requests_are_sequential_at_least_one_second_apart():
    clock = Clock()
    site = Timed(clock)
    client = fetcher(site, clock)
    client.load_robots()
    for path in ("/catalog?page=1", "/paths/3666", "/course_templates/1401"):
        client.get(ORIGIN + path)
    gaps = [b - a for a, b in zip(clock.starts, clock.starts[1:], strict=False)]
    assert len(gaps) == 3 and all(gap >= 1.1 - 1e-9 for gap in gaps)
    assert [r.status for r in client.receipts] == [200, 200, 200, 200]
    assert all(r.sha256 and r.bytes for r in client.receipts)
    assert USER_AGENT == DEFAULT_USER_AGENT == "gemini-academy-api/0.1.0"
    assert "http" not in USER_AGENT and "@" not in USER_AGENT
    with pytest.raises(ValueError):
        Fetcher(interval=0.5)


def test_user_agent_env_override_and_validation(monkeypatch):
    assert user_agent_from_environment({}) == DEFAULT_USER_AGENT
    assert user_agent_from_environment({"GEMINI_ACADEMY_USER_AGENT": ""}) == DEFAULT_USER_AGENT
    monkeypatch.setenv("GEMINI_ACADEMY_USER_AGENT", "gemini-academy-api/0.1.0 custom")
    client = Fetcher()
    assert client.user_agent == "gemini-academy-api/0.1.0 custom"

    for bad in ["   ", "x" * 201, "bad\nline", "non-ascii-\u00e9", "tab\there"]:
        with pytest.raises(ValueError):
            validate_user_agent(bad)
        with pytest.raises(ValueError):
            Fetcher(user_agent=bad)


def test_robots_is_read_first_and_disallowed_or_lab_pages_are_never_requested():
    site = SiteOpener(robots="User-agent: *\nDisallow: /paths/\n")
    client = fetcher(site)
    with pytest.raises(FetchError):
        client.get(ORIGIN + "/course_templates/1401")
    assert site.calls == []
    client.load_robots()
    with pytest.raises(RobotsDisallowed):
        client.get(ORIGIN + "/paths/3666")
    with pytest.raises(ValueError):
        client.get("https://cdn.qwiklabs.com/page")
    with pytest.raises(ValueError):
        client.get(ORIGIN + "/api/courses")
    with pytest.raises(ValueError):
        client.get(ORIGIN + "/focuses/104012?parent=catalog")
    with pytest.raises(ValueError):
        client.get(ORIGIN + "/course_templates/1401/documents/686074")
    assert site.calls == [ORIGIN + "/robots.txt"]


class Flaky(SiteOpener):
    def __init__(self, statuses, headers=None):
        super().__init__()
        self.statuses, self.headers = list(statuses), headers or {}

    def open(self, request, timeout):
        if request.full_url.endswith("/robots.txt"):
            return super().open(request, timeout)
        self.calls.append(request.full_url)
        status = self.statuses.pop(0)
        if status == "timeout":
            raise TimeoutError()
        if status != 200:
            raise urllib.error.HTTPError(
                request.full_url, status, "x", self.headers, io.BytesIO(b"")
            )
        return Response(b"<html></html>")


def test_transient_failures_retry_with_bounded_backoff():
    clock = Clock()
    site = Flaky([503, "timeout", 200], headers={"Retry-After": "7"})
    client = fetcher(site, clock)
    client.load_robots()
    assert client.get(ORIGIN + "/course_templates/1401").body == b"<html></html>"
    assert 7 in clock.sleeps
    assert [r.status for r in client.receipts] == [200, 503, None, 200]
    assert client.receipts[1].error == "HTTP 503" and client.receipts[2].error == "TimeoutError"


def test_permanent_failures_redirects_size_and_budget():
    site = Flaky([404, 302])
    client = fetcher(site)
    client.load_robots()
    with pytest.raises(FetchError, match="404"):
        client.get(ORIGIN + "/course_templates/1401")
    with pytest.raises(FetchError, match="302"):
        client.get(ORIGIN + "/course_templates/1402")
    assert site.calls == [
        ORIGIN + "/robots.txt",
        ORIGIN + "/course_templates/1401",
        ORIGIN + "/course_templates/1402",
    ]

    big = SiteOpener(pages={ORIGIN + "/course_templates/1401": "x" * 2048})
    client = fetcher(big, max_bytes=1024, retries=0)
    client.load_robots()
    with pytest.raises(FetchError, match="size limit"):
        client.get(ORIGIN + "/course_templates/1401")

    client = fetcher(SiteOpener(), max_requests=2)
    client.load_robots()
    client.get(ORIGIN + "/catalog?page=1")
    with pytest.raises(BudgetExhausted):
        client.get(ORIGIN + "/course_templates/1401")


def test_default_transport_never_follows_redirects_or_ambient_proxies(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    client = Fetcher()
    handlers = client._opener.handlers
    assert not [h for h in handlers if isinstance(h, urllib.request.ProxyHandler) and h.proxies]
    redirect = next(h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
    request = urllib.request.Request(ORIGIN + "/course_templates/1401")
    assert redirect.redirect_request(request, None, 302, "Found", {}, "https://x.test/") is None


def test_a_redirect_means_the_page_is_not_public():
    from gemini_academy_api.fetch import NotPublic

    site = Flaky([302], headers={"Location": "https://www.skills.google/"})
    client = fetcher(site)
    client.load_robots()
    with pytest.raises(NotPublic, match="not public"):
        client.get(ORIGIN + "/course_templates/1191")
    assert client.receipts[-1].error == "HTTP 302 to https://www.skills.google/"
