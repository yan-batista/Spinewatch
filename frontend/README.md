# Frontend — Spinewatch

The web UI for the price history the crawler collects, plus the catalog
management the CLI exposes: a dashboard of every book and its current prices,
a per-book detail view (history table, chart, listing management), and a
stores view.

Plain HTML/CSS/JS. No framework, no bundler, no build step — a filter bar, a
few tables and `fetch()` do not need React, and skipping it is what makes
deployment a file copy. See the root [README](../README.md) §7 for the API
contract this page depends on.

| File | What it is |
|---|---|
| `index.html` | The whole page: three `<section>` views, toggled by the nav |
| `app.js` | Fetches from the API and renders the views |
| `style.css` | — |
| `config.js` | One line: `API_BASE`. Not overwritten by deploys, see below |

## Local development

The API must be running first (from the repo root, in a Python environment
with the `api` extra installed):

```bash
SPINEWATCH_DB_PATH=books.db SPINEWATCH_CORS_ORIGINS=http://127.0.0.1:8080 \
  venv/bin/uvicorn spinewatch.api:app --reload --port 8000
```

Then, from this directory, serve the static files (`fetch()` against
`file://` pages is blocked by the browser, so this needs an actual server):

```bash
python3 -m http.server 8080
```

Open `http://127.0.0.1:8080`. The committed `config.js` already points at
`http://127.0.0.1:8000`, matching the `uvicorn` command above, and
`SPINEWATCH_CORS_ORIGINS` is needed here because the page and the API are on
different origins — in production they aren't.

## Deployment

There is nothing to do by hand. Pushing to `main` makes
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) rsync this
directory to `/srv/spinewatch/frontend` on the VM, where Caddy serves it as
static files on the same domain as the API (`/api/*` is reverse-proxied to
the API container; everything else is served from here).

Two consequences worth knowing:

- **`config.js` is excluded from the rsync.** The deployed copy on the VM
  reads `API_BASE = "/api"`, matching the `handle_path` prefix in
  `deploy/Caddyfile`, and it is edited in place there. The committed copy is
  the local-development one, and deploys never clobber the VM's.
- **`--delete` is on.** Anything in `/srv/spinewatch/frontend` that isn't in
  this directory (except `config.js`) gets removed on the next deploy.

Auth is HTTP basic auth in Caddy, in front of the whole site — there is no
API key in this page and there must not be, since every byte here is served
to whoever asks. See `../deploy/README.md` §10.
