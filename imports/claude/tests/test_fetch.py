from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest
from conftest import ORIGIN, Response, SiteOpener

from claude_academy_api.fetch import (
    USER_AGENT,
    BudgetExhausted,
    Fetcher,
    FetchError,
    RobotsDisallowed,
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
    for path in ("/sitemap.xml", "/courses/claude-code-101", "/use-cases/account-research-brief"):
        client.get(ORIGIN + path)
    gaps = [b - a for a, b in zip(clock.starts, clock.starts[1:], strict=False)]
    assert len(gaps) == 3 and all(gap >= 1.1 - 1e-9 for gap in gaps)
    assert [r.status for r in client.receipts] == [200, 200, 200, 200]
    assert all(r.sha256 and r.bytes for r in client.receipts)
    assert USER_AGENT.startswith("claude-academy-api/0.1.0 (+https://github.com/")
    with pytest.raises(ValueError):
        Fetcher(interval=0.5)


def test_robots_is_read_first_and_disallowed_pages_are_never_requested():
    site = SiteOpener(robots="User-agent: *\nDisallow: /tutorials/\n")
    client = fetcher(site)
    with pytest.raises(FetchError):
        client.get(ORIGIN + "/courses/claude-code-101")
    assert site.calls == []
    client.load_robots()
    with pytest.raises(RobotsDisallowed):
        client.get(ORIGIN + "/tutorials/choosing-the-right-claude-model")
    with pytest.raises(ValueError):
        client.get("https://anthropic.skilljar.com/page")
    with pytest.raises(ValueError):
        client.get(ORIGIN + "/api/courses")
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
    assert client.get(ORIGIN + "/courses/a").body == b"<html></html>"
    assert 7 in clock.sleeps
    assert [r.status for r in client.receipts] == [200, 503, None, 200]
    assert client.receipts[1].error == "HTTP 503" and client.receipts[2].error == "TimeoutError"


def test_permanent_failures_redirects_size_and_budget():
    site = Flaky([404, 301])
    client = fetcher(site)
    client.load_robots()
    with pytest.raises(FetchError, match="404"):
        client.get(ORIGIN + "/courses/a")
    with pytest.raises(FetchError, match="301"):
        client.get(ORIGIN + "/courses/b")
    assert site.calls == [ORIGIN + "/robots.txt", ORIGIN + "/courses/a", ORIGIN + "/courses/b"]

    big = SiteOpener(pages={ORIGIN + "/courses/big": "x" * 2048})
    client = fetcher(big, max_bytes=1024, retries=0)
    client.load_robots()
    with pytest.raises(FetchError, match="size limit"):
        client.get(ORIGIN + "/courses/big")

    client = fetcher(SiteOpener(), max_requests=2)
    client.load_robots()
    client.get(ORIGIN + "/sitemap.xml")
    with pytest.raises(BudgetExhausted):
        client.get(ORIGIN + "/courses/claude-code-101")


def test_default_transport_never_follows_redirects_or_ambient_proxies(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    client = Fetcher()
    handlers = client._opener.handlers
    assert not [h for h in handlers if isinstance(h, urllib.request.ProxyHandler) and h.proxies]
    redirect = next(h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
    request = urllib.request.Request(ORIGIN + "/courses/a")
    assert redirect.redirect_request(request, None, 302, "Found", {}, "https://x.test/") is None
