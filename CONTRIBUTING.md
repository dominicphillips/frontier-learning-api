# Contributing to `frontier-learning-api`

Contributions should preserve the read-only serving boundary, per-provider metadata contracts, and offline test reproducibility.

## Prerequisites and setup

Install Node 24 (`npm`), Python `>=3.11`, and [`uv`](https://docs.astral.sh/uv/). Build the frontend before syncing the Python environment, because the wheel/sdist packages `frontend/dist`:

```bash
npm ci --prefix frontend
npm run build --prefix frontend
uv sync --frozen
```

## Offline fixture workflow

All routine development and CI checks run offline without provider credentials or live network crawling. Use the single-record synthetic fixtures in `examples/{openai,claude,gemini}/collection.fixture.json` to validate collection artifacts or build local snapshots:

```bash
for provider in openai claude gemini; do
  uv run frontier-learning-collect --provider "$provider" validate "examples/${provider}/collection.fixture.json"
  uv run frontier-learning-collect --provider "$provider" --snapshot "/tmp/frontier-test/${provider}.json" import "examples/${provider}/collection.fixture.json" --method fixture
  uv run frontier-learning-collect --provider "$provider" --snapshot "/tmp/frontier-test/${provider}.json" validate-snapshot
done
```

Do not commit generated `data/*.json` snapshots or full saved HTML pages from provider sites. HTML parser fixtures under `tests/` must stay reduced to the minimal metadata markup needed for tests.

## Required checks before opening a pull request

Run the frontend checks, Python linter, formatter check, schema generator, and test suite locally (CI runs against Python 3.11 and 3.13):

```bash
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm run copy:check --prefix frontend -- --strict
uv run ruff check .
uv run ruff format --check .
uv run python scripts/generate_schemas.py
git diff --exit-code schema/
uv run pytest
```

- `tests/test_api.py` covers unified `/v1/*` and scoped `/v1/providers/{provider}/*` behavior, cursor invariants, caching headers, and partial-availability (`503`) handling.
- `tests/{openai,claude,gemini}/` cover provider-specific URL canonicalization, content hashing, parser rules, and schema validation.

## Contract invariants to keep intact

1. **Request-time isolation:** `frontier-learning-api` reads local validated snapshot files only. Never add outbound HTTP requests, crawling, or model calls to the serving layer.
2. **Scoped vs. aggregate schemas:** Scoped routes (`/v1/providers/{provider}/*`) must preserve each provider's native `kind` enum, un-namespaced category slugs, 4-key cursor filter hash (`q`, `category`, `kind`, `audience`), and source `snapshotId`. Aggregate routes (`/v1/*`) project `provider`, namespaced `provider:slug` categories, a 5-key cursor filter hash (adding `provider`), and a combined `snapshotId` without mutating `provenance.contentHash`.
3. **Null-field and hash stability:** Keep all documented nullable fields present in JSON responses (`null` or `[]` when unknown). Preserve canonical `oa_`, `ca_`, and `ga_` ID derivation and per-provider `contentHash` rules (including OpenAI's omission of null `artwork` when computing the canonical resource hash).
