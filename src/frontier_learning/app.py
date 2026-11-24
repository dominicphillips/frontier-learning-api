import base64
import re
from pathlib import Path
from typing import Annotated, get_args

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import __version__, catalog
from .models import Audience, CategoryCount, CategoryPage, Hash, Model, Slug, Status, json_hash
from .storage import SnapshotUnavailable

CATALOG_CACHE = (
    "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800, stale-if-error=604800"
)
STATUS_CACHE = "public, max-age=300, s-maxage=86400"
FRONTEND_HTML_CACHE = "public, max-age=3600"
FRONTEND_FILE_CACHE = "public, max-age=86400"
FRONTEND_ASSET_CACHE = "public, max-age=31536000, immutable"
FRONTEND_CSP = (
    "default-src 'none'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
    "script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; form-action 'none'"
)
DOC_PAGES = (
    "/docs",
    "/docs/resources",
    "/docs/resource",
    "/docs/learning-paths",
    "/docs/categories",
    "/docs/status",
)
SWAGGER_PATHS = ("/docs/api", "/docs/api/oauth2-redirect")


def frontend_root(frontend_dir: Path | str | None) -> Path | None:
    if frontend_dir is None:
        package = Path(__file__).resolve().parent
        candidates = [package / "web"]
        if package.parent.name == "src" and (package.parent.parent / "pyproject.toml").is_file():
            candidates.append(package.parent.parent / "frontend" / "dist")
        frontend_dir = next((path for path in candidates if (path / "index.html").is_file()), None)
        if frontend_dir is None:
            return None
    root = Path(frontend_dir).resolve(strict=True)
    index = (root / "index.html").resolve()
    if not root.is_dir() or not index.is_file() or not index.is_relative_to(root):
        raise ValueError("Frontend directory must contain index.html")
    if any(part.startswith(".") for part in index.relative_to(root).parts):
        raise ValueError("Frontend directory must contain index.html")
    return root


