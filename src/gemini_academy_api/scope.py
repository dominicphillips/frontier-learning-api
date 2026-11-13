"""Deterministic scope rules for Gemini learning material on Google Skills."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

from .security import ACADEMY_ORIGIN, resource_kind, resource_url

GEMINI_RE = re.compile(r"\bgemini\b", re.IGNORECASE)
DEPRECATED_RE = re.compile(r"^\s*\[deprecated\]", re.IGNORECASE)


def is_deprecated(title: str | None) -> bool:
    """Return True when a resource title starts with [DEPRECATED] (case-insensitive)."""
    return bool(title and DEPRECATED_RE.match(title))


def matches_gemini(*texts: str | None) -> bool:
    """Return True when any text contains the standalone word 'gemini' (case-insensitive)."""
    return any(bool(text and GEMINI_RE.search(text)) for text in texts)


def in_text_scope(title: str | None, description: str | None = None) -> bool:
    """Rule 1 scope check from listing title and description, excluding deprecated entries."""
    return not is_deprecated(title) and matches_gemini(title, description)


def in_scope(
    title: str | None,
    description: str | None = None,
    *,
    is_path_member: bool = False,
) -> bool:
    """Full scope check: rule 1 (word 'gemini') or rule 2 (member of an in-scope path)."""
    if is_deprecated(title):
        return False
    return bool(is_path_member or matches_gemini(title, description))


def dry_check_catalog(raw_entries: list[dict]) -> dict:
    """Deduplicate raw catalog objects by canonical URL and count in-scope items by kind."""
    seen: dict[str, dict] = {}
    for entry in raw_entries:
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        try:
            url = resource_url(urljoin(ACADEMY_ORIGIN, raw_path))
        except ValueError:
            continue
        seen.setdefault(url, entry)

    counts: Counter[str] = Counter()
    for url, entry in seen.items():
        if in_text_scope(entry.get("title"), entry.get("description")):
            counts[resource_kind(url)] += 1

    return {
        "totalRows": len(raw_entries),
        "distinctResources": len(seen),
        "inScopeTotal": sum(counts.values()),
        "byKind": dict(sorted(counts.items())),
    }


if __name__ == "__main__":
    catalog_path = Path("output/research/full/catalog-full.json")
    if not catalog_path.exists():
        print(json.dumps({"present": False, "path": str(catalog_path)}, indent=2))
    else:
        data = json.loads(catalog_path.read_text())
        print(json.dumps({"present": True, **dry_check_catalog(data)}, indent=2))
