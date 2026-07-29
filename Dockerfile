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

# Source only -- no install here, so neither final stage repeats it.
COPY pyproject.toml README.md ./
COPY book_monitor ./book_monitor

# --- runtime: no Playwright, no Chromium -----------------------------------
FROM base AS runtime

RUN pip install --no-cache-dir .

ENV BOOKMON_DB_PATH=/data/books.db
ENV PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["books"]

# --- runtime-browser: adds the browser extra + Chromium -------------------
FROM base AS runtime-browser

RUN pip install --no-cache-dir ".[browser]" \
    && playwright install --with-deps chromium

ENV BOOKMON_DB_PATH=/data/books.db
ENV PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["books"]
