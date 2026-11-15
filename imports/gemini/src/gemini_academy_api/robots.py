"""A small RFC 9309 robots.txt matcher: longest match wins, allow wins ties, `*` and `$`."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)


def _pattern(path: str) -> re.Pattern[str]:
    anchored = path.endswith("$")
    body = path[:-1] if anchored else path
    expression = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(expression + ("$" if anchored else ""))


class Robots:
    def __init__(self, text: str):
        self.groups: list[_Group] = []
        self.sitemaps: list[str] = []
        current: _Group | None = None
        in_agents = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or not in_agents:
                    current = _Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                in_agents = True
            elif key in {"allow", "disallow"}:
                in_agents = False
                if current is not None and value:
                    current.rules.append((key == "allow", value))
            elif key == "sitemap":
                self.sitemaps.append(value)

    def _rules(self, product: str) -> list[tuple[bool, str]]:
        product = product.lower()
        named = [g for g in self.groups if product in g.agents]
        chosen = named or [g for g in self.groups if "*" in g.agents]
        return [rule for group in chosen for rule in group.rules]

    def allowed(self, url: str, product: str) -> bool:
        parts = urlsplit(url)
        target = unquote(parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: tuple[int, bool] | None = None
        for allow, path in self._rules(product):
            if _pattern(unquote(path)).match(target):
                candidate = (len(path), allow)
                if best is None or candidate > best:
                    best = candidate
        return True if best is None else best[1]
