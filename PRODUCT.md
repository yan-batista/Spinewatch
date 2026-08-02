# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person — the operator, who is also the author of the system. They add books, link each one to product URLs on stores, and check what those books cost over time. They know the domain vocabulary (listing, observation, escalation, `parse_error`) without explanation.

This is permanently single-operator. There is no second audience, no roles, no per-user state, and no plan for one. HTTP basic auth in Caddy in front of the whole site is the permanent access model.

Primary scene is a desktop browser at a workstation. The phone is an occasional check, not the main case — it must work, but the wide viewport is what the UI is designed for.

## Product Purpose

Spinewatch records what a personal list of books costs across online bookstores — Amazon BR and Mercado Livre today — writing one price observation per book, per store, per day into SQLite.

The output is the history, not the current price. Success is being able to answer "is this cheaper than it was in March?" — and to trust the answer, because a failed scrape is recorded as a failure with a reason, never as a missing day or a zero.

The web UI exists to browse that history and to manage the catalog without dropping to the CLI: a dashboard of every book with its listings and current prices, a per-book detail view (history table, chart, listing management), and a stores view.

## Positioning

Not a price-comparison service, not a commercial scraper, not a reselling aid. It is a personal instrument whose distinguishing commitment is **provenance over coverage**: every crawl attempt produces a typed row, and the schema enforces that a price exists exactly when the crawl succeeded (`CHECK ((status = 'ok') = (price_cents IS NOT NULL))`). Products that optimize for coverage collapse failure into absence; this one refuses to, because the failure taxonomy is what tells the operator whether a store is fighting back (`blocked`) or a parser has rotted (`parse_error`).

A book is linked once to a product URL and that URL is re-fetched nightly — it does not re-search every night, because search results drift between editions, used copies, and box sets, and a series built on that would be measuring something different each day.

## Operating Context

- Crawl runs unattended via host cron at 03:17 in a one-shot container; the operator reads its outcome later, not live.
- Volume is deliberately small: tens of books, a handful of stores, one pass per day. Politeness to the stores visited is a product commitment, not a performance tradeoff.
- Everything runs on one 1GB always-free VM behind Caddy (TLS + basic auth). The API container binds to `127.0.0.1:8000` only.
- The CLI (`books`) and the web UI are peers over the same database. Everything the CLI can do is reachable from the UI except adding a new store adapter, which is a code change.
- Deployment of the UI is an rsync of `frontend/` on push to `main`. `config.js` is excluded and edited in place on the VM (`API_BASE = "/api"`).

## Capabilities and Constraints

**Confirmed capabilities:** book catalog CRUD with ISBN normalization and checksum validation; assisted search and manual URL linking, multiple listings per book and store; nightly crawl with same-day idempotency and failure isolation; HTTP fetch with browser escalation bounded by a budget, only on `BlockedError`; typed observation history queryable by store and date range.

**Binding constraints:**

- **No build step, no framework, no bundler.** The frontend stays vanilla HTML/CSS/JS. Anything requiring a bundler is off the table — deployment being a file copy depends on it.
- **The 1GB VM is a real ceiling.** Asset weight and request count are constrained, not merely tidy. The page is served from the same box as the API.
- **Non-`ok` statuses are always visible as text.** `blocked`, `parse_error`, `not_found`, `unavailable`, and `error` must never render as a gap, a dash that reads as "no change", or a zero. The distinction is the operational signal the product exists to preserve.
- Prices cross the API as integer cents; division by 100 happens at render time. Never floats.
- Vocabulary is fixed by the schema and the CLI: *book*, *listing*, *store*, *observation*, *status*. Future work uses these words rather than inventing synonyms.

## Brand Commitments

The product is named **Spinewatch** and `frontend/icon.svg` exists. Neither was declared binding — the name and icon are in use, not committed identity, and future work may revisit them. Nothing else about voice, personality, or identity has been established.

## Evidence on Hand

- `books.db` — real accumulated observations, including real non-`ok` rows. Design work has actual data to show, and should use it rather than invented series.
- `tests/fixtures/` — saved store HTML; 241 tests, none touching the network.
- `README.md` — the committed system-of-record for architecture (the `docs/` design notes are deliberately uncommitted working notes).

There are no customers, testimonials, benchmarks, press, pricing, or usage numbers. None exist and none may be fabricated.

## Product Principles

1. **Failure is data.** A missing price is a typed, explained row — never a gap, never a zero. Anything that hides a failed observation is a defect, not a simplification.
2. **The history is the product.** Current price is the least interesting view of the data. Anything that makes change over time harder to see is working against the point.
3. **One operator, no ceremony.** No onboarding, no roles, no permission surfaces, no explanatory chrome for a stranger. The user knows the domain.
4. **The box is the budget.** 1GB, one VM, no build step. Ambition has to fit through an rsync.
5. **A polite visitor.** Small volume, sequential requests, jittered delays, bounded escalation. Nothing in the product may create pressure to crawl harder.
