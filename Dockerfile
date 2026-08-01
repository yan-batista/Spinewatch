# syntax=docker/dockerfile:1
#
# Multi-stage build with three targets:
#   runtime          - app + curl_cffi/selectolax HTTP fetching only, no browser.
#   runtime-browser  - the above plus Playwright/Chromium for the escalation
#                      fallback (fetching/browser.py).
#   api              - read-only HTTP API for the frontend (spinewatch/api.py),
#                      long-running instead of one-shot. No Playwright.
#
# See README.md §11 for how each target is deployed, and why the api one runs
# continuously while the crawl one is a one-shot.

FROM python:3.14-slim AS base

WORKDIR /app

# Only the packaging metadata, not the app source -- this is what the
# dependency-install layers below key their cache off of. A stub package dir
# (just an empty __init__.py) is enough for the build backend to resolve
# metadata and install dependencies via an editable install; the real source
# is copied in later, after the expensive installs, in each final stage. That
# way touching spinewatch/*.py never busts the pip-install/Chromium-download
# layer -- only the pyproject.toml dependency set does.
COPY pyproject.toml README.md ./
RUN mkdir -p spinewatch && touch spinewatch/__init__.py

# --- runtime: no Playwright, no Chromium -----------------------------------
FROM base AS runtime

RUN pip install --no-cache-dir -e .
COPY spinewatch ./spinewatch

ENV SPINEWATCH_DB_PATH=/data/books.db
ENV PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["books"]

# --- runtime-browser: adds the browser extra + Chromium -------------------
FROM base AS runtime-browser

RUN pip install --no-cache-dir -e ".[browser]" \
    && playwright install --with-deps chromium
COPY spinewatch ./spinewatch

ENV SPINEWATCH_DB_PATH=/data/books.db
ENV PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["books"]

# --- api: read-only HTTP API for the frontend, no Playwright --------------
FROM base AS api

RUN pip install --no-cache-dir -e ".[api]"
COPY spinewatch ./spinewatch

ENV SPINEWATCH_DB_PATH=/data/books.db
ENV PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["uvicorn", "spinewatch.api:app", "--host", "0.0.0.0", "--port", "8000"]
