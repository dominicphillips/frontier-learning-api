# Frontier Learning Metadata API

> **Independent project:** Dominic Phillips is not affiliated with OpenAI, Anthropic, or Google, and this project is not endorsed by those providers.

I built this read-only metadata API so teams can pull public AI learning resources from OpenAI, Anthropic, and Google into internal directories and tools with links back to the official provider pages. Browse the [human catalog](https://deployedwork.com/learn), or query `https://learning.deployedwork.com` directly without an API key.

## Query the public API

All read endpoints are public and require no authentication:

```bash
curl -s "https://learning.deployedwork.com/v1/resources?limit=3" | python3 -m json.tool
```

### Aggregate catalog endpoints

| Endpoint | Description |
| --- | --- |
| `GET /v1/resources` | Paginated resource metadata across `openai`, `claude`, and `gemini`. Filter by `provider`, `q`, `category` (namespaced `provider:slug`), `kind`, `audience`, `cursor`, and `limit` (`1..100`, default `20`). |
| `GET /v1/resources/{id}` | Single resource record by URL-derived ID (`oa_`, `ca_`, or `ga_` plus 24 lowercase hex characters). |
| `GET /v1/categories` | Namespaced categories (`id` as `provider:slug`, `provider`, `slug`, `label`, `count`). |
| `GET /v1/providers` | Configured provider summaries and availability. |
| `GET /v1/status` | Per-provider snapshot freshness, coverage, and aggregate status. |

Aggregate resources include a `provider` field (`openai`, `claude`, or `gemini`) and namespaced `categoryIds` (`provider:slug`). Provenance fields (`sourceUrls`, `fetchedAt`, `contentHash`, `method`) reflect the underlying source metadata; API projections do not alter source content hashes.

Aggregate `kind` filters accept the union of source kinds (`course`, `learning-path`, `article`, `video`, `event`, `collection`, `external`, `tutorial`, `use-case`, `lab`), though each provider only publishes a subset. Results are ordered deterministically by ID hash suffix with a full-ID tie-breaker and paginate via opaque cursors. An invalid cursor or a cursor reused with different filter parameters returns `400`; if any provider snapshot refreshes mid-pagination, the aggregate `snapshotId` changes and the API returns `409` so the client can restart from the first page. Aggregate list endpoints (`/v1/resources` and `/v1/categories`) return `503` only when a provider has no valid current, in-memory, or previous snapshot; an invalid replacement snapshot continues serving the last valid snapshot and reports `stale`. `GET /v1/resources/{id}` reads only the matching provider and remains available when another provider has no usable snapshot.

### Provider-scoped endpoints

| Endpoint | Description |
| --- | --- |
| `GET /v1/providers/{provider}/resources` | Provider-only paginated resources with native category slugs, provider-specific `kind` enums, and a provider-scoped cursor. |
| `GET /v1/providers/{provider}/resources/{id}` | Single resource record in that provider's native metadata shape. |
| `GET /v1/providers/{provider}/categories` | Un-namespaced category slugs and counts for that provider. |
| `GET /v1/providers/{provider}/status` | Snapshot freshness and category coverage for that provider. |

Healthy provider-scoped endpoints continue serving `200` responses even when another provider's snapshot is unavailable.

### Health, schema, and HTTP caching

- **Operational and OpenAPI routes:** `GET /health`, `GET /health/ready`, `GET /docs` (Swagger UI), and `GET /openapi.json`. `GET /health/ready` returns `503` only when a provider has no usable snapshot.
- **Caching:** Successful catalog `GET` responses send a 24-hour `Cache-Control` policy with a weak `ETag` and return `304 Not Modified` on matching `If-None-Match` requests. Status endpoints use a 5-minute browser recheck policy, and error responses send `Cache-Control: no-store`.
- **Optional Cloudflare cache purge:** To purge edge caches after a published snapshot update, set `FRONTIER_CLOUDFLARE_ZONE_ID`, `FRONTIER_CLOUDFLARE_HOSTNAMES` (comma-separated exact hostnames), and `FRONTIER_CLOUDFLARE_PURGE_TOKEN_FILE`. Source-specific schedulers share this configuration.

## Source scope and practical limitations

This service serves validated snapshots of public metadata and links back to the official source pages (`https://academy.openai.com`, `https://academy.claude.com`, and `https://www.skills.google`). Check [`GET /v1/status`](https://learning.deployedwork.com/v1/status) for current snapshot timestamps and per-category coverage (`complete`, `partial`, or `not-collected`).

- **No course hosting or account actions:** The API never hosts course bodies, videos, or downloadable assets, and it does not provision accounts, enroll learners, track progress, or unlock gated content. Sign-in and learning happen on the official provider sites.
- **Unpublished fields stay empty:** All documented nullable fields are serialized, but fields not published on an in-scope source page remain `null` or `[]` rather than estimated.
- **Provider-specific collection boundaries:**
  - **OpenAI (`openai`):** Captures public `academy.openai.com` resource pages within robots.txt and domain controls; excludes authenticated `/home` routes, club member areas, and SCORM packages.
  - **Claude (`claude`):** Captures public `academy.claude.com` course, collection, tutorial, and use-case overview pages from the sitemap; excludes lesson pages and `anthropic.skilljar.com`, and only hotlinks the page's share image URL for `artwork`.
  - **Gemini (`gemini`):** Captures public `www.skills.google` catalog entries, `/paths/<id>`, and `/course_templates/<id>` pages; lab records (`kind=lab`) come from catalog listings without fetching `/focuses/` lab pages, course units, account pages, or internal `/api/` routes, and `artwork` is always `null`.

## Run locally with synthetic fixtures

Running the server requires Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/). Production snapshot files are not committed to git; the API expects validated snapshots at `data/openai.json`, `data/claude.json`, and `data/gemini.json`.

Each `examples/<provider>/collection.fixture.json` file contains one synthetic resource record for local testing and CI verification (not current live catalog data). Import the three fixtures into `data/` and start the server:

```bash
uv sync --frozen
for provider in openai claude gemini; do
  uv run frontier-learning-collect --provider "$provider" --snapshot "data/${provider}.json" import "examples/${provider}/collection.fixture.json" --method fixture
done
uv run frontier-learning-api --data-dir data --host 127.0.0.1 --port 8000
```

Once running, query `http://127.0.0.1:8000/v1/resources` or open `http://127.0.0.1:8000/docs`.

## Documentation, contributing, and license

- **Schemas and source history:** Unified OpenAPI and per-provider JSON schemas live in [`schema/openapi.json`](schema/openapi.json) and `schema/{openai,claude,gemini}/`. Prior standalone repository histories and tests are preserved under the `import/openai`, `import/claude`, and `import/gemini` git tags at [`github.com/dominicphillips/frontier-learning-api`](https://github.com/dominicphillips/frontier-learning-api).
- **Contributing and security:** See [`CONTRIBUTING.md`](CONTRIBUTING.md) for offline validation, schema generation, and test commands, and [`SECURITY.md`](SECURITY.md) for runtime boundaries and vulnerability reporting.
- **License:** Repository software is licensed under the [MIT License](LICENSE) (Copyright (c) 2026 Dominic Phillips). The MIT License covers this repository's code only and grants no rights to OpenAI, Anthropic, or Google courses, trademarks, media, or third-party content.
