import time

from nectar.blockchainobject import ObjectCache


def test_cache():
    cache = ObjectCache(default_expiration=1, auto_clean=False)
    assert str(cache) == "ObjectCache(n=0, default_expiration=1)"

    # Data
    cache["foo"] = "bar"
    assert "foo" in cache
    assert cache["foo"] == "bar"
    assert cache.get("foo", "New") == "bar"

    # Expiration
    time.sleep(1.1)
    assert "foo" not in cache
    assert str(cache) == "ObjectCache(n=1, default_expiration=1)"

    # Get
    assert cache.get("foo", "New") == "New"


def test_cache_autoclean():
    cache = ObjectCache(default_expiration=1, auto_clean=True)
    assert str(cache) == "ObjectCache(n=0, default_expiration=1)"

    # Data
    cache["foo"] = "bar"
    assert str(cache) == "ObjectCache(n=1, default_expiration=1)"
    assert "foo" in cache
    assert cache["foo"] == "bar"
    assert cache.get("foo", "New") == "bar"

    # Expiration
    time.sleep(1.1)
    assert "foo" not in cache
    assert str(cache) == "ObjectCache(n=0, default_expiration=1)"
    assert len(list(cache)) == 0

    # Get
    assert cache.get("foo", "New") == "New"


def test_cache2():
    cache = ObjectCache(default_expiration=3, auto_clean=True)
    assert str(cache) == "ObjectCache(n=0, default_expiration=3)"

    # Data
    cache["foo"] = "bar"
    assert str(cache) == "ObjectCache(n=1, default_expiration=3)"
    assert "foo" in cache
    assert cache["foo"] == "bar"
    assert cache.get("foo", "New") == "bar"
    time.sleep(1)
    cache["foo2"] = "bar2"
    time.sleep(1)
    cache["foo3"] = "bar3"
    assert str(cache) == "ObjectCache(n=3, default_expiration=3)"
    # Expiration
    time.sleep(2.1)
    assert "foo" not in cache
    assert str(cache) == "ObjectCache(n=1, default_expiration=3)"
    assert len(list(cache)) == 1
    # Get
    assert cache.get("foo", "New") == "New"
