# Curiosity Radar — project rules

Read this file together with the developer's shared/root AGENTS guidance. This file only defines project-specific constraints; do not duplicate general policies.

## Design and acceptance documents

- Authoritative user stories: `docs/USER_STORIES.md` (US-xx / AC-xx).
- Target architecture and the distinction from the current implementation: `docs/SYSTEM_DESIGN.md`.
- Scope and required test evidence per PR: `docs/IMPLEMENTATION_PLAN.md`.
- First Codex task: `CODEX_START_HERE.md`. Begin with PR-00 only, then request review; no unrequested P1/P2.
- The documents are specifications, **not proof that features are implemented**. Never mark success without actual tests.

## Product contract

- Purpose: a personal Japanese discovery reader for OSS, AI, travel, security, community discussions, monetization *hypotheses*, and hobbies.
- First screen must make one useful discovery immediately. Mobile-first; no login required.
- Keep **verified facts, inference, and ideas** visibly separate. Never call an RSS excerpt an LLM summary; never present heuristic revenue ideas as validated business opportunities.
- Do not claim X trending posts are collected unless an authorized source is connected and the result is demonstrably real.
- Do not put private conversations, personal identity, health, finance, location histories, cookies, or API secrets in the repository or Pages data.

## Architecture

- `index.html`, `styles.css`, `app.js` = build-free static UI. Avoid new dependencies unless justified.
- `scripts/collect.py` = scheduled Python collector, standard library, resilient partial failure.
- `data/news.json` = public snapshot (untrusted text, no private data); mark demo mode explicitly.
- `.github/workflows/publish.yml` = collection, tests, and Pages deployment.
- `tests/` = collector tests. UI should be exercised at 400px and desktop widths.
- `sw.js` = optional offline cache. Never hide timestamp or misrepresent cached content as fresh.

## Collection and trust requirements

- Prefer official RSS and public APIs. Honor robots/TOS, source rate limits, and attribution.
- X RPA/scraping is **not approved**; do not work around paywalls, CAPTCHA, authentication, or platform limits.
- Validate source URLs, avoid storing full articles or copying protected material. Guard against RSS/HTML injection.
- Clearly label scores as **heuristics**; ranking quality is not equivalent to source reliability.
- Source outages may not clear existing live data; flag incomplete/stale collection.
- Treat GitHub repositories as untrusted code; check license and security before running or monetizing.

## Efficient workflow

- Inspect only changed/relevant files; avoid repetitive broad scans and verbose logs.
- Before changing functionality, state acceptance criteria and identify affected layers.
- Make minimal coherent edits and run `python -m unittest discover -s tests -v`, `node --check app.js`, and relevant browser smoke tests.
- For a new feed, add a parsing fixture, preserve provenance, and test one failure path.
- Never weaken tests to conceal an implementation defect. Separate external-network unverified status from locally validated behavior.

## Future improvements

- Optional LLM summaries with a cost ceiling and auditable citations; error/factuality checks required.
- Cross-source deduplication and burst metrics across equal-length snapshots.
- Notification and sharing features only after privacy/security review.
- Unit/integration checks for deployed Pages, scheduled collection health, and feed accuracy.
