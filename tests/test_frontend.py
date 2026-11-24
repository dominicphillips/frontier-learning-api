import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from frontier_learning.app import create_app

app_module = importlib.import_module("frontier_learning.app")


@pytest.fixture
def web(tmp_path):
    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    (root / "fonts").mkdir()
    (root / "index.html").write_text("<!doctype html><main id='docs'></main>")
    (root / "assets" / "index-AbCd1234.js").write_text("export const ready = true;")
    (root / "assets" / "index-AbCd1234.css").write_text("body { margin: 0; }")
    (root / "fonts" / "geist.woff2").write_bytes(b"font")
    (root / "theme-init.js").write_text("document.documentElement.dataset.theme = 'light';")
    (root / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return root


@pytest.fixture
def client(tmp_path, web):
    with TestClient(create_app(tmp_path / "data", web)) as client:
        yield client


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/docs/resources",
        "/docs/resource",
        "/docs/learning-paths",
        "/docs/categories",
        "/docs/status",
        "/docs/resources/oa_" + "a" * 24,
        "/docs/resources/ca_" + "b" * 24,
        "/docs/resources/ga_" + "c" * 24,
    ],
)
def test_docs_deep_links_and_head(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.text == "<!doctype html><main id='docs'></main>"
    assert response.headers["cache-control"] == "public, max-age=3600"
    head = client.head(path)
    assert head.status_code == 200 and head.content == b""
    assert head.headers["content-length"] == response.headers["content-length"]


def test_docs_redirects_and_swagger_are_distinct(client):
    for path in ("/", "/reference"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"
    ui = client.get("/docs")
    csp = ui.headers["content-security-policy"]
    assert "script-src 'self';" in csp
    assert "style-src 'self' 'unsafe-inline';" in csp
    assert "font-src 'self';" in csp
    assert "connect-src 'self';" in csp
    assert "https://" not in csp
    assert ui.headers["x-content-type-options"] == "nosniff"
    assert ui.headers["x-frame-options"] == "DENY"
    swagger = client.get("/docs/api")
    assert swagger.status_code == 200
    assert "SwaggerUIBundle" in swagger.text
    assert "'/openapi.json'" in swagger.text
    assert "/docs/api/oauth2-redirect" in swagger.text
    for path in ("/docs/api", "/docs/api/oauth2-redirect"):
        response = client.get(path)
        assert response.status_code == 200
        assert (
            "script-src https://cdn.jsdelivr.net 'unsafe-inline'"
            in response.headers["content-security-policy"]
        )
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert schema.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert all(
        not path.startswith(("/docs", "/reference", "/assets")) for path in schema.json()["paths"]
    )


@pytest.mark.parametrize(
    ("path", "cache"),
    [
        ("/docs/assets/index-AbCd1234.js", "public, max-age=31536000, immutable"),
        ("/docs/assets/index-AbCd1234.css", "public, max-age=31536000, immutable"),
        ("/docs/fonts/geist.woff2", "public, max-age=86400"),
        ("/docs/theme-init.js", "public, max-age=86400"),
        ("/docs/favicon.svg", "public, max-age=86400"),
        ("/docs/index.html", "public, max-age=3600"),
    ],
)
def test_static_assets_and_cache(client, path, cache):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == cache
    assert client.head(path).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/docs/unknown",
        "/docs/resources/invalid",
        "/docs/resources/oa_" + "a" * 24 + "/extra",
        "/docs/api/unknown",
        "/docs/oauth2-redirect",
        "/v1/unknown",
        "/health/unknown",
        "/openapi.json/extra",
        "/redoc",
        "/docs/assets/missing.js",
        "/docs/assets/missing",
        "/assets/index-AbCd1234.js",
        "/favicon.svg",
        "/snapshot.json",
        "/.env",
        "/docs/.env",
        "/docs/assets/.private.js",
        "/docs/assets/%2e%2e/.env",
        "/docs/assets/%5cprivate.txt",
        "/docs/assets/%00",
    ],
)
def test_unknown_and_unsafe_paths_are_not_spa_fallbacks(client, path):
    for response in (client.get(path), client.head(path)):
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
        assert "text/html" not in response.headers.get("content-type", "")


