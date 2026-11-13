# Contributing to Gemini Academy Metadata API

This guide covers local setup, offline verification checks, and contract maintenance for contributors.

## Backend setup and offline checks

Requires Python `>=3.11` (CI runs on Python `3.11` and `3.13`) and `uv`.

Install locked dependencies and run the backend verification suite from the repository root (matching [`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All tests run offline. API tests use temporary snapshots; collector tests serve the reduced pages in [`tests/fixtures/pages/`](tests/fixtures/pages/) and the saved [`robots.txt`](tests/fixtures/robots.txt) through a fake HTTP opener. No network access or live collector run is required.

To verify the CLI against the synthetic fixture, import into a temporary snapshot path rather than `data/snapshot.json`:

```bash
uv run --locked gemini-academy-collector validate examples/collection.fixture.json
uv run --locked gemini-academy-collector --snapshot /tmp/gemini-academy-example/snapshot.json import examples/collection.fixture.json --method fixture
```

## Parser changes and page fixtures

When Google Skills changes its markup, check a page offline first:

```bash
uv run gemini-academy-collector parse tests/fixtures/pages/course_templates__1401.html --url https://www.skills.google/course_templates/1401
```

New fixtures must keep only the markup the parser reads: head metadata, `.top-title` `<h1>`, `.course-detail` header facts, `<ql-search-result-container>`, `<ql-activity-card>`, and `<ql-contents-menu>` metadata. Remove course and lesson text before committing, and never commit lab page bodies.

## Keeping schemas, examples, and tests in sync

When changing route behavior, query validation, normalization rules, or CLI options, update the corresponding files in the same change:

- **API and schema contracts:** [`schema/contract.json`](schema/contract.json), plus the generated [`schema/openapi.json`](schema/openapi.json), [`schema/resource.schema.json`](schema/resource.schema.json), [`schema/snapshot.schema.json`](schema/snapshot.schema.json) and [`schema/collection.schema.json`](schema/collection.schema.json). Regenerate them with `uv run python scripts/generate_schemas.py`.
- **OpenAPI parity test:** `test_openapi_schema_matches_generated_contract` in [`tests/test_api.py`](tests/test_api.py) asserts that `create_app("/nonexistent/snapshot.json").openapi()` equals [`schema/openapi.json`](schema/openapi.json).
- **Examples and documentation:** Keep [`examples/commands.json`](examples/commands.json), [`examples/collection.fixture.json`](examples/collection.fixture.json), and [`README.md`](README.md) aligned with actual CLI flags and field names.

## Frontend checks for changes in `frontend/`

If your change touches files under `frontend/`, run the Node `24` checks defined in [`frontend/package.json`](frontend/package.json) and [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run copy:check -- --strict
npm run build
```

## Commit messages and pull requests

- Write clear, neutral, imperative commit messages that state what changed and why.
- Include test coverage for bug fixes, validation rules, parser changes, and contract changes, and report the exact commands you ran in your pull request description.
