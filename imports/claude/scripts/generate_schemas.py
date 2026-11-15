"""Regenerate the committed JSON Schema and OpenAPI files from the code."""

from __future__ import annotations

import json
from pathlib import Path

from claude_academy_api.app import create_app
from claude_academy_api.models import CollectionArtifact, Resource, Snapshot

ROOT = Path(__file__).resolve().parent.parent


def write(name: str, value: dict) -> None:
    (ROOT / "schema" / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    for name, model in [
        ("resource", Resource),
        ("snapshot", Snapshot),
        ("collection", CollectionArtifact),
    ]:
        write(f"{name}.schema.json", model.model_json_schema(by_alias=True))
    write("openapi.json", create_app("/nonexistent/snapshot.json").openapi())
