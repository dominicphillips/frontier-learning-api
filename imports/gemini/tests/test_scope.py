from __future__ import annotations

import json
from pathlib import Path

import pytest

from gemini_academy_api.scope import dry_check_catalog, in_scope, in_text_scope, is_deprecated


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("Gemini in Gmail", None, True),
        ("Build with GEMINI 2.5", "", True),
        ("AI Overview", "Explore how gemini powers Google Workspace.", True),
        ("Geminis in the sky", "Plural word must not match word boundary.", False),
        ("Subgemini tools", None, False),
        ("BigQuery ML Basics", "Train tabular models with SQL.", False),
        ("[DEPRECATED] Gemini Code Assist", "Still mentions Gemini", False),
        ("  [deprecated] Gemini in Docs", None, False),
    ],
)
def test_text_scope_word_boundary_and_deprecated_exclusion(title, description, expected):
    assert in_text_scope(title, description) is expected


def test_path_membership_scope_includes_non_gemini_members_unless_deprecated():
    assert in_scope("Conversational Insights", "No mention of target keyword", is_path_member=True)
    assert not in_scope(
        "[DEPRECATED] Streamline App Development with Gemini Code Assist",
        "Contains Gemini",
        is_path_member=True,
    )
    assert is_deprecated("  [DEPRECATED] Old course")
    assert not is_deprecated("Course [DEPRECATED] mid-title")


def test_offline_dry_check_against_saved_catalog_if_present():
    path = Path("output/research/full/catalog-full.json")
    if not path.exists():
        pytest.skip("Optional research catalog snapshot not present")
    data = json.loads(path.read_text())
    report = dry_check_catalog(data)
    assert report["totalRows"] == 1315
    assert report["distinctResources"] == 1312
    assert report["inScopeTotal"] == 262
    assert report["byKind"] == {"course": 181, "lab": 58, "learning-path": 23}
