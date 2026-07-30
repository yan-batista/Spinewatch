# Book Price Monitor

Tracks what a list of books costs across online bookstores — Amazon BR, Mercado Livre, and whatever else gets added — recording one price observation per book, per store, per day into SQLite. The point is the history: knowing what a book cost in March, not just what it costs now.

Runs as a nightly cron job in Docker on a 1GB Oracle Cloud free-tier VM.

## Status

All eight phases of the development plan are implemented: catalog management, the Mercado Livre and Amazon Brazil store adapters, crawl orchestration with browser-based anti-bot escalation, assisted search/linking, price history and CSV export, and a multi-stage Docker image (`runtime` and `runtime-browser` targets). 198 tests pass offline. See [docs/development-plan.md](docs/development-plan.md) for the phase-by-phase build log and [deploy/README.md](deploy/README.md) for provisioning a VM and installing the nightly cron job — the one thing this repo does not do for you, since it requires your own VM credentials.

## Setup

Requires Python 3.13 or 3.14 (the upper bound is `selectolax`'s).

```bash
python3 -m venv venv
venv/bin/python -m pip install -e ".[browser]" --group dev
```

Drop `[browser]` to skip Playwright — the browser fallback is optional and the code must import without it. Drop `--group dev` to skip pytest.

Chromium itself is a separate download, not needed until Phase 5:

```bash
venv/bin/playwright install chromium
```

## Usage

```bash
books init                                          # create the database
books book add --title "..." --isbn ...             # add a book to track
books search <book_id> --store amazon_br            # find it on a store, confirm the match
books link <book_id> <url>                          # or paste a product URL directly
books crawl                                         # fetch today's prices — this is what cron runs
books history <book_id> --days 90                   # what has it cost
books export --csv prices.csv
```

## How it works

A book is linked **once** to a product URL on each store, and the daily crawl re-fetches those URLs. It does not re-search every night — search results drift between editions, used copies, and box sets, and a price series built on that would be measuring something different each day.

Fetching tries `curl_cffi` with a Chrome TLS fingerprint first, which is cheap and gets past most bot detection. Pages that come back blocked can escalate to a real browser, capped per run and stripped of images and CSS, because the deployment target has 1GB of RAM and Chromium is the only thing that can exhaust it.

Every crawl attempt writes a row with an explicit status — `ok`, `blocked`, `parse_error`, and so on. A failed scrape is never recorded as a missing day or a zero price. That distinction is enforced by a schema constraint, not by convention.

Adding a store means adding one file under `book_monitor/stores/`; removing it means deleting that file. Adapters are discovered at import.

## Documentation

- [docs/requirements.md](docs/requirements.md) — what it must do, and what it deliberately does not
- [docs/architecture.md](docs/architecture.md) — schema, module layout, rejected alternatives, risks
- [docs/development-plan.md](docs/development-plan.md) — build order, phase by phase
- [docs/frontend.md](docs/frontend.md) — the read-only web UI: a new API on the VPS, a static site on Vercel

## Tests

```bash
venv/bin/pytest
```

No test touches the network. Parser tests run against store HTML committed under `tests/fixtures/`.
