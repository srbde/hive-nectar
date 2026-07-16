#!/usr/bin/env python3
"""Simple test for PublicKey.add method"""

import hashlib
import os
import sys

# Add src to path so we can import nectargraphenebase
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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


if __name__ == "__main__":
    success = test_basic_add_functionality()
    if success:
        print("\n Basic functionality test PASSED")
    else:
        print("\n Basic functionality test FAILED")
