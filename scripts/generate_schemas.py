import json
from pathlib import Path

from frontier_learning.app import create_app
from frontier_learning.catalog import providers

ROOT = Path(__file__).resolve().parent.parent


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    spec = create_app("/nonexistent").openapi()
    write(ROOT / "schema/openapi.json", spec)
    for name, provider in providers(Path("/nonexistent")).items():
        for kind, model in [
            ("resource", provider.models.Resource),
            ("snapshot", provider.models.Snapshot),
            ("collection", provider.models.CollectionArtifact),
        ]:
            write(
                ROOT / f"schema/{name}/{kind}.schema.json", model.model_json_schema(by_alias=True)
            )
        write(
            ROOT / f"schema/{name}/openapi.json",
            spec
            | {
                "paths": {
                    path: value
                    for path, value in spec["paths"].items()
                    if path.startswith(f"/v1/providers/{name}/")
                }
            },
        )
