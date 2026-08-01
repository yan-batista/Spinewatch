import pytest

from spinewatch.errors import (
    BlockedError,
    NotFoundError,
    ParseError,
    StoreError,
    UnavailableError,
)


@pytest.mark.parametrize(
    "exc_type", [BlockedError, NotFoundError, UnavailableError, ParseError]
)
def test_each_error_is_a_store_error(exc_type):
    assert issubclass(exc_type, StoreError)
    assert issubclass(StoreError, Exception)


def test_errors_carry_a_message():
    err = ParseError("could not find price element")
    assert str(err) == "could not find price element"