def mount_frontend(app: FastAPI, root: Path, specs: dict[str, catalog.ProviderSpec]) -> None:
    for spec in specs.values():
        for path in (
            spec.store.path.parent,
            spec.store.path,
            spec.store.state_path,
            spec.store.previous_path,
        ):
            if path.resolve().is_relative_to(root):
                raise ValueError("Snapshot must be outside the frontend directory")

    def document(document_path: str):
        parts = document_path.split("/")
        if any(
            not part
            or part.startswith(".")
            or "\\" in part
            or any(ord(char) < 32 or ord(char) == 127 for char in part)
            for part in parts
        ):
            raise fail(404, "not-found")
        try:
            target = (root / document_path).resolve()
            relative = target.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            raise fail(404, "not-found") from None
        if not target.is_file() or any(part.startswith(".") for part in relative.parts):
            raise fail(404, "not-found")
        headers = {"Cache-Control": FRONTEND_FILE_CACHE}
        if target.suffix == ".html":
            headers = {
                "Cache-Control": FRONTEND_HTML_CACHE,
                "Content-Security-Policy": FRONTEND_CSP,
            }
        elif parts[0] == "assets" and re.search(r"-[A-Za-z0-9_-]{8,}\.[a-zA-Z0-9]+$", target.name):
            headers["Cache-Control"] = FRONTEND_ASSET_CACHE
        return FileResponse(target, headers=headers)

    def page():
        return document("index.html")

    for path in DOC_PAGES:
        app.add_api_route(path, page, methods=["GET", "HEAD"], include_in_schema=False)

    @app.api_route(
        "/docs/resources/{resource_id}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def resource_page(resource_id: str):
        if not re.fullmatch(r"(?:oa|ca|ga)_[a-f0-9]{24}", resource_id):
            raise fail(404, "not-found")
        return page()

    def asset(request: Request):
        return document(request.url.path.removeprefix("/docs/"))

    reserved = {
        "api",
        "resources",
        "resource",
        "learning-paths",
        "categories",
        "status",
        "v1",
        "health",
        "docs",
        "reference",
        "redoc",
        "openapi.json",
    }
    for entry in sorted(root.iterdir()):
        if entry.name in reserved or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", entry.name):
            continue
        path = (
            f"/docs/{entry.name}/{{document_path:path}}"
            if entry.is_dir()
            else f"/docs/{entry.name}"
        )
        app.add_api_route(path, asset, methods=["GET", "HEAD"], include_in_schema=False)


class Cursor(Model):
    version: int
    snapshot_id: Hash
    filters_hash: Hash
    after_id: str


def fail(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


def encode_cursor(snapshot: str, filters_hash: str, last_id: str) -> str:
    value = Cursor(version=1, snapshot_id=snapshot, filters_hash=filters_hash, after_id=last_id)
    return (
        base64.urlsafe_b64encode(value.model_dump_json(by_alias=True).encode()).decode().rstrip("=")
    )


def decode_cursor(value: str) -> Cursor:
    if len(value) > 1024 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise fail(400, "invalid-cursor")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        cursor = Cursor.model_validate_json(raw)
        if cursor.version != 1:
            raise ValueError("Cursor version")
        return cursor
    except (ValueError, UnicodeError):
        raise fail(400, "invalid-cursor") from None


def cached_result(request: Request, value, cache: str = CATALOG_CACHE) -> Response:
    data = value.model_dump(mode="json", by_alias=True) if isinstance(value, Model) else value
    etag = f'W/"{json_hash(data)}"'
    headers = {"ETag": etag, "Cache-Control": cache}
    candidates = request.headers.get("if-none-match", "").split(",")
    if any(
        token.strip() == "*" or token.strip().removeprefix("W/") == etag.removeprefix("W/")
        for token in candidates
    ):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=data, headers=headers)


def paginate(items, snapshot_id, filters, cursor, limit, *, aggregate=False):
    filters_hash = json_hash(filters)
    items.sort(key=(lambda r: (r["id"][3:], r["id"])) if aggregate else (lambda r: r["id"]))
    start = 0
    if cursor:
        parsed = decode_cursor(cursor)
        if parsed.snapshot_id != snapshot_id:
            raise fail(409, "snapshot-changed")
        if parsed.filters_hash != filters_hash:
            raise fail(400, "cursor-filter-mismatch")
        positions = {r["id"]: i for i, r in enumerate(items)}
        if parsed.after_id not in positions:
            raise fail(400, "invalid-cursor")
        start = positions[parsed.after_id] + 1
    page = items[start : start + limit]
    next_cursor = (
        encode_cursor(snapshot_id, filters_hash, page[-1]["id"])
        if page and start + limit < len(items)
        else None
    )
    return {
        "items": page,
        "nextCursor": next_cursor,
        "total": len(items),
        "snapshotId": snapshot_id,
    }


def matches(resource, search, category, kind, audience):
    return (
        (category is None or category in resource.category_ids)
        and (kind is None or resource.kind == kind)
        and (audience is None or audience in resource.audiences)
        and (
            not search
            or search
            in " ".join([resource.title, resource.summary or "", *resource.tags]).casefold()
        )
    )


def matches_learning_path(item: dict, search: str, audience: str | None, contains: str | None):
    return (
        (audience is None or audience in item["audiences"])
        and (contains is None or any(step["resourceId"] == contains for step in item["steps"]))
        and (
            not search
            or search
            in " ".join(
                [
                    item["title"],
                    item["summary"] or "",
                    *item["tags"],
                    *(step["title"] for step in item["steps"]),
                ]
            ).casefold()
        )
    )


def provider_router(spec: catalog.ProviderSpec) -> APIRouter:
    router = APIRouter(prefix=f"/v1/providers/{spec.id}", tags=[spec.label])
    models, store = spec.models, spec.store

    @router.get("/status", response_model=Status, responses={304: {"description": "Not modified"}})
    def status(request: Request):
        value = store.status()
        if value.state == "unavailable":
            return JSONResponse(
                value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"}
            )
        return cached_result(request, value, STATUS_CACHE)

    @router.get(
        "/categories", response_model=CategoryPage, responses={304: {"description": "Not modified"}}
    )
    def categories(request: Request):
        snapshot = store.read()
        items = [
            CategoryCount(
                id=x.id,
                label=x.label,
                count=sum(x.id in r.category_ids for r in snapshot.resources),
            )
            for x in sorted(snapshot.categories, key=lambda c: c.id)
        ]
        return cached_result(request, CategoryPage(items=items, snapshot_id=snapshot.snapshot_id))

    @router.get(
        "/resources",
        response_model=models.ResourcePage,
        responses={304: {"description": "Not modified"}},
    )
    def resources(
        request: Request,
        q: Annotated[str | None, Query(max_length=200)] = None,
        category: Annotated[Slug | None, Query()] = None,
        kind: models.Kind | None = None,
        audience: Audience | None = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        snapshot = store.read()
        search = " ".join((q or "").split()).casefold()
        filters = {"q": search, "category": category, "kind": kind, "audience": audience}
        items = [
            r.model_dump(mode="json", by_alias=True)
            for r in snapshot.resources
            if matches(r, search, category, kind, audience)
        ]
        return cached_result(request, paginate(items, snapshot.snapshot_id, filters, cursor, limit))

    @router.get(
        "/resources/{resource_id}",
        response_model=models.Resource,
        responses={304: {"description": "Not modified"}},
    )
    def resource(resource_id: str, request: Request):
        if not re.fullmatch(spec.prefix + r"[a-f0-9]{24}", resource_id):
            raise fail(404, "resource-not-found")
        for item in store.read().resources:
            if item.id == resource_id:
                return cached_result(request, item)
        raise fail(404, "resource-not-found")

    @router.get(
        "/learning-paths",
        response_model=catalog.ProviderLearningPathPage,
        responses={304: {"description": "Not modified"}},
    )
    def learning_paths(
        request: Request,
        q: Annotated[str | None, Query(max_length=200)] = None,
        audience: Audience | None = None,
        contains: Annotated[catalog.ResourceId | None, Query()] = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        snapshot = store.read()
        search = " ".join((q or "").split()).casefold()
        filters = {"q": search, "audience": audience, "contains": contains}
        items = [
            item
            for item in catalog.snapshot_learning_paths(spec.id, snapshot, aggregate=False)
            if matches_learning_path(item, search, audience, contains)
        ]
        return cached_result(request, paginate(items, snapshot.snapshot_id, filters, cursor, limit))

    @router.get(
        "/learning-paths/{resource_id}",
        response_model=catalog.ProviderLearningPath,
        responses={304: {"description": "Not modified"}},
    )
    def learning_path(resource_id: str, request: Request):
        if not re.fullmatch(spec.prefix + r"[a-f0-9]{24}", resource_id):
            raise fail(404, "learning-path-not-found")
        snapshot = store.read()
        by_url = {catalog.canonical_url_key(item.url): item for item in snapshot.resources}
        for item in snapshot.resources:
            if item.id == resource_id and item.kind == "learning-path":
                return cached_result(
                    request,
                    catalog.project_learning_path(spec.id, item, by_url, aggregate=False),
                )
        raise fail(404, "learning-path-not-found")

    @router.get("/health/ready", include_in_schema=False)
    def ready():
        try:
            store.read()
        except SnapshotUnavailable:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    return router


def create_app(data_dir: Path | str, frontend_dir: Path | str | None = None) -> FastAPI:
    specs = catalog.providers(Path(data_dir))
    app = FastAPI(
        title="Frontier Learning API",
        version=__version__,
        docs_url=SWAGGER_PATHS[0],
        swagger_ui_oauth2_redirect_url=SWAGGER_PATHS[1],
        redoc_url=None,
        debug=False,
    )
    app.state.providers = specs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "HEAD"],
        allow_headers=["Accept", "Content-Type", "If-None-Match"],
        expose_headers=["ETag"],
    )

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if (
            "application/json" in response.headers.get("Content-Type", "")
            or response.status_code == 304
        ):
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        elif "text/html" in response.headers.get("Content-Type", ""):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
                "script-src https://cdn.jsdelivr.net 'unsafe-inline'; "
                "style-src https://cdn.jsdelivr.net 'unsafe-inline'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'"
                if request.url.path in SWAGGER_PATHS
                else FRONTEND_CSP
            )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/v1/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "ETag"
        response.headers.setdefault("Cache-Control", "public, max-age=60")
        if response.status_code >= 400 or "/health" in request.url.path:
            response.headers["Cache-Control"] = "no-store"
            if "ETag" in response.headers:
                del response.headers["ETag"]
        return response

    @app.exception_handler(SnapshotUnavailable)
    async def unavailable(_request: Request, _exc: SnapshotUnavailable):
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "snapshot-unavailable"}},
            headers={"Cache-Control": "no-store", "Retry-After": "60"},
        )

    @app.get("/", include_in_schema=False)
    @app.get("/reference", include_in_schema=False)
    def root():
        return RedirectResponse("/docs", status_code=307)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            for spec in specs.values():
                spec.store.read()
        except SnapshotUnavailable:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    def snapshots():
        values = {name: spec.store.read() for name, spec in specs.items()}
        return values, json_hash({name: value.snapshot_id for name, value in values.items()})

    @app.get("/v1/providers", response_model=catalog.ProviderPage)
    def providers(request: Request):
        values = [
            catalog.Provider(
                id=spec.id,
                label=spec.label,
                source_url=spec.source_url,
                resource_prefix=spec.prefix,
                kinds=list(get_args(spec.models.Kind)),
                status=spec.store.status(),
            )
            for spec in specs.values()
        ]
        page = catalog.ProviderPage(items=values)
        if any(value.status.state == "unavailable" for value in values):
            return JSONResponse(
                page.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"}
            )
        return cached_result(request, page, STATUS_CACHE)

    @app.get("/v1/status", response_model=catalog.CatalogStatus)
    def status(request: Request):
        values = {name: spec.store.status() for name, spec in specs.items()}
        states = {value.state for value in values.values()}
        state = (
            "unavailable" if "unavailable" in states else "stale" if "stale" in states else "fresh"
        )
        value = catalog.CatalogStatus(
            state=state,
            snapshot_id=None
            if state == "unavailable"
            else json_hash({name: value.snapshot_id for name, value in values.items()}),
            resource_count=sum(value.resource_count for value in values.values()),
            providers=values,
        )
        if state == "unavailable":
            return JSONResponse(
                value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"}
            )
        return cached_result(request, value, STATUS_CACHE)

    @app.get("/v1/categories", response_model=catalog.CategoryPage)
    def categories(request: Request, provider: catalog.ProviderId | None = None):
        values, snapshot_id = snapshots()
        items = [
            catalog.Category(
                id=f"{name}:{category.id}",
                provider=name,
                slug=category.id,
                label=category.label,
                count=sum(category.id in r.category_ids for r in snapshot.resources),
            )
            for name, snapshot in values.items()
            if provider is None or name == provider
            for category in snapshot.categories
        ]
        items.sort(key=lambda c: c.id)
        return cached_result(request, catalog.CategoryPage(items=items, snapshot_id=snapshot_id))

    @app.get("/v1/resources", response_model=catalog.ResourcePage)
    def resources(
        request: Request,
        provider: catalog.ProviderId | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        category: Annotated[catalog.CategoryId | None, Query()] = None,
        kind: catalog.Kind | None = None,
        audience: Audience | None = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        values, snapshot_id = snapshots()
        search = " ".join((q or "").split()).casefold()
        filters = {
            "q": search,
            "category": category,
            "kind": kind,
            "audience": audience,
            "provider": provider,
        }
        category_provider, _, category_slug = (category or "").partition(":")
        items = [
            catalog.project_resource(name, r)
            for name, snapshot in values.items()
            if (provider is None or name == provider)
            and (not category or category_provider == name)
            for r in snapshot.resources
            if matches(r, search, category_slug or None, kind, audience)
        ]
        return cached_result(
            request, paginate(items, snapshot_id, filters, cursor, limit, aggregate=True)
        )

    @app.get("/v1/resources/{resource_id}", response_model=catalog.Resource)
    def resource(resource_id: str, request: Request):
        if not re.fullmatch(r"(?:oa|ca|ga)_[a-f0-9]{24}", resource_id):
            raise fail(404, "resource-not-found")
        spec = next(spec for spec in specs.values() if resource_id.startswith(spec.prefix))
        for item in spec.store.read().resources:
            if item.id == resource_id:
                return cached_result(request, catalog.project_resource(spec.id, item))
        raise fail(404, "resource-not-found")

    @app.get(
        "/v1/learning-paths",
        response_model=catalog.LearningPathPage,
        responses={304: {"description": "Not modified"}},
    )
    def learning_paths(
        request: Request,
        provider: catalog.ProviderId | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        audience: Audience | None = None,
        contains: Annotated[catalog.ResourceId | None, Query()] = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        values, snapshot_id = snapshots()
        search = " ".join((q or "").split()).casefold()
        filters = {
            "q": search,
            "audience": audience,
            "contains": contains,
            "provider": provider,
        }
        items = [
            item
            for name, snapshot in values.items()
            if provider is None or name == provider
            for item in catalog.snapshot_learning_paths(name, snapshot, aggregate=True)
            if matches_learning_path(item, search, audience, contains)
        ]
        return cached_result(
            request, paginate(items, snapshot_id, filters, cursor, limit, aggregate=True)
        )

    @app.get(
        "/v1/learning-paths/{resource_id}",
        response_model=catalog.LearningPath,
        responses={304: {"description": "Not modified"}},
    )
    def learning_path(resource_id: str, request: Request):
        if not re.fullmatch(r"(?:oa|ca|ga)_[a-f0-9]{24}", resource_id):
            raise fail(404, "learning-path-not-found")
        spec = next(spec for spec in specs.values() if resource_id.startswith(spec.prefix))
        snapshot = spec.store.read()
        by_url = {catalog.canonical_url_key(item.url): item for item in snapshot.resources}
        for item in snapshot.resources:
            if item.id == resource_id and item.kind == "learning-path":
                return cached_result(
                    request,
                    catalog.project_learning_path(spec.id, item, by_url, aggregate=True),
                )
        raise fail(404, "learning-path-not-found")

    for spec in specs.values():
        app.include_router(provider_router(spec))
    static_root = frontend_root(frontend_dir)
    if static_root is not None:
        mount_frontend(app, static_root, specs)
    return app
