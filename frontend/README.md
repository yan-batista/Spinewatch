# Frontend — Book Price Monitor

Static HTML/CSS/JS read-only viewer for the price history the backend
collects. No framework, no build step — see `../docs/frontend.md` for why.

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

Open `http://127.0.0.1:8080`. `config.js` already points at
`http://127.0.0.1:8000`, matching the `uvicorn` command above.

## Deploying to Vercel

1. Import this repo into Vercel.
2. Set **Root Directory** to `frontend/`.
3. Leave the build command empty — there is nothing to build.
4. Before going live, edit `config.js` to point at the deployed API's HTTPS
   URL, and add the resulting `*.vercel.app` domain (and any custom domain)
   to the API's `SPINEWATCH_CORS_ORIGINS`.

See `../docs/frontend.md` for the full design and the API contract this
page depends on.
