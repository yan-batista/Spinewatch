import types

import pytest

from spinewatch import stores
from spinewatch.errors import SearchNotSupported
from spinewatch.models import ParsedListing
from spinewatch.stores.base import Store


def _make_store_class(slug: str) -> type[Store]:
    """Build a minimal concrete Store subclass with a given slug."""

    class _ConcreteStore(Store):
        name = f"Store {slug}"

        def parse_listing(self, html: str, url: str) -> ParsedListing:
            raise NotImplementedError

        def matches_url(self, url: str) -> bool:
            return False

        def normalize_url(self, url: str) -> str:
            return url

    _ConcreteStore.slug = slug
    _ConcreteStore.__name__ = f"Store_{slug}"
    return _ConcreteStore


def _make_module(name: str, *classes: type) -> types.ModuleType:
    module = types.ModuleType(name)
    for cls in classes:
        setattr(module, cls.__name__, cls)
    return module


def test_collect_stores_discovers_distinct_slugs():
    store_a = _make_store_class("store_a")
    store_b = _make_store_class("store_b")
    module_a = _make_module("fake_pkg.a", store_a)
    module_b = _make_module("fake_pkg.b", store_b)

    registry = stores._collect_stores([module_a, module_b])

    assert registry == {"store_a": store_a, "store_b": store_b}


def test_collect_stores_raises_on_duplicate_slug():
    store_c = _make_store_class("dup")
    store_d = _make_store_class("dup")
    module_c = _make_module("fake_pkg.c", store_c)
    module_d = _make_module("fake_pkg.d", store_d)

    with pytest.raises(ValueError) as exc_info:
        stores._collect_stores([module_c, module_d])

    message = str(exc_info.value)
    assert "fake_pkg.c" in message
    assert "fake_pkg.d" in message


def test_default_search_url_raises_search_not_supported():
    store = _make_store_class("some_store")()

    with pytest.raises(SearchNotSupported):
        store.search_url("anything")


def test_default_parse_search_results_raises_search_not_supported():
    store = _make_store_class("some_store")()

    with pytest.raises(SearchNotSupported):
        store.parse_search_results("<html></html>", "anything")


def test_store_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Store()
