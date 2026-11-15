import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frontier_learning.app import create_app
from frontier_learning.catalog import providers
from frontier_learning.storage import atomic_json

from .claude.conftest import artifact as claude_artifact
from .gemini.conftest import artifact as gemini_artifact
from .openai.conftest import artifact as openai_artifact


@pytest.fixture
def api(tmp_path):
    specs = providers(tmp_path)
    for name, factory in [
        ("openai", openai_artifact),
        ("claude", claude_artifact),
        ("gemini", gemini_artifact),
    ]:
        artifact = specs[name].models.CollectionArtifact.model_validate_json(
            json.dumps(factory.__wrapped__())
        )
        snapshot = specs[name].models.build_snapshot(artifact, "fixture")
        atomic_json(tmp_path / f"{name}.json", snapshot.model_dump(mode="json", by_alias=True))
    app = create_app(tmp_path)
    with TestClient(app) as client:
        yield client, app, tmp_path


def test_aggregate_projection_preserves_source_metadata(api):
    client, _, _ = api
    combined = client.get("/v1/resources?limit=100").json()
    assert {r["provider"] for r in combined["items"]} == {"openai", "claude", "gemini"}
    source_total = 0
    for provider in ["openai", "claude", "gemini"]:
        scoped = client.get(f"/v1/providers/{provider}/resources?limit=100").json()
        source_total += scoped["total"]
        filtered = client.get(f"/v1/resources?provider={provider}&limit=100").json()
        assert filtered["total"] == scoped["total"]
        projected = {r["id"]: r for r in filtered["items"]}
        for resource in scoped["items"]:
            expected = resource | {
                "provider": provider,
                "categoryIds": [f"{provider}:{c}" for c in resource["categoryIds"]],
            }
            assert projected[resource["id"]] == expected
            assert client.get(f"/v1/resources/{resource['id']}").json() == expected
        assert client.get(f"/v1/providers/{provider}/resources?limit=100").json() == scoped
    assert combined["total"] == source_total
    assert client.get("/v1/status").json()["resourceCount"] == source_total
    assert len(client.get("/v1/providers").json()["items"]) == 3


def test_category_namespaces_and_filters(api):
    client, _, _ = api
    categories = client.get("/v1/categories").json()["items"]
    assert len({x["id"] for x in categories}) == len(categories)
    for category in categories:
        assert category["id"] == f"{category['provider']}:{category['slug']}"
        page = client.get("/v1/resources", params={"category": category["id"]}).json()
        assert page["total"] == category["count"]
        assert all(r["provider"] == category["provider"] for r in page["items"])
    assert client.get("/v1/resources?category=plain-slug").status_code == 422


def test_pagination_and_cursor_scope(api):
    client, _, _ = api
    first = client.get("/v1/resources?limit=1").json()
    assert first["nextCursor"]
    seen, page = [], first
    while True:
        seen.extend(item["id"] for item in page["items"])
        if not page["nextCursor"]:
            break
        page = client.get("/v1/resources", params={"limit": 2, "cursor": page["nextCursor"]}).json()
    assert len(seen) == len(set(seen)) == first["total"]
    assert seen == sorted(seen, key=lambda value: (value[3:], value))
    mismatch = client.get(
        "/v1/resources", params={"provider": "openai", "cursor": first["nextCursor"]}
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"]["code"] == "cursor-filter-mismatch"
    scoped = client.get("/v1/providers/openai/resources?limit=1").json()
    assert scoped["nextCursor"]
    cross = client.get("/v1/resources", params={"cursor": scoped["nextCursor"]})
    assert cross.status_code == 409
    invalid = base64.urlsafe_b64encode(b"{}").decode().rstrip("=")
    assert client.get("/v1/resources", params={"cursor": invalid}).status_code == 400


def test_snapshot_changes_reject_old_cursor(api):
    client, app, path = api
    before = client.get("/v1/resources?limit=1").json()
    provider = app.state.providers["openai"]
    snapshot = provider.store.read()
    replacement = provider.models.assemble_snapshot(
        generated_at=datetime.now(UTC) + timedelta(seconds=1),
        categories=snapshot.categories,
        resources=snapshot.resources,
        coverage=snapshot.coverage,
    )
    atomic_json(path / "openai.json", replacement.model_dump(mode="json", by_alias=True))
    response = client.get("/v1/resources", params={"cursor": before["nextCursor"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snapshot-changed"


def test_partial_source_failure_isolated_and_not_cached(api):
    client, _, path = api
    resource_id = client.get("/v1/providers/openai/resources").json()["items"][0]["id"]
    (path / "gemini.json").unlink()
    with TestClient(create_app(path)) as fresh:
        for endpoint in ["/v1/resources", "/v1/categories", "/health/ready"]:
            response = fresh.get(endpoint)
            assert response.status_code == 503
            assert response.headers["cache-control"] == "no-store"
        for endpoint in ["/v1/status", "/v1/providers", "/v1/providers/gemini/status"]:
            response = fresh.get(endpoint)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
        assert fresh.get("/v1/providers/openai/resources").status_code == 200
        assert fresh.get(f"/v1/resources/{resource_id}").status_code == 200
        assert fresh.get("/v1/providers/openai/health/ready").status_code == 200
        assert fresh.get("/v1/providers/gemini/health/ready").status_code == 503


@pytest.mark.parametrize(
    "provider,bad_kind", [("openai", "lab"), ("claude", "lab"), ("gemini", "tutorial")]
)
def test_provider_kind_validation_stays_specific(api, provider, bad_kind):
    client, _, _ = api
    response = client.get(f"/v1/providers/{provider}/resources", params={"kind": bad_kind})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/v1/resources", params={"kind": bad_kind}).status_code == 200


def test_cache_errors_and_cors(api):
    client, _, _ = api
    for endpoint in [
        "/v1/resources",
        "/v1/categories",
        "/v1/status",
        "/v1/providers",
        "/v1/providers/claude/resources",
    ]:
        response = client.get(endpoint)
        etag = response.headers["etag"]
        assert etag.startswith('W/"')
        for value in [etag, etag.removeprefix("W/"), f'"unrelated", {etag}', "*"]:
            unchanged = client.get(endpoint, headers={"If-None-Match": value})
            assert unchanged.status_code == 304 and unchanged.content == b""
            assert unchanged.headers["etag"] == etag
        assert response.headers["access-control-allow-origin"] == "*"
    for endpoint, status in [
        ("/v1/resources/no-such-id", 404),
        ("/v1/resources?limit=101", 422),
        ("/v1/resources?cursor=bad!", 400),
    ]:
        response = client.get(endpoint)
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"
        assert "etag" not in response.headers
    options = client.options(
        "/v1/resources",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
    )
    assert options.status_code == 200
    assert options.headers["access-control-allow-origin"] == "*"
    assert client.post("/v1/resources").status_code == 405
    assert client.head("/v1/providers/openai/resources").status_code == 405
    assert client.get("/docs/api").status_code == 200


def test_generated_openapi_matches_runtime(api):
    client, _, _ = api
    assert client.get("/openapi.json").json() == json.loads(Path("schema/openapi.json").read_text())
