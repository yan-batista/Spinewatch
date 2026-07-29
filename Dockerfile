# syntax=docker/dockerfile:1
#
# Multi-stage build with two targets:
#   runtime          - app + curl_cffi/selectolax HTTP fetching only, no browser.
#   runtime-browser  - the above plus Playwright/Chromium for the escalation
#                      fallback (fetching/browser.py).
#
# See docs/architecture.md §7 for why these two targets exist and how the VM
# uses them.

FROM python:3.14-slim AS base

WORKDIR /app

# Only the packaging metadata, not the app source -- this is what the
# dependency-install layers below key their cache off of. A stub package dir
# (just an empty __init__.py) is enough for the build backend to resolve
# metadata and install dependencies via an editable install; the real source
# is copied in later, after the expensive installs, in each final stage. That
# way touching book_monitor/*.py never busts the pip-install/Chromium-download
# layer -- only the pyproject.toml dependency set does.
COPY pyproject.toml README.md ./
RUN mkdir -p book_monitor && touch book_monitor/__init__.py

# --- runtime: no Playwright, no Chromium -----------------------------------
FROM base AS runtime

RUN pip install --no-cache-dir -e .
COPY book_monitor ./book_monitor

ENV BOOKMON_DB_PATH=/data/books.db
ENV PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["books"]

# --- runtime-browser: adds the browser extra + Chromium -------------------
FROM base AS runtime-browser

RUN pip install --no-cache-dir -e ".[browser]" \
    && playwright install --with-deps chromium
COPY book_monitor ./book_monitor

ENV BOOKMON_DB_PATH=/data/books.db
ENV PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["books"]
