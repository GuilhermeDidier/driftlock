import pytest
from django.core.cache import cache

from .factories import make_source


@pytest.fixture
def source(db):
    return make_source()


@pytest.fixture(autouse=True)
def clear_throttle_state():
    """Throttles live in the cache, so state must not leak between tests."""
    cache.clear()
    yield
    cache.clear()
