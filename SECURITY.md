# Security Policy

## Runtime and collection boundaries

`frontier-learning-api` separates public HTTP serving from operator-run snapshot collection:

- **Read-only local snapshot serving:** The FastAPI service (`frontier-learning-api`) reads pre-validated local JSON files (`data/openai.json`, `data/claude.json`, `data/gemini.json`). Incoming HTTP requests never trigger outbound network fetches, web crawls, or LLM/agent calls, and the service requires no provider API keys.
- **Operator-only collection (`frontier-learning-collect`):**
  - `validate`, `validate-snapshot`, `parse`, and `import` run offline against local files.
  - Live collection (`--live`) is invoked manually or on an operator schedule, never from an API route.
  - **Claude (`academy.claude.com`) and Gemini (`www.skills.google`):** Deterministic HTTP `GET` collectors check `robots.txt` and static path allow/deny lists, send sequential requests at least one second apart, never call models or agents, and never fetch gated lessons, `/focuses/` labs, user accounts, `anthropic.skilljar.com`, or internal `/api/` routes.
  - **OpenAI (`academy.openai.com`):** Live managed collection requires explicit `--live` execution, operator credentials, domain/robots enforcement, and page budgets; it excludes authenticated `/home` routes, club member pages, and SCORM packages.
- **Untrusted source content:** All scraped HTML, JSON-LD, and collection artifacts are treated as untrusted data. Collectors extract bounded metadata fields and ignore embedded prompt instructions, role changes, or permission claims.

## Reporting a vulnerability

Report suspected security vulnerabilities, SSRF/path-bypass bugs in collectors, or unintended content exposure privately by emailing Dominic Phillips at **dom@dominicphillips.de**. Include the affected component (`frontier-learning-api` or `frontier-learning-collect --provider <name>`), reproduction steps, and the observed behavior. Please allow time for remediation before public disclosure.
