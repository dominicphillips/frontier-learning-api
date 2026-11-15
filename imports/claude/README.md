# Claude Academy Metadata API

> **Independent project:** Dominic Phillips is not affiliated with Anthropic, and this project is not endorsed by Anthropic.

I built this catalog and read-only metadata API to share with portfolio companies and internal teams so they can build learning resources for their employees. Browse the [live catalog](https://claude-academy.deployedwork.com/), or use the API to pull public resource metadata into your own tools with links back to the official [Claude Academy](https://academy.claude.com) pages.

It follows the same API contract as the [OpenAI Academy Metadata API](https://github.com/dominicphillips/openai-academy-api), so one client can read both.

## Public API and coverage limits

All read endpoints are public and require no authentication or API key:

```bash
curl -s "https://claude-academy.deployedwork.com/v1/resources?limit=3" | python3 -m json.tool
```

| Endpoint | Description |
| --- | --- |
| `GET /v1/resources` | Paginated resource metadata with optional search, category, kind, and audience filters. |
| `GET /v1/resources/{id}` | Single resource metadata record by ID. |
| `GET /v1/categories` | Collections and resource counts for the active snapshot. |
| `GET /v1/status` | Snapshot freshness and per-collection coverage. |

The snapshot covers the public course, collection, tutorial and use-case pages listed in the Claude Academy sitemap, refreshed daily; check [`GET /v1/status`](https://claude-academy.deployedwork.com/v1/status) for freshness. Each record holds the title, summary, estimated time, product and role tags, the collections that list it and, for courses, the outline of lesson and quiz titles. Lesson pages are linked, never fetched. Course text, videos and images are not copied; `artwork` links to each page's own share image on `academy.claude.com`. The pages publish no audience or level, so `audiences` is `[]` and `level` is `null`. The service does not host courses, provision accounts, enroll learners, or grant access. Sign-in and learning remain on Claude Academy.

## Run locally with the synthetic fixture

Requires Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/) in a checkout of this repository. [`examples/collection.fixture.json`](examples/collection.fixture.json) contains one synthetic resource record for local verification (not live Claude Academy data). Import it into a temporary snapshot path such as `/tmp/claude-academy-example/snapshot.json` rather than `data/snapshot.json`, then start the server:

```bash
uv sync --frozen
uv run --frozen claude-academy-collector --snapshot /tmp/claude-academy-example/snapshot.json import examples/collection.fixture.json --method fixture
uv run --frozen claude-academy-api --snapshot /tmp/claude-academy-example/snapshot.json --host 127.0.0.1 --port 8000
```

## Collect a live snapshot

The collector is deterministic: no model or agent is involved. It reads `robots.txt` first and checks every URL against it, reads the sitemap, then fetches each public resource page once, one request at a time, at least 1.1 seconds apart, with the User-Agent `claude-academy-api/<version> (+https://github.com/dominicphillips/claude-academy-api)`. A full pass is about 340 requests.

```bash
uv run --frozen claude-academy-collector --snapshot data/snapshot.json --state-dir data/collector run --live
```

A page that fails keeps its previous record, a page that leaves the sitemap leaves the snapshot, and a pass that reads fewer than half of the published pages publishes nothing.

## Documentation, contributing, and license

- **API documentation and source:** See the [API Reference](https://claude-academy.deployedwork.com/reference), [Swagger UI (`/docs`)](https://claude-academy.deployedwork.com/docs), [OpenAPI 3.1 specification (`/openapi.json`)](https://claude-academy.deployedwork.com/openapi.json), [`schema/contract.json`](schema/contract.json), and the [GitHub repository](https://github.com/dominicphillips/claude-academy-api) for schemas, filter values, and pagination details.
- **Contributing:** See [`CONTRIBUTING.md`](CONTRIBUTING.md) for offline test, lint, and contract checks.
- **License:** Repository code is licensed under the [MIT License](LICENSE) (Copyright (c) 2026 Dominic Phillips). The MIT License covers this repository's software only and does not grant rights to Claude Academy courses, media, or other content.
