"""Polite, robots-checked GET requests to the public Claude Academy site."""

from __future__ import annotations

import hashlib
import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from . import __version__
from .robots import Robots
from .security import ACADEMY_ORIGIN, source_url

PRODUCT = "claude-academy-api"
USER_AGENT = f"{PRODUCT}/{__version__} (+https://github.com/dominicphillips/claude-academy-api)"
ROBOTS_URL = ACADEMY_ORIGIN + "/robots.txt"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    pass


class RobotsDisallowed(FetchError):
    pass


class BudgetExhausted(FetchError):
    pass


@dataclass
class Receipt:
    url: str
    status: int | None
    bytes: int
    sha256: str | None
    fetchedAt: str
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Page:
    url: str
    body: bytes
    fetched_at: datetime

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # A redirect is reported as a failed page, never followed off the policy.


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


class Fetcher:
    """One request at a time, at least `interval` seconds apart, GET only, bounded size."""

    def __init__(
        self,
        *,
        interval: float = 1.1,
        max_requests: int = 1000,
        max_bytes: int = 5 * 1024 * 1024,
        timeout: float = 30,
        retries: int = 2,
        opener=None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if interval < 1.0:
            raise ValueError("Requests must be at least one second apart")
        self.interval, self.max_requests, self.max_bytes = interval, max_requests, max_bytes
        self.timeout, self.retries = timeout, retries
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )
        self._clock, self._sleep, self._now = clock, sleep, now
        self._last: float | None = None
        self.receipts: list[Receipt] = []
        self.robots: Robots | None = None

    @property
    def requests(self) -> int:
        return len(self.receipts)

    def load_robots(self) -> Robots:
        page = self._get(ROBOTS_URL)
        self.robots = Robots(page.text())
        return self.robots

    def allowed(self, url: str) -> bool:
        if self.robots is None:
            raise FetchError("robots.txt must be read before any other request")
        return self.robots.allowed(url, PRODUCT)

    def get(self, url: str) -> Page:
        url = source_url(url)
        if url == ROBOTS_URL:
            return self._get(url)
        if not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        return self._get(url)

    def _wait(self) -> None:
        if self._last is not None:
            remaining = self.interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()

    def _get(self, url: str) -> Page:
        attempt = 0
        while True:
            if self.requests >= self.max_requests:
                raise BudgetExhausted(f"Request budget of {self.max_requests} is exhausted")
            self._wait()
            fetched_at = self._now()
            stamp = fetched_at.isoformat().replace("+00:00", "Z")
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xml;q=0.9,text/plain;q=0.8",
                    "Accept-Encoding": "identity",
                },
                method="GET",
            )
            status, body, error, delay = None, b"", None, None
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    status = response.status
                    body = response.read(self.max_bytes + 1)
            except urllib.error.HTTPError as exc:
                status, error = exc.code, f"HTTP {exc.code}"
                delay = _retry_after(exc.headers.get("Retry-After") if exc.headers else None)
            except (OSError, http.client.HTTPException, ValueError) as exc:
                error = type(exc).__name__
            if status == 200 and len(body) > self.max_bytes:
                status, body, error = None, b"", "Response exceeds the size limit"
            ok = status == 200 and error is None
            self.receipts.append(
                Receipt(
                    url=url,
                    status=status,
                    bytes=len(body) if ok else 0,
                    sha256=hashlib.sha256(body).hexdigest() if ok else None,
                    fetchedAt=stamp,
                    error=error if not ok else None,
                )
            )
            if ok:
                return Page(url=url, body=body, fetched_at=fetched_at)
            retryable = status in RETRY_STATUSES or status is None
            if not retryable or attempt >= self.retries:
                raise FetchError(f"{url}: {error or f'HTTP {status}'}")
            attempt += 1
            backoff = min(60.0, delay if delay is not None else 5.0 * attempt)
            self._sleep(backoff)
