# Gemini Academy Metadata API

> **Independent project:** Dominic Phillips is not affiliated with Google, and this project is not endorsed by Google.

I built this catalog and read-only metadata API to share with portfolio companies and internal teams so they can build learning resources for their employees. Browse the [live catalog](https://gemini-academy.deployedwork.com/), or use the API to pull public resource metadata into your own tools with links back to the official [Google Skills](https://www.skills.google) pages.

It follows the same API contract as the [OpenAI Academy Metadata API](https://github.com/dominicphillips/openai-academy-api) and the [Claude Academy Metadata API](https://github.com/dominicphillips/claude-academy-api), so one client can read all three.

## Why Google Skills

To find Google's equivalent of Claude Academy and OpenAI Academy, I looked for a public catalog of Gemini courses, learning paths, and hands-on labs. [Google Skills](https://www.skills.google) is where Google itself sends learners: Google's "Learn AI skills" page (`ai.google/learn-ai-skills`) links mostly to `www.skills.google`, and the former Google Cloud Skills Boost address (`cloudskillsboost.google`) redirects to it. On 2026-11-13 it held 1,315 English entries across courses, labs, and learning paths, each with a title, description, duration, level, and, where one exists, a credential. Its `robots.txt` allows the catalog, path, and course pages for every user agent, disallows only `/api/` and the lab start, resume, and stop actions, and has no rule against AI crawlers. Its terms of service (the Qwiklabs agreement at `/terms_of_service`) are written for signed-in lab use and forbid reselling or copying the service and publishing course content. This project signs in nowhere, starts no lab, copies no course, lesson, or lab text, video, or image, and publishes only catalog-listing metadata with links back to the official pages.

Other Google learning sites were considered and not used:

- **Gemini Academy from Google for Education (`edu.google.com`):** A training program for teachers whose host `robots.txt` blocks AI crawlers by name (`ClaudeBot`, `Anthropic-AI`, `GPTBot`, `Google-Extended`, and others).
- **Grow with Google (`grow.google/ai`):** Explicitly allows AI crawlers, but is a program page for a handful of courses and certificates taught on Coursera rather than a catalog of its own.
- **Google Cloud Skills Boost (`cloudskillsboost.google`):** Redirects to Google Skills.
- **Google Workspace Learning Center (`support.google.com/a/users`):** Help-center articles and tips without course metadata such as duration or level; a possible second source later.
- **Google AI for Developers (`ai.google.dev`):** API reference documentation and a cookbook rather than courses.

## Public API and coverage limits

All read endpoints are public and require no authentication or API key:

```bash
curl -s "https://gemini-academy.deployedwork.com/v1/resources?limit=3" | python3 -m json.tool
```

| Endpoint | Description |
| --- | --- |
| `GET /v1/resources` | Paginated resource metadata with optional search, category, kind, and audience filters. |
| `GET /v1/resources/{id}` | Single resource metadata record by ID. |
| `GET /v1/categories` | Learning paths and resource counts for the active snapshot. |
| `GET /v1/status` | Snapshot freshness and per-path coverage. |

The snapshot covers every Google Skills catalog entry (`course`, `learning-path`, and `lab`) whose title or description mentions Gemini, plus every course and lab that belongs to one of those learning paths, leaving out entries marked `[DEPRECATED]`. On 2026-11-13 the snapshot held 292 entries: 211 courses, 58 labs, and 23 learning paths; check [`GET /v1/status`](https://gemini-academy.deployedwork.com/v1/status) for current counts and per-path coverage. Each record holds the title, summary, duration, level (Google's Introductory, Intermediate, and Advanced mapped to `beginner`, `intermediate`, and `advanced`), a credential tag such as `Skill badge` when one exists, the learning paths that list it (`categories`), and, for courses, the outline of module, lesson, quiz, and lab titles, while learning paths list their member courses and labs. Lab pages hold lab instructions and are never fetched; a lab's record comes from the catalog listing, and lab links carry `?parent=catalog` because Google Skills sends a visitor who is not signed in to the sign-in page without it. Lesson, quiz, and lab steps inside a course are linked, never fetched. Course, lesson, and lab text, videos, and images are not in the snapshot: `media` is always `[]`, `artwork` is always `null` because Google Skills serves one generic share image for every page, and `audiences` is `[]` because the pages publish no audience.

## Run locally with the synthetic fixture

Requires Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/) in a checkout of this repository. [`examples/collection.fixture.json`](examples/collection.fixture.json) contains one synthetic resource record for local verification (not live Google Skills data). Import it into a temporary snapshot path such as `/tmp/gemini-academy-example/snapshot.json` rather than `data/snapshot.json`, then start the server:

```bash
uv sync --frozen
uv run --frozen gemini-academy-collector --snapshot /tmp/gemini-academy-example/snapshot.json import examples/collection.fixture.json --method fixture
uv run --frozen gemini-academy-api --snapshot /tmp/gemini-academy-example/snapshot.json --host 127.0.0.1 --port 8000
```

## Collect a live snapshot

The collector is deterministic: no model or agent is involved. It reads `robots.txt` first and checks every URL against it, reads the public catalog listing page by page (`/catalog?page=N`, eight entries a page), and then fetches each in-scope learning path page and course page once. It makes `GET` requests only, one request at a time, at least 1.1 seconds apart, with no cookies and no sign-in, using the User-Agent `gemini-academy-api/<version>` (set `GEMINI_ACADEMY_USER_AGENT` to add contact details). A full pass is about 400 requests and takes about ten minutes (165 catalog listing pages, 23 learning path pages, and about 210 course pages on 2026-11-13).

```bash
uv run --frozen gemini-academy-collector --snapshot data/snapshot.json --state-dir data/collector run --live
```

A page that fails keeps its previous record, an entry that leaves scope leaves the snapshot, and a pass that reads fewer than half of the published resources, or a listing that comes back more than 10% short, publishes nothing.

## Documentation, contributing, and license

- **API documentation and source:** See the [API Reference](https://gemini-academy.deployedwork.com/reference), [Swagger UI (`/docs`)](https://gemini-academy.deployedwork.com/docs), [OpenAPI 3.1 specification (`/openapi.json`)](https://gemini-academy.deployedwork.com/openapi.json), [`schema/contract.json`](schema/contract.json), and the [GitHub repository](https://github.com/dominicphillips/gemini-academy-api) for schemas, filter values, and pagination details.
- **Contributing:** See [`CONTRIBUTING.md`](CONTRIBUTING.md) for offline test, lint, and contract checks.
- **License:** Repository code is licensed under the [MIT License](LICENSE) (Copyright (c) 2026 Dominic Phillips). The MIT License covers this repository's software only and grants no rights to Google Skills courses, media, or other content.
