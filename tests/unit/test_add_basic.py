import hashlib

from nectargraphenebase.account import PublicKey


def test_basic_add_functionality():
    """Basic assertions for PublicKey.add and .child"""
    test_key = "STM6oVMzJJJgSu3hV1DZBcLdMUJYj3Cs6kGXf6WVLP3HhgLgNkA5J"
    test_pub = PublicKey(test_key)
    tweak = hashlib.sha256(b"test_tweak").digest()
    result = test_pub.add(tweak)
    assert isinstance(result, PublicKey)
    assert result.prefix == test_pub.prefix
    assert str(result) != str(test_pub)
    child_key = test_pub.child(b"test_offset")
    assert isinstance(child_key, PublicKey)
