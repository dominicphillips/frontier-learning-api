# Security Policy and Trust Boundaries

`claude-academy-api` separates unauthenticated public read serving from operator-run metadata collection.

## Read-only HTTP serving

- **No collection on HTTP requests:** Public endpoints (`/v1/resources`, `/v1/resources/{id}`, `/v1/categories`, `/v1/status`, `/health`, `/health/ready`, `/openapi.json`, `/docs`) are read-only and unauthenticated. Serving requests only reads a pre-validated local snapshot file; it never fetches `academy.claude.com` or starts a collector run.
- **No credentials needed:** Importing `claude_academy_api` or running `claude-academy-api` requires no key or token.
- **Public metadata only in snapshots:** Published snapshots contain only normalized public resource metadata, categories, coverage counts, and provenance (`sourceUrls`, `fetchedAt`, `contentHash`, `method`). Run reports (`STATE_DIR/runs/*.json`), the optional Cloudflare purge token, and raw fetched HTML must never be placed in served snapshot files or static assets.

## Static file serving and response headers

When `claude-academy-api` serves HTTP responses and optional `--frontend-dir` assets (tested in [`tests/test_api.py`](tests/test_api.py)):

- API and health routes are registered before static serving; unknown paths under `/v1/*` and `/health/*` return `404` and never fall back to `index.html`.
- Static resolution requires the snapshot file to reside outside `--frontend-dir` and rejects symbolic links, path traversal (`..`), dotfiles (such as `/.env`), and direct requests for `/snapshot.json` with `404`.
- All responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
- `Content-Security-Policy` is scoped by response type: JSON API responses send `default-src 'none'; frame-ancestors 'none'`; served frontend HTML restricts scripts to `'self'` and images to `'self'`, `data:` and `https://academy.claude.com` (hotlinked share images); `/docs` uses a separate policy that allows Swagger UI's `https://cdn.jsdelivr.net` and inline scripts/styles.
- Public API responses set `Access-Control-Allow-Origin: *` without `Access-Control-Allow-Credentials`.

## Collector boundaries

Source pages, the sitemap, `robots.txt` content, JSON-LD and collection artifacts are untrusted data (see [`tests/test_parse.py`](tests/test_parse.py), [`tests/test_collector.py`](tests/test_collector.py) and [`tests/test_security.py`](tests/test_security.py)):

- **No authority from source text:** Embedded instructions or permission claims inside pages are stored, if at all, only as bounded metadata strings. They cannot change hosts, paths, budgets, output locations or validation rules.
- **Host and path enforcement:** Every URL must be `https://academy.claude.com` on the default port with no credentials, IP literals, traversal, or control characters. Fetchable paths are `/robots.txt`, `/sitemap.xml` and `/courses|collections|tutorials|use-cases/<slug>`; lesson pages may be linked but are never fetched. The static excluded prefixes mirror the published `robots.txt`.
- **Polite fetching:** The collector reads and parses `robots.txt` before any other request and checks every URL against it, sends `GET` only, one request at a time, at least one second apart, with an identifying User-Agent, caps responses at 5 MB and each run at 1000 requests, never follows redirects, ignores ambient proxy settings, and retries only transient failures with bounded backoff.
- **Publication safety:** Artifacts are validated against [`schema/collection.schema.json`](schema/collection.schema.json), IDs and content hashes are recomputed, and the snapshot is written atomically with the previous copy kept. A pass that reads fewer than half of the published pages publishes nothing.
- **Cache purge:** The optional purge reads a token from a file named in the environment, purges exactly one hostname, never follows redirects, and never prints the token.

## Reporting a vulnerability privately

Do not report security vulnerabilities, exploit details, or exposed credentials in public issues, pull requests, or discussions.

- If private vulnerability reporting is enabled on the repository host where you accessed this project, submit your report through that private security advisory feature.
- Otherwise, contact the maintainer (`Dominic Phillips`, listed in [`LICENSE`](LICENSE)) to request a private reporting channel before disclosing technical details.

When reporting, include the affected component (`claude-academy-api`, `claude-academy-collector`, URL validation, or static file serving), reproduction steps, and the observed impact without including private keys or sensitive host data.