def test_static_routes_do_not_shadow_api_methods(client):
    for path in ("/v1/resources", "/v1/providers/claude/status", "/health", "/health/ready"):
        for response in (client.head(path), client.post(path)):
            assert response.status_code == 405
            assert response.headers["allow"] == "GET"
            assert response.headers["cache-control"] == "no-store"


def test_reserved_files_and_symlinks_do_not_escape(tmp_path, web):
    secret = tmp_path / "private.txt"
    secret.write_text("private")
    (web / ".env").write_text("private")
    (web / "assets" / "escape.txt").symlink_to(secret)
    (web / "assets" / "hidden.txt").symlink_to(web / ".env")
    (web / "assets" / "outside").symlink_to(tmp_path, target_is_directory=True)
    for directory in (
        "docs",
        "v1",
        "health",
        "api",
        "resources",
        "resource",
        "learning-paths",
        "categories",
        "status",
    ):
        (web / directory).mkdir()
        (web / directory / "private.txt").write_text("private")
    with TestClient(create_app(tmp_path / "data", web)) as client:
        for path in (
            "/docs/assets/escape.txt",
            "/docs/assets/hidden.txt",
            "/docs/assets/outside/private.txt",
            "/docs/private.txt",
            "/docs/api/private.txt",
            "/docs/resources/private.txt",
            "/docs/resource/private.txt",
            "/docs/categories/private.txt",
            "/docs/status/private.txt",
            "/docs/v1/private.txt",
            "/docs/health/private.txt",
            "/v1/private.txt",
            "/health/private.txt",
        ):
            assert client.get(path).status_code == 404


@pytest.mark.parametrize("provider", ["openai", "claude", "gemini"])
@pytest.mark.parametrize("suffix", [".json", ".status.json", ".previous.json"])
def test_snapshot_files_must_remain_outside_public_root(tmp_path, web, provider, suffix):
    data = tmp_path / "data"
    data.mkdir()
    (data / f"{provider}{suffix}").symlink_to(web / "private.json")
    with pytest.raises(ValueError, match="Snapshot must be outside"):
        create_app(data, web)


def test_snapshot_directory_must_remain_outside_public_root(web):
    with pytest.raises(ValueError, match="Snapshot must be outside"):
        create_app(web / "data", web)


def test_index_cannot_escape_public_root(tmp_path, web):
    (web / "index.html").unlink()
    outside = tmp_path / "private.html"
    outside.write_text("private")
    (web / "index.html").symlink_to(outside)
    with pytest.raises(ValueError, match="Frontend directory must contain index.html"):
        create_app(tmp_path / "data", web)


def test_explicit_frontend_requires_an_index(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(ValueError, match="Frontend directory must contain index.html"):
        create_app(tmp_path / "data", root)


def test_auto_discovery_prefers_package_then_editable_checkout(tmp_path, monkeypatch):
    package = tmp_path / "src" / "frontier_learning"
    package.mkdir(parents=True)
    monkeypatch.setattr(app_module, "__file__", str(package / "app.py"))
    (tmp_path / "pyproject.toml").write_text("")
    editable = tmp_path / "frontend" / "dist"
    editable.mkdir(parents=True)
    (editable / "index.html").write_text("editable")
    packaged = package / "web"
    packaged.mkdir()
    (packaged / "index.html").write_text("packaged")
    with TestClient(create_app(tmp_path / "data")) as client:
        assert client.get("/docs").text == "packaged"
    (packaged / "index.html").unlink()
    with TestClient(create_app(tmp_path / "data")) as client:
        assert client.get("/docs").text == "editable"


def test_unbuilt_checkout_keeps_api_and_swagger_available(tmp_path, monkeypatch):
    monkeypatch.setattr(
        app_module, "__file__", str(tmp_path / "src" / "frontier_learning" / "app.py")
    )
    with TestClient(create_app(tmp_path / "data")) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/docs/api").status_code == 200
        assert client.get("/docs").status_code == 404


def test_cli_passes_explicit_frontend_directory(tmp_path, web, monkeypatch):
    import uvicorn

    from frontier_learning.cli import serve

    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(app=app, **kwargs))
    monkeypatch.setattr(
        sys,
        "argv",
        ["frontier-learning-api", "--data-dir", str(tmp_path / "data"), "--frontend-dir", str(web)],
    )
    serve()
    with TestClient(captured["app"]) as client:
        assert client.get("/docs").status_code == 200
    assert captured["host"] == "127.0.0.1"
    assert captured["proxy_headers"] is False
