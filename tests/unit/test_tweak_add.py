import hashlib
from typing import cast

import pytest

from nectargraphenebase.account import SECP256K1_N, PublicKey


@pytest.fixture
def test_pub():
    test_pub_key = "STM6oVMzJJJgSu3hV1DZBcLdMUJYj3Cs6kGXf6WVLP3HhgLgNkA5J"
    return PublicKey(test_pub_key)


@pytest.fixture
def valid_tweak():
    return hashlib.sha256(b"test_tweak").digest()


@pytest.fixture
def zero_tweak():
    return b"\x00" * 32


@pytest.fixture
def large_tweak():
    large_num = SECP256K1_N + (1 << 100)
    return large_num.to_bytes(32, "big")


def test_basic_tweak_add(test_pub, valid_tweak):
    """Test basic tweak-add operation"""
    result = test_pub.add(valid_tweak)
    assert isinstance(result, PublicKey)
    assert result.prefix == test_pub.prefix
    assert str(result) != str(test_pub)

    # Should be deterministic
    result2 = test_pub.add(valid_tweak)
    assert str(result) == str(result2)


def test_child_method_compatibility(test_pub):
    """Test that child() method works with new add() implementation"""
    offset = b"test_offset"
    child_key = test_pub.child(offset)
    assert isinstance(child_key, PublicKey)
    assert child_key.prefix == test_pub.prefix
    assert str(child_key) != str(test_pub)


def test_tweak_validation(test_pub, valid_tweak, zero_tweak, large_tweak):
    """Test tweak validation"""
    result = test_pub.add(valid_tweak)
    assert isinstance(result, PublicKey)

    # Zero tweak should raise ValueError
    with pytest.raises(ValueError, match="cannot be zero"):
        test_pub.add(zero_tweak)

    # Tweak too large should raise ValueError
    with pytest.raises(ValueError, match="must be less than curve order"):
        test_pub.add(large_tweak)


def test_invalid_tweak_types(test_pub):
    """Test invalid tweak input types"""
    with pytest.raises(ValueError, match="must be bytes"):
        test_pub.add(cast(bytes, 12345))

    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        test_pub.add(b"short")

    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        test_pub.add(b"too_long" * 10)


def test_deterministic_behavior(test_pub):
    """Test that same inputs produce same outputs"""
    tweak1 = hashlib.sha256(b"deterministic_test_1").digest()
    tweak2 = hashlib.sha256(b"deterministic_test_2").digest()

    result1a = test_pub.add(tweak1)
    result1b = test_pub.add(tweak1)
    result2a = test_pub.add(tweak2)

    assert str(result1a) == str(result1b)
    assert str(result1a) != str(result2a)


def test_different_keys_different_results(test_pub, valid_tweak):
    """Test that different keys with same tweak give different results"""
    other_pub_key = "STM8YAMLtNcnqGNd3fx28NP3WoyuqNtzxXpwXTkZjbfe9scBmSyGT"
    other_pub = PublicKey(other_pub_key)

    result1 = test_pub.add(valid_tweak)
    result2 = other_pub.add(valid_tweak)

    assert str(result1) != str(result2)


def test_round_trip_consistency(test_pub):
    """Test that operations are consistent"""
    child = test_pub.child(b"round_trip_test")
    grandchild = child.add(hashlib.sha256(b"another_tweak").digest())

    assert isinstance(child, PublicKey)
    assert isinstance(grandchild, PublicKey)
    assert child.prefix == test_pub.prefix
    assert grandchild.prefix == test_pub.prefix
