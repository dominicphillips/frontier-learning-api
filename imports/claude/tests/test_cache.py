from fastapi.testclient import TestClient

from claude_academy_api.app import create_app
from claude_academy_api.storage import SnapshotStore

CATALOG_CACHE = (
    "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800, stale-if-error=604800"
)
STATUS_CACHE = "public, max-age=300, s-maxage=86400"


def test_successful_read_responses_support_etag_and_weak_matching(
    tmp_path, artifact, write_artifact
):
    path = tmp_path / "snapshot.json"
    snapshot = SnapshotStore(path).publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(path))
    for route, cache in [
        ("/v1/resources?limit=1", CATALOG_CACHE),
        ("/v1/categories", CATALOG_CACHE),
        (f"/v1/resources/{snapshot.resources[0].id}", CATALOG_CACHE),
        ("/v1/status", STATUS_CACHE),
    ]:
        first = client.get(route, headers={"Origin": "https://example.com"})
        assert first.status_code == 200
        assert first.headers["cache-control"] == cache
        etag = first.headers["etag"]
        assert etag.startswith('W/"')
        assert "ETag" in first.headers["access-control-expose-headers"]
        for condition in [etag, etag.removeprefix("W/"), f'W/"other", {etag}', "*"]:
            response = client.get(route, headers={"If-None-Match": condition})
            assert response.status_code == 304 and response.content == b""
            assert response.headers["etag"] == etag
            assert response.headers["cache-control"] == cache
            assert response.headers["access-control-expose-headers"] == "ETag"
            assert response.headers["x-content-type-options"] == "nosniff"


def test_status_keeps_its_shape_and_changes_etag_on_publication(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    store.publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(path))
    first = client.get("/v1/status")
    assert list(first.json()) == [
        "state",
        "snapshotId",
        "generatedAt",
        "lastAttemptAt",
        "lastSuccessAt",
        "resourceCount",
        "coverage",
    ]
    artifact["resources"][0]["summary"] = "Changed fixture summary."
    store.publish(write_artifact(artifact), method="fixture")
    changed = client.get("/v1/status", headers={"If-None-Match": first.headers["etag"]})
    assert changed.status_code == 200
    assert changed.headers["etag"] != first.headers["etag"]
    assert changed.json()["snapshotId"] != first.json()["snapshotId"]


def test_filter_and_snapshot_changes_do_not_return_wrong_not_modified(
    tmp_path, artifact, write_artifact
):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    store.publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(path))
    first = client.get("/v1/resources?limit=1")
    etag = first.headers["etag"]
    filtered = client.get("/v1/resources?q=missing", headers={"If-None-Match": etag})
    assert filtered.status_code == 200 and filtered.headers["etag"] != etag
    cursor = first.json()["nextCursor"]
    artifact["resources"][0]["summary"] = "Changed fixture summary."
    store.publish(write_artifact(artifact), method="fixture")
    changed = client.get("/v1/resources?limit=1", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["etag"] != etag
    conflict = client.get(
        "/v1/resources", params={"cursor": cursor}, headers={"If-None-Match": "*"}
    )
    assert conflict.status_code == 409 and conflict.headers["cache-control"] == "no-store"
    assert "etag" not in conflict.headers


def test_errors_and_operational_routes_are_never_cacheable(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    SnapshotStore(path).publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(path))
    for route in [
        "/v1/resources?limit=101",
        "/v1/resources?cursor=bad",
        "/v1/resources/missing",
        "/v1/missing",
        "/health",
        "/health/ready",
    ]:
        response = client.get(route, headers={"If-None-Match": "*"})
        assert response.status_code != 304
        assert response.headers["cache-control"] == "no-store"
        assert "etag" not in response.headers
    missing = TestClient(create_app(tmp_path / "missing.json"))
    unavailable = missing.get("/v1/resources")
    assert unavailable.status_code == 503 and unavailable.headers["cache-control"] == "no-store"
    status = missing.get("/v1/status", headers={"If-None-Match": "*"})
    assert status.status_code == 200 and status.json()["state"] == "unavailable"
    assert status.headers["cache-control"] == "no-store" and "etag" not in status.headers


def test_shared_cache_copy_is_identical_with_or_without_origin(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    snapshot = SnapshotStore(path).publish(write_artifact(artifact), method="fixture")
    client = TestClient(create_app(path))
    for route in [
        "/v1/resources?limit=1",
        "/v1/categories",
        f"/v1/resources/{snapshot.resources[0].id}",
        "/v1/status",
    ]:
        variants = [
            client.get(route, headers=headers)
            for headers in [
                {},
                {"Origin": "https://one.example"},
                {"Origin": "https://two.example", "Cookie": "session=fixture"},
            ]
        ]
        for response in variants:
            # An edge copy stored from any one request must stay valid for every requester.
            assert response.headers["access-control-allow-origin"] == "*"
            assert response.headers["access-control-expose-headers"] == "ETag"
            assert "access-control-allow-credentials" not in response.headers
            assert response.headers["etag"] == variants[0].headers["etag"]
            assert response.content == variants[0].content


def test_cross_origin_conditional_get_preflight_is_allowed(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.json"))
    response = client.options(
        "/v1/resources",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "If-None-Match",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers
