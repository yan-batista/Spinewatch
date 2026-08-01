"""Store adapter discovery.

Every concrete `Store` subclass under this package is picked up via
`pkgutil.iter_modules` — there is no registration list to keep in sync when
an adapter is added or removed (FR-5 / NFR-3).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sqlite3
from types import ModuleType
from urllib.parse import urlsplit

from spinewatch import repository
from spinewatch.stores.base import Store

__all__ = ["Store", "get_store", "all_stores", "sync_registry", "store_for_url"]

_instances: dict[str, Store] = {}


def _discover_modules() -> list[ModuleType]:
    """Import every module living directly under this package."""
    return [
        importlib.import_module(module_info.name)
        for module_info in pkgutil.iter_modules(__path__, prefix=f"{__name__}.")
    ]


def _collect_stores(modules: list[ModuleType]) -> dict[str, type[Store]]:
    """Collect concrete Store subclasses defined as attributes of `modules`
    into a dict keyed by `.slug`, raising ValueError on a duplicate slug.
    """
    registry: dict[str, type[Store]] = {}
    defined_in: dict[str, str] = {}
    for module in modules:
        for obj in vars(module).values():
            if not (
                isinstance(obj, type)
                and issubclass(obj, Store)
                and obj is not Store
                and not inspect.isabstract(obj)
            ):
                continue
            slug = obj.slug
            if slug in registry:
                raise ValueError(
                    f"duplicate store slug {slug!r}: defined in both "
                    f"{defined_in[slug]} and {module.__name__}"
                )
            registry[slug] = obj
            defined_in[slug] = module.__name__
    return registry


def all_stores() -> dict[str, type[Store]]:
    """Every registered store adapter class, keyed by slug."""
    return _collect_stores(_discover_modules())


def get_store(slug: str) -> Store:
    """Instantiate (and cache) the store adapter registered under `slug`."""
    if slug not in _instances:
        registry = all_stores()
        if slug not in registry:
            raise KeyError(f"no store registered with slug {slug!r}")
        _instances[slug] = registry[slug]()
    return _instances[slug]


def store_for_url(url: str) -> Store | None:
    """The registered store adapter whose `matches_url` accepts `url`, or
    None. Used by `books link` and `books fixture save` to resolve a store
    from a pasted product URL.
    """
    # Adapters match on hostname only, so without this a `file://` or `ftp://`
    # URL carrying a store hostname would be accepted here and handed straight
    # to the fetcher at crawl time.
    if urlsplit(url).scheme not in ("http", "https"):
        return None
    for slug, store_cls in all_stores().items():
        if store_cls().matches_url(url):
            return get_store(slug)
    return None


def sync_registry(conn: sqlite3.Connection) -> None:
    """Upsert every registered store adapter into the `stores` table, so
    `books store *` (and Phase 4's `crawl.py`) see current adapters even on
    a fresh database. A store already in the table keeps its existing
    `enabled` state (e.g. a prior `books store disable`); only newly
    discovered stores default to `enabled=True`.
    """
    existing_enabled = {row["slug"]: bool(row["enabled"]) for row in repository.list_stores(conn)}
    for slug, store_cls in all_stores().items():
        repository.upsert_store(
            conn, slug, store_cls.name, enabled=existing_enabled.get(slug, True)
        )
